import random
import asyncio
import psycopg2
import psycopg2.extras
import config
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from aiogram import Router

from database import (
    init_db, update_stats,
    reset_user_stats, get_all_user_shown_questions_count,
    log_user_answer, get_daily_user_stats,
    get_user_wrong_answers, get_mistake_questions,
    # --- чёрный список ---
    blacklist_add, blacklist_remove, blacklist_list, blacklist_is_blocked
)

bot = Bot(
    token=config.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()
router = Router()

questions = []
user_question_map = {}
last_question_text = {}
user_progress = {}
user_seen_questions = {}   # user_id -> set(question_text)

mistake_mode = {}          # user_id -> True/False
mistake_questions = {}     # user_id -> list of mistake questions
retry_attempts = {}        # user_id -> number of retries for current question

# Кэш последнего списка из /blacklist и ожидание ввода номеров для разблокировки
blacklist_cache = {}       # user_id -> [question_text]
awaiting_unban = {}        # user_id -> True/False


def load_questions_from_postgres():
    connection = psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        dbname=config.DB_NAME
    )

    with connection:
        with connection.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute("""
                SELECT question, option_a, option_b, option_c, option_d, option_e, correct_answer
                FROM questions
            """)
            result = cursor.fetchall()

            all_qs = []
            for row in result:
                options = [row[k] for k in ['option_a', 'option_b', 'option_c', 'option_d', 'option_e'] if row[k]]
                all_qs.append({
                    "question": row["question"],
                    "options": options,
                    "correct": row["correct_answer"]
                })

    return all_qs


def create_keyboard(num_options):
    builder = InlineKeyboardBuilder()
    for i in range(num_options):
        builder.button(text=str(i + 1), callback_data=f"opt_{i}")
    return builder.as_markup()


@router.message(Command("start"))
async def start_handler(message: types.Message):
    user_id = message.chat.id
    mistake_mode[user_id] = False
    await message.answer("🧠 Привет! Это тренажёр по медэкспертизе. Начнём!")
    await send_next_question(user_id)


async def send_progress_report(chat_id, user_id):
    progress = user_progress.get(user_id)
    if not progress:
        await bot.send_message(chat_id, "📭 Нет статистики.")
        return

    total = progress["total"]
    correct_count = progress["correct"]
    incorrect = total - correct_count
    percent = round(correct_count / total * 100, 1) if total else 0.0
    answered_qs = get_all_user_shown_questions_count(user_id)
    remaining = max(len(questions) - answered_qs, 0)

    report = (
        f"📊 <b>Промежуточный отчёт</b>\n"
        f"Всего решено: <b>{total}</b>\n"
        f"Верно: <b>{correct_count}</b>\n"
        f"Ошибок: <b>{incorrect}</b>\n"
        f"Точность: <b>{percent}%</b>\n"
        f"📚 Ещё не отвечено: <b>{remaining}</b>"
    )
    await bot.send_message(chat_id, report)


async def send_next_question(chat_id):
    user_id = chat_id
    previous_question = last_question_text.get(user_id)

    # исключаем заблокированные вопросы
    blocked_set = set(blacklist_list(user_id))

    def is_allowed(qtext: str) -> bool:
        return (qtext not in blocked_set) and (qtext != previous_question)

    if mistake_mode.get(user_id):
        pool_src = mistake_questions.get(user_id, [])
        pool = [q for q in pool_src if is_allowed(q["question"])]
        if not pool:
            pool = [q for q in pool_src if q["question"] not in blocked_set]
    else:
        seen = user_seen_questions.setdefault(user_id, set())
        pool = [q for q in questions if (q["question"] not in seen) and is_allowed(q["question"])]
        if not pool:
            pool = [q for q in questions if is_allowed(q["question"])]
        if not pool:
            pool = [q for q in questions if q["question"] not in blocked_set]
        if not pool:
            pool = questions  # крайний случай

    if not pool:
        await bot.send_message(chat_id, "📭 Вопросов не найдено.")
        return

    q = random.choice(pool)
    shuffled = q["options"].copy()
    random.shuffle(shuffled)
    q["shuffled_options"] = shuffled

    user_question_map[user_id] = q
    last_question_text[user_id] = q["question"]
    if not mistake_mode.get(user_id):
        user_seen_questions.setdefault(user_id, set()).add(q["question"])

    retry_attempts[user_id] = 0

    text = f"<b>Вопрос:</b>\n{q['question']}\n\n"
    for idx, option in enumerate(shuffled, 1):
        text += f"{idx}. {option}\n"

    keyboard = create_keyboard(len(shuffled))
    await bot.send_message(chat_id, text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("opt_"))
async def handle_answer(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    q = user_question_map.get(user_id)
    if not q:
        await callback.answer("Ошибка. Попробуйте снова.", show_alert=True)
        return

    index = int(callback.data.replace("opt_", ""))
    selected = q["shuffled_options"][index].strip()
    correct = (q["correct"] or "").strip()
    is_correct = selected == correct

    update_stats(user_id, q["question"], is_correct)
    log_user_answer(user_id, datetime.utcnow().date(), is_correct, q["question"], selected, correct)

    progress = user_progress.setdefault(user_id, {"total": 0, "correct": 0})
    progress["total"] += 1
    if is_correct:
        progress["correct"] += 1

    text = (
        f"✅ Верно!\n<b>{q['question']}</b>\nОтвет: <b>{correct}</b>"
        if is_correct else
        f"❌ Неверно!\n<b>{q['question']}</b>\nПравильный ответ: <b>{correct}</b>"
    )

    # Кнопка "Больше не показывать" — появляется после ответа
    kb = InlineKeyboardBuilder()
    kb.button(text="Больше не показывать", callback_data="block_q")
    await callback.message.edit_text(text, reply_markup=kb.as_markup())

    # Режим тренировки ошибок
    if mistake_mode.get(user_id):
        if is_correct and q in mistake_questions.get(user_id, []):
            mistake_questions[user_id].remove(q)
        elif not is_correct:
            retry_attempts[user_id] += 1
            if retry_attempts[user_id] < 2:
                await asyncio.sleep(1)
                await bot.send_message(callback.message.chat.id, "🔁 Попробуй ещё раз!")
                await send_next_question(callback.message.chat.id)
                return

        if not mistake_questions.get(user_id):
            await bot.send_message(callback.message.chat.id, "🎯 Все ошибки отработаны! Возвращаемся к обычному режиму.")
            mistake_mode[user_id] = False

    if progress["total"] % 50 == 0:
        await send_progress_report(callback.message.chat.id, user_id)

    await asyncio.sleep(1.5)
    await send_next_question(callback.message.chat.id)


# Нажатие "Больше не показывать"
@router.callback_query(F.data == "block_q")
async def on_block_question(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    q = user_question_map.get(user_id)
    if not q:
        await callback.answer("Не удалось определить вопрос.", show_alert=True)
        return

    question_text = q["question"]
    if not blacklist_is_blocked(user_id, question_text):
        blacklist_add(user_id, question_text)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await bot.send_message(callback.message.chat.id, "🚫 Ок, больше не покажу этот вопрос 👌")


# ======= Новый UX для чёрного списка =======

def _format_blacklist_list(items):
    lines = ["<b>Заблокированные вопросы:</b>"]
    for i, qtext in enumerate(items, start=1):
        preview = qtext.strip().replace("\n", " ")
        if len(preview) > 80:
            preview = preview[:77] + "..."
        lines.append(f"{i}. {preview}")
    return "\n".join(lines)


def _parse_indices(text: str, max_n: int) -> list[int]:
    """
    Парсит ввод пользователя с номерами:
    - разделители: пробелы или запятые
    - диапазоны: 2-5
    Возвращает отсортированный список уникальных индексов (1..max_n)
    """
    raw = text.replace(",", " ").split()
    indices = set()
    for token in raw:
        if "-" in token:
            try:
                a, b = token.split("-", 1)
                a, b = int(a), int(b)
                if a > b:
                    a, b = b, a
                for v in range(a, b + 1):
                    if 1 <= v <= max_n:
                        indices.add(v)
            except ValueError:
                continue
        else:
            try:
                v = int(token)
                if 1 <= v <= max_n:
                    indices.add(v)
            except ValueError:
                continue
    return sorted(indices)


@router.message(Command("blacklist"))
async def blacklist_handler(message: types.Message):
    user_id = message.from_user.id
    items = blacklist_list(user_id)  # список строк-вопросов
    if not items:
        awaiting_unban.pop(user_id, None)
        blacklist_cache.pop(user_id, None)
        await message.answer("Твой чёрный список пуст.")
        return

    blacklist_cache[user_id] = items[:]  # запомним порядок
    awaiting_unban[user_id] = True       # ждём следующий ввод с номерами

    text = _format_blacklist_list(items)
    text += "\n\nНапиши номера вопросов, которые нужно разблокировать (через пробел/запятые, диапазоны поддерживаются: <code>2-5</code>)."
    await message.answer(text)


# Перехват следующего сообщения после /blacklist для разблокировки
@router.message(F.text & ~F.text.startswith("/"))
async def maybe_unban_numbers(message: types.Message):
    user_id = message.from_user.id
    # если не ждём ввод — это обычный ответ на вопрос (игровой флоу не здесь обрабатывается)
    if not awaiting_unban.get(user_id):
        return

    items = blacklist_cache.get(user_id) or []
    if not items:
        awaiting_unban[user_id] = False
        await message.answer("Список заблокированных пуст.")
        return

    idxs = _parse_indices(message.text or "", len(items))
    if not idxs:
        await message.answer("Не удалось распознать номера. Пример: <code>1 3 5-7</code>")
        return

    # Разблокируем выбранные
    unlocked = []
    for i in idxs:
        qtext = items[i - 1]
        blacklist_remove(user_id, qtext)
        unlocked.append(i)

    # Обновим список
    new_items = blacklist_list(user_id)
    blacklist_cache[user_id] = new_items
    awaiting_unban[user_id] = False

    reply = f"✅ Разблокировано: {', '.join(map(str, unlocked))}."
    if new_items:
        reply += "\n\n" + _format_blacklist_list(new_items)
        reply += "\n\nЕсли хочешь разблокировать ещё — снова введи номера или вызови /blacklist."
    else:
        reply += "\nЧёрный список теперь пуст."

    await message.answer(reply)


# ===========================================


@router.message(Command("progress"))
async def progress_handler(message: types.Message):
    await send_progress_report(message.chat.id, message.from_user.id)


@router.message(Command("week"))
async def weekly_stats_handler(message: types.Message):
    user_id = message.from_user.id
    today = datetime.utcnow().date()
    text_lines = []
    for i in range(7):
        day = today - timedelta(days=i)
        total, correct = get_daily_user_stats(user_id, day)
        if total == 0:
            continue
        percent = round(correct / total * 100, 1)
        text_lines.append(f"{day.strftime('%Y-%m-%d')}: {correct}/{total} — {percent}%")

    if text_lines:
        text = "<b>📅 Ваша статистика за последние 7 дней:</b>\n" + "\n".join(text_lines)
    else:
        text = "📭 Нет данных за неделю."

    await message.answer(text)


@router.message(Command("stats"))
async def stats_handler(message: types.Message):
    rows = get_user_wrong_answers(message.from_user.id)
    if not rows:
        await message.answer("📬 У вас пока нет ошибок.")
        return

    lines = ["<b>❌ Ошибки по вопросам:</b>"]
    for i, row in enumerate(rows, 1):
        question = row.get('question') or "[вопрос не найден]"
        user_answer = row.get('user_answer') or "-"
        correct_answer = row.get('correct_answer') or "-"
        date_obj = row.get('answered_at')
        date_str = date_obj.strftime('%Y-%m-%d') if date_obj else "неизвестно"
        lines.append(f"{i}. {question[:40]}... — вы выбрали: {user_answer}, верно: {correct_answer} (дата: {date_str})")

    await message.answer("\n".join(lines))


@router.message(Command("errors"))
async def train_mistakes_handler(message: types.Message):
    user_id = message.from_user.id
    mistake_mode[user_id] = True
    mistake_questions[user_id] = get_mistake_questions(user_id)
    if not mistake_questions[user_id]:
        await message.answer("🎉 Нет ошибок для повторения — хорошая работа!")
        mistake_mode[user_id] = False
        return
    await message.answer("🔁 Начинаем тренировку на ошибках!")
    await send_next_question(user_id)


@router.message(Command("reset"))
async def reset_handler(message: types.Message):
    user_id = message.from_user.id
    reset_user_stats(user_id)
    user_progress[user_id] = {"total": 0, "correct": 0}
    user_seen_questions[user_id] = set()
    # Сброс локальных состояний, связанных с blacklist UX
    blacklist_cache.pop(user_id, None)
    awaiting_unban.pop(user_id, None)
    await message.answer("🔄 Ваша статистика сброшена.")


@router.message(Command("help"))
async def help_handler(message: types.Message):
    text = (
        "🧠 <b>Тренажёр по медэкспертизе</b>\n\n"
        "Ты получаешь вопрос с несколькими вариантами.\n"
        "✅ Верно — идём дальше.\n"
        "❌ Неверно — бот покажет правильный.\n\n"
        "📈 <b>Команды:</b>\n"
        "/start — обычный режим\n"
        "/errors — тренировка ошибок\n"
        "/stats — список ошибок\n"
        "/progress — прогресс\n"
        "/week — статистика по дням\n"
        "/reset — сбросить всё\n"
        "/blacklist — показать чёрный список; затем пришли номера для разблокировки\n"
        "/help — это меню"
    )
    await message.answer(text)


def main():
    init_db()
    global questions
    questions = load_questions_from_postgres()
    dp.include_router(router)
    dp.run_polling(bot)


if __name__ == "__main__":
    main()
