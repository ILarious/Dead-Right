import pymysql
import config

def get_connection():
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )

def init_db():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_stats (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT,
                    question TEXT,
                    is_correct BOOLEAN,
                    answered_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_daily_summary (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT,
                    day DATE,
                    total INT DEFAULT 0,
                    correct INT DEFAULT 0,
                    UNIQUE KEY unique_day_user (user_id, day)
                )
            """)
        conn.commit()

def update_stats(user_id, question, is_correct):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO user_stats (user_id, question, is_correct)
                VALUES (%s, %s, %s)
            """, (user_id, question, is_correct))
        conn.commit()

def get_question_stats(user_id, question):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) AS shown,
                       SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) AS wrong
                FROM user_stats
                WHERE user_id = %s AND question = %s
            """, (user_id, question))
            result = cursor.fetchone()
            return {"shown": result["shown"] or 0, "wrong": result["wrong"] or 0}

def get_user_top_mistakes(user_id, limit=5):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT question,
                       SUM(is_correct = 0) AS wrong,
                       COUNT(*) AS shown,
                       ROUND(SUM(is_correct = 0) / COUNT(*) * 100, 1) AS error_rate
                FROM user_stats
                WHERE user_id = %s
                GROUP BY question
                HAVING shown >= 3
                ORDER BY error_rate DESC, shown DESC
                LIMIT %s
            """, (user_id, limit))
            return [(row["question"], row["wrong"], row["shown"], row["error_rate"]) for row in cursor.fetchall()]

def reset_user_stats(user_id):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM user_stats WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM user_daily_summary WHERE user_id = %s", (user_id,))
        conn.commit()

def get_all_user_shown_questions_count(user_id):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(DISTINCT question) AS count
                FROM user_stats
                WHERE user_id = %s
            """, (user_id,))
            return cursor.fetchone()["count"]

def log_user_answer(user_id, day, is_correct):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO user_daily_summary (user_id, day, total, correct)
                VALUES (%s, %s, 1, %s)
                ON DUPLICATE KEY UPDATE
                    total = total + 1,
                    correct = correct + VALUES(correct)
            """, (user_id, day, int(is_correct)))
        conn.commit()

def get_daily_user_stats(user_id, day):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT total, correct
                FROM user_daily_summary
                WHERE user_id = %s AND day = %s
            """, (user_id, day))
            row = cursor.fetchone()
            return (row["total"], row["correct"]) if row else (0, 0)
