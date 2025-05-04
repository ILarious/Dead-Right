import sqlite3

def init_db():
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            user_id INTEGER,
            question TEXT,
            shown INTEGER DEFAULT 0,
            wrong INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, question)
        )
    ''')
    conn.commit()
    conn.close()

def update_stats(user_id, question, correct):
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute('''
        INSERT OR IGNORE INTO stats (user_id, question) VALUES (?, ?)
    ''', (user_id, question))
    if not correct:
        c.execute('''
            UPDATE stats SET shown = shown + 1, wrong = wrong + 1
            WHERE user_id = ? AND question = ?
        ''', (user_id, question))
    else:
        c.execute('''
            UPDATE stats SET shown = shown + 1
            WHERE user_id = ? AND question = ?
        ''', (user_id, question))
    conn.commit()
    conn.close()

def get_question_stats(user_id, question):
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute('''
        SELECT shown, wrong FROM stats
        WHERE user_id = ? AND question = ?
    ''', (user_id, question))
    row = c.fetchone()
    conn.close()
    return {"shown": row[0], "wrong": row[1]} if row else {"shown": 0, "wrong": 0}

def get_user_top_mistakes(user_id, limit=5):
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute('''
        SELECT question, wrong, shown,
               ROUND(CAST(wrong AS REAL) / shown * 100.0, 1) AS error_rate
        FROM stats
        WHERE user_id = ? AND shown > 0
        ORDER BY error_rate DESC, wrong DESC
        LIMIT ?
    ''', (user_id, limit))
    results = c.fetchall()
    conn.close()
    return results

def reset_user_stats(user_id):
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute('DELETE FROM stats WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()


def get_all_user_shown_questions_count(user_id):
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM stats WHERE user_id = ? AND shown > 0", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

