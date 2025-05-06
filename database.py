import pymysql
from datetime import datetime
import config

def get_connection():
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )

def init_db():
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    user_id BIGINT,
                    question TEXT,
                    shown INT DEFAULT 0,
                    wrong INT DEFAULT 0,
                    PRIMARY KEY (user_id, question(255))
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT,
                    question TEXT,
                    user_answer TEXT,
                    correct_answer TEXT,
                    is_correct BOOLEAN,
                    answered_at DATE
                )
            """)

def update_stats(user_id, question, correct):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO stats (user_id, question, shown, wrong)
                VALUES (%s, %s, 1, %s)
                ON DUPLICATE KEY UPDATE
                    shown = shown + 1,
                    wrong = wrong + VALUES(wrong)
            """, (user_id, question, 0 if correct else 1))

def log_user_answer(user_id, date, correct, question=None, user_answer=None, correct_answer=None):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO logs (user_id, question, user_answer, correct_answer, is_correct, answered_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, question, user_answer, correct_answer, correct, date))

def get_question_stats(user_id, question):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("SELECT shown, wrong FROM stats WHERE user_id = %s AND question = %s", (user_id, question))
            row = c.fetchone()
            return {"shown": row['shown'], "wrong": row['wrong']} if row else {"shown": 0, "wrong": 0}

def get_user_top_mistakes(user_id, limit=5):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT question, wrong, shown,
                       ROUND(wrong / shown * 100, 1) AS rate
                FROM stats
                WHERE user_id = %s AND shown > 0
                ORDER BY rate DESC, wrong DESC
                LIMIT %s
            """, (user_id, limit))
            return c.fetchall()

def get_all_user_shown_questions_count(user_id):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) AS cnt FROM stats WHERE user_id = %s AND shown > 0", (user_id,))
            return c.fetchone()['cnt']

def get_daily_user_stats(user_id, day):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT COUNT(*) AS total,
                       SUM(is_correct) AS correct
                FROM logs
                WHERE user_id = %s AND answered_at = %s
            """, (user_id, day))
            row = c.fetchone()
            return row['total'] or 0, row['correct'] or 0

def get_user_wrong_answers(user_id):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT question, user_answer, correct_answer, answered_at
                FROM logs
                WHERE user_id = %s AND is_correct = FALSE
                ORDER BY answered_at DESC
            """, (user_id,))
            return c.fetchall()

def get_mistake_questions(user_id):
    with get_connection() as conn:
        with conn.cursor() as c:
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
                    FROM questions WHERE question = %s
                """, (q_text,))
                opt = c.fetchone()
                if not opt:
                    continue
                options = [opt[k] for k in opt if opt[k]]
                questions.append({
                    'question': q_text,
                    'options': options,
                    'correct': row['correct_answer']
                })
            return questions

def reset_user_stats(user_id):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM stats WHERE user_id = %s", (user_id,))
            c.execute("DELETE FROM logs WHERE user_id = %s", (user_id,))
