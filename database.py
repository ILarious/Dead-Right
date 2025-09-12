import psycopg2
import psycopg2.extras
from datetime import datetime
import config

def get_connection():
    return psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        dbname=config.DB_NAME
    )

def init_db():
    with get_connection() as conn:
        conn.autocommit = True
        with conn.cursor() as c:
            # Statistics Table: PK (user_id, question)
            c.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    user_id BIGINT NOT NULL,
                    question TEXT NOT NULL,
                    shown INTEGER NOT NULL DEFAULT 0,
                    wrong INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, question)
                )
            """)

            # Log of answers
            c.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    question TEXT,
                    user_answer TEXT,
                    correct_answer TEXT,
                    is_correct BOOLEAN NOT NULL,
                    answered_at DATE NOT NULL
                )
            """)

            # Blacklist of questions per user
            c.execute("""
                CREATE TABLE IF NOT EXISTS user_blocked_questions (
                    user_id BIGINT NOT NULL,
                    question TEXT NOT NULL,
                    PRIMARY KEY (user_id, question)
                )
            """)


def blacklist_add(user_id: int, question: str) -> None:
    """Добавить вопрос в чёрный список пользователя (идемпотентно)."""
    with get_connection() as conn:
        conn.autocommit = True
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO user_blocked_questions (user_id, question)
                VALUES (%s, %s)
                ON CONFLICT (user_id, question) DO NOTHING
            """, (user_id, question))


def blacklist_remove(user_id: int, question: str) -> None:
    """Удалить вопрос из чёрного списка пользователя."""
    with get_connection() as conn:
        conn.autocommit = True
        with conn.cursor() as c:
            c.execute("""
                DELETE FROM user_blocked_questions
                WHERE user_id = %s AND question = %s
            """, (user_id, question))


def blacklist_is_blocked(user_id: int, question: str) -> bool:
    """Проверить, заблокирован ли вопрос пользователем."""
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT 1
                FROM user_blocked_questions
                WHERE user_id = %s AND question = %s
                LIMIT 1
            """, (user_id, question))
            return c.fetchone() is not None


def blacklist_list(user_id: int):
    """Return the list of user blocked questions (list of lines)."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute("""
                SELECT question
                FROM user_blocked_questions
                WHERE user_id = %s
                ORDER BY question
            """, (user_id,))
            rows = c.fetchall()
            return [row["question"] for row in rows]


def blacklist_clear(user_id: int) -> None:
    """Clean the entire black list of the user."""
    with get_connection() as conn:
        conn.autocommit = True
        with conn.cursor() as c:
            c.execute("""
                DELETE FROM user_blocked_questions
                WHERE user_id = %s
            """, (user_id,))



def update_stats(user_id, question, correct):
    """
    We insert the recording, with a conflict in the (user_id, Question) we increase the counters.
    """
    with get_connection() as conn:
        conn.autocommit = True
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO stats (user_id, question, shown, wrong)
                VALUES (%s, %s, 1, %s)
                ON CONFLICT (user_id, question) DO UPDATE SET
                    shown = stats.shown + 1,
                    wrong = stats.wrong + EXCLUDED.wrong
            """, (user_id, question, 0 if correct else 1))

def log_user_answer(user_id, date, correct, question=None, user_answer=None, correct_answer=None):
    with get_connection() as conn:
        conn.autocommit = True
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO logs (user_id, question, user_answer, correct_answer, is_correct, answered_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, question, user_answer, correct_answer, correct, date))

def get_question_stats(user_id, question):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute("""
                SELECT shown, wrong
                FROM stats
                WHERE user_id = %s AND question = %s
            """, (user_id, question))
            row = c.fetchone()
            return {"shown": row['shown'], "wrong": row['wrong']} if row else {"shown": 0, "wrong": 0}

def get_user_top_mistakes(user_id, limit=5):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute("""
                SELECT
                    question,
                    wrong,
                    shown,
                    ROUND(wrong::numeric / NULLIF(shown, 0) * 100, 1) AS rate
                FROM stats
                WHERE user_id = %s AND shown > 0
                ORDER BY rate DESC NULLS LAST, wrong DESC
                LIMIT %s
            """, (user_id, limit))
            return c.fetchall()

def get_all_user_shown_questions_count(user_id):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute("""
                SELECT COUNT(*) AS cnt
                FROM stats
                WHERE user_id = %s AND shown > 0
            """, (user_id,))
            return c.fetchone()['cnt']

def get_daily_user_stats(user_id, day):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) AS correct
                FROM logs
                WHERE user_id = %s AND answered_at = %s
            """, (user_id, day))
            row = c.fetchone()
            total = row['total'] or 0
            correct = row['correct'] or 0
            return total, correct

def get_user_wrong_answers(user_id):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute("""
                SELECT question, user_answer, correct_answer, answered_at
                FROM logs
                WHERE user_id = %s AND is_correct = FALSE
                ORDER BY answered_at DESC
            """, (user_id,))
            return c.fetchall()

def get_mistake_questions(user_id):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute("""
                SELECT DISTINCT question, correct_answer
                FROM logs
                WHERE user_id = %s AND is_correct = FALSE
            """, (user_id,))
            results = c.fetchall()

            questions = []
            for row in results:
                q_text = row['question']
                c.execute("""
                    SELECT option_a, option_b, option_c, option_d, option_e
                    FROM questions
                    WHERE question = %s
                """, (q_text,))
                opt = c.fetchone()
                if not opt:
                    continue

                options = [opt[k] for k in ('option_a', 'option_b', 'option_c', 'option_d', 'option_e') if opt.get(k)]
                questions.append({
                    'question': q_text,
                    'options': options,
                    'correct': row['correct_answer']
                })
            return questions

def reset_user_stats(user_id):
    with get_connection() as conn:
        conn.autocommit = True
        with conn.cursor() as c:
            c.execute("DELETE FROM stats WHERE user_id = %s", (user_id,))
            c.execute("DELETE FROM logs WHERE user_id = %s", (user_id,))

