import sqlite3
import time
from pathlib import Path
from typing import Optional, Dict, List

Path("data").mkdir(exist_ok=True)
DB_PATH = "data/database.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        # Таблица пользователей
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                login TEXT,
                access_token TEXT,
                refresh_token TEXT,
                token_type TEXT,
                expires_in INTEGER,
                timestamp TEXT
            )
        """)
        # Таблица уведомлений (без полей форума)
        c.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                telegram_id INTEGER PRIMARY KEY,
                schedule_enabled INTEGER DEFAULT 0,
                frequency TEXT,
                schedule_type TEXT,
                preferred_day INTEGER,
                preferred_time TEXT
            )
        """)
        # Таблица дисциплин
        c.execute("""
            CREATE TABLE IF NOT EXISTS disciplines (
                user_id INTEGER,
                discipline_id INTEGER,
                title TEXT,
                PRIMARY KEY (user_id, discipline_id)
            )
        """)
        # Таблица состояния форума
        c.execute("""
            CREATE TABLE IF NOT EXISTS forum_states (
                user_id INTEGER,
                discipline_id INTEGER,
                last_message_id INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, discipline_id)
            )
        """)
        # Таблица настроек форума
        c.execute("""
            CREATE TABLE IF NOT EXISTS forum_settings (
                telegram_id INTEGER PRIMARY KEY,
                forum_enabled INTEGER DEFAULT 1,
                polling_interval INTEGER DEFAULT 60,
                last_polling_time TEXT,
                FOREIGN KEY (telegram_id) REFERENCES notifications(telegram_id)
            )
        """)
        conn.commit()
        migrate_notifications_table()

def migrate_notifications_table():
    """Переносит настройки форума из notifications в forum_settings и удаляет старые поля."""
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("PRAGMA table_info(notifications)")
        columns = [col[1] for col in c.fetchall()]
        if 'forum_enabled' in columns:
            c.execute("""
                INSERT OR REPLACE INTO forum_settings (telegram_id, forum_enabled, polling_interval, last_polling_time)
                SELECT telegram_id, forum_enabled, polling_interval, last_polling_time
                FROM notifications
                WHERE forum_enabled IS NOT NULL OR polling_interval IS NOT NULL OR last_polling_time IS NOT NULL
            """)
            c.execute("CREATE TABLE notifications_new (telegram_id INTEGER PRIMARY KEY, schedule_enabled INTEGER DEFAULT 0, frequency TEXT, schedule_type TEXT, preferred_day INTEGER, preferred_time TEXT)")
            c.execute("INSERT INTO notifications_new SELECT telegram_id, schedule_enabled, frequency, schedule_type, preferred_day, preferred_time FROM notifications")
            c.execute("DROP TABLE notifications")
            c.execute("ALTER TABLE notifications_new RENAME TO notifications")
        conn.commit()

def save_user_disciplines(telegram_id: int, disciplines: list[dict]):
    """Сохраняет список дисциплин для пользователя"""
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM disciplines WHERE user_id = ?", (telegram_id,))
        for d in disciplines:
            c.execute(
                "INSERT INTO disciplines (user_id, discipline_id, title) VALUES (?, ?, ?)",
                (telegram_id, d["DisciplineId"], d.get("Title", "")),
            )
        conn.commit()

def get_user_disciplines(telegram_id: int) -> list[dict]:
    """Возвращает список дисциплин из БД"""
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT discipline_id, title FROM disciplines WHERE user_id = ?", (telegram_id,))
        return [{"DisciplineId": row[0], "Title": row[1]} for row in c.fetchall()]

def get_last_forum_message_id(telegram_id: int, discipline_id: int) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT last_message_id 
            FROM forum_states 
            WHERE user_id = ? AND discipline_id = ?
        """, (telegram_id, discipline_id))
        row = c.fetchone()
        return row[0] if row else 0

def update_last_forum_message_id(telegram_id: int, discipline_id: int, last_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO forum_states (user_id, discipline_id, last_message_id)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, discipline_id) DO UPDATE SET last_message_id=excluded.last_message_id
        """, (telegram_id, discipline_id, last_id))
        conn.commit()

def save_user_token(telegram_id: int, login: str, token_data: dict):
    """Сохраняет или обновляет токены пользователя"""
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO users 
            (telegram_id, login, access_token, refresh_token, token_type, expires_in, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            telegram_id,
            login,
            token_data.get('access_token'),
            token_data.get('refresh_token'),
            token_data.get('token_type'),
            token_data.get('expires_in'),
            int(time.time())
        ))
        c.execute("""
            INSERT OR IGNORE INTO notifications 
            (telegram_id, schedule_enabled)
            VALUES (?, 0)
        """, (telegram_id,))
        c.execute("""
            INSERT OR IGNORE INTO forum_settings 
            (telegram_id, forum_enabled, polling_interval)
            VALUES (?, 1, 60)
        """, (telegram_id,))
        conn.commit()

def get_user_token(telegram_id: int) -> Optional[Dict]:
    """Возвращает данные пользователя"""
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        user = c.fetchone()
        return {
            "access_token": user[2],
            "refresh_token": user[3],
            "token_type": user[4],
            "expires_in": user[5],
            "timestamp": user[6]
        } if user else None

def save_notification_settings(
        telegram_id: int,
        **kwargs
):
    """Сохраняет настройки расписания"""
    current = get_notification_settings(telegram_id)
    new_settings = {
        'schedule_enabled': kwargs.get('schedule_enabled', current['schedule_enabled']),
        'frequency': kwargs.get('frequency', current['frequency']),
        'schedule_type': kwargs.get('schedule_type', current['schedule_type']),
        'preferred_day': kwargs.get('preferred_day', current['preferred_day']),
        'preferred_time': kwargs.get('preferred_time', current['preferred_time'])
    }
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO notifications 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            telegram_id,
            new_settings['schedule_enabled'],
            new_settings['frequency'],
            new_settings['schedule_type'],
            new_settings['preferred_day'],
            new_settings['preferred_time']
        ))
        conn.commit()

def get_notification_settings(telegram_id: int) -> Dict:
    """Возвращает настройки расписания"""
    defaults = {
        'schedule_enabled': False,
        'frequency': None,
        'schedule_type': None,
        'preferred_day': None,
        'preferred_time': None
    }
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM notifications WHERE telegram_id = ?", (telegram_id,))
        settings = c.fetchone()
        if not settings:
            return defaults
        return {
            'schedule_enabled': bool(settings[1]),
            'frequency': settings[2],
            'schedule_type': settings[3],
            'preferred_day': settings[4],
            'preferred_time': settings[5]
        }

def save_forum_settings(
        telegram_id: int,
        **kwargs
):
    """Сохраняет настройки форума"""
    current = get_forum_settings(telegram_id)
    new_settings = {
        'forum_enabled': kwargs.get('forum_enabled', current['forum_enabled']),
        'polling_interval': kwargs.get('polling_interval', current['polling_interval']),
        'last_polling_time': kwargs.get('last_polling_time', current['last_polling_time'])
    }
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO forum_settings 
            VALUES (?, ?, ?, ?)
        """, (
            telegram_id,
            new_settings['forum_enabled'],
            new_settings['polling_interval'],
            new_settings['last_polling_time']
        ))
        conn.commit()

def get_forum_settings(telegram_id: int) -> Dict:
    """Возвращает настройки форума"""
    defaults = {
        'forum_enabled': True,
        'polling_interval': 60,
        'last_polling_time': None
    }
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM forum_settings WHERE telegram_id = ?", (telegram_id,))
        settings = c.fetchone()
        if not settings:
            return defaults
        return {
            'forum_enabled': bool(settings[1]),
            'polling_interval': settings[2],
            'last_polling_time': settings[3]
        }

def get_users_with_forum_enabled() -> List[int]:
    """Возвращает список telegram_id пользователей с включенными уведомлениями форума"""
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT telegram_id FROM forum_settings WHERE forum_enabled = 1")
        return [row[0] for row in c.fetchall()]

def logout_user(telegram_id: int):
    """Удаляет данные пользователя"""
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
        c.execute("DELETE FROM notifications WHERE telegram_id = ?", (telegram_id,))
        c.execute("DELETE FROM forum_settings WHERE telegram_id = ?", (telegram_id,))
        conn.commit()

def update_forum_state(user_id: int, discipline_id: int, last_message_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO forum_states 
            (user_id, discipline_id, last_message_id)
            VALUES (?, ?, ?)
        """, (user_id, discipline_id, last_message_id))
        conn.commit()

def get_forum_states(user_id: int) -> Dict[int, int]:
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT discipline_id, last_message_id FROM forum_states WHERE user_id = ?", (user_id,))
        return {row[0]: row[1] for row in c.fetchall()}

def update_user_tokens(telegram_id: int, token_data: Dict):
    """Обновляет токены пользователя"""
    if not get_user_token(telegram_id):
        raise ValueError("User does not exist")
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE users SET
                access_token = ?,
                refresh_token = ?,
                expires_in = ?,
                timestamp = ?
            WHERE telegram_id = ?
        """, (
            token_data['access_token'],
            token_data.get('refresh_token', ''),
            token_data.get('expires_in', 3600),
            int(time.time()),
            telegram_id
        ))
        conn.commit()