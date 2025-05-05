import random
import asyncio
import pymysql
import config
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from aiogram import Router


from database import (
    init_db, update_stats,
    get_question_stats, get_user_top_mistakes,
    reset_user_stats, get_all_user_shown_questions_count
)

bot = Bot(
    token=config.BOT_TOKEN_TEST,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()
router = Router()

questions = []
user_question_map = {}
last_question_text = {}
user_progress = {}

def load_questions_from_mysql():
    connection = pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )
    with connection:
        with connection.cursor() as cursor:
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
    await message.answer("🧠 Привет! Это тренажёр по медэкспертизе. Начнём!")
    await send_next_question(message.chat.id)

async def send_next_question(chat_id):
    user_id = chat_id
    previous_question = last_question_text.get(user_id)

    available_questions = [q for q in questions if q["question"] != previous_question]
    if not available_questions:
        available_questions = questions

    weights = []
    for q in available_questions:
        stats = get_question_stats(user_id, q["question"])
        shown = stats.get("shown", 0)
        wrong = stats.get("wrong", 0)
        weight = 1.0 if shown == 0 else (wrong + 1) / shown
        weights.append(weight)

    q = random.choices(available_questions, weights=weights, k=1)[0]
    shuffled = q["options"].copy()
    random.shuffle(shuffled)
    q["shuffled_options"] = shuffled

    user_question_map[user_id] = q
    last_question_text[user_id] = q["question"]

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
    correct = q["correct"].strip()
    update_stats(user_id, q["question"], selected == correct)

    progress = user_progress.setdefault(user_id, {"total": 0, "correct": 0})
    progress["total"] += 1
    if selected == correct:
        progress["correct"] += 1

    text = (
        f"✅ Верно!\n<b>{q['question']}</b>\nОтвет: <b>{correct}</b>"
        if selected == correct else
        f"❌ Неверно!\n<b>{q['question']}</b>\nПравильный ответ: <b>{correct}</b>"
    )

    await callback.message.edit_text(text)

    if progress["total"] % 50 == 0:
        await send_progress_report(callback.message.chat.id, user_id)

    await asyncio.sleep(1.5)
    await send_next_question(callback.message.chat.id)

async def send_progress_report(chat_id, user_id):
    progress = user_progress.get(user_id)
    if not progress:
        return

    total = progress["total"]
    correct_count = progress["correct"]
    incorrect = total - correct_count
    percent = round(correct_count / total * 100, 1)
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

@router.message(Command("progress"))
async def progress_handler(message: types.Message):
    await send_progress_report(message.chat.id, message.from_user.id)

@router.message(Command("stats"))
async def stats_handler(message: types.Message):
    results = get_user_top_mistakes(message.from_user.id)
    if not results:
        await message.answer("📬 У вас пока нет статистики.")
        return

    text = "<b>📉 Ваши ошибки:</b>\n"
    for i, (q, wrong, shown, rate) in enumerate(results, 1):
        text += f"{i}. {q[:50]}... — {wrong}/{shown} ошибок ({rate}%)\n"
    await message.answer(text)

@router.message(Command("reset"))
async def reset_handler(message: types.Message):
    reset_user_stats(message.from_user.id)
    user_progress[message.from_user.id] = {"total": 0, "correct": 0}
    await message.answer("🔄 Ваша статистика сброшена.")

@router.message(Command("help"))
async def help_handler(message: types.Message):
    text = (
        "🧠 <b>Тренажёр по медэкспертизе</b>\n\n"
        "Ты получаешь вопрос с несколькими вариантами.\n"
        "✅ Верно — идём дальше.\n"
        "❌ Неверно — бот покажет правильный.\n\n"
        "📈 <b>Команды:</b>\n"
        "/start — начать или продолжить\n"
        "/stats — твоя статистика ошибок\n"
        "/progress — промежуточный отчёт\n"
        "/reset — сбросить статистику\n"
        "/help — это меню"
    )
    await message.answer(text)

def main():
    init_db()
    global questions
    questions = load_questions_from_mysql()
    dp.include_router(router)
    dp.run_polling(bot)

if __name__ == "__main__":
    main()