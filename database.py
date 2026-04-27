import sqlite3
from datetime import datetime, timedelta
from typing import Optional


class Database:
    def __init__(self, db_path: str = "loks.db"):
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id     INTEGER PRIMARY KEY,
                    username    TEXT,
                    first_name  TEXT,
                    last_name   TEXT,
                    created_at  TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS loks (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    receiver_id INTEGER NOT NULL,
                    giver_id    INTEGER NOT NULL,
                    chat_id     INTEGER NOT NULL,
                    given_at    TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_loks_receiver ON loks(receiver_id);
                CREATE INDEX IF NOT EXISTS idx_loks_given_at ON loks(given_at);
                CREATE INDEX IF NOT EXISTS idx_loks_chat     ON loks(chat_id);
            """)

    def ensure_user(self, user_id: int, username: Optional[str], first_name: Optional[str], last_name: Optional[str]):
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username   = excluded.username,
                    first_name = excluded.first_name,
                    last_name  = excluded.last_name
                """,
                (user_id, username, first_name, last_name),
            )
            if username:
                conn.execute(
                    """
                    UPDATE loks SET receiver_id = ?
                    WHERE receiver_id IN (
                        SELECT user_id FROM users
                        WHERE username = ? COLLATE NOCASE AND user_id != ?
                    )
                    """,
                    (user_id, username, user_id),
                )
                conn.execute(
                    "DELETE FROM users WHERE username = ? COLLATE NOCASE AND user_id != ?",
                    (username, user_id),
                )

    def get_or_create_user_by_username(self, username: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
                (username,),
            ).fetchone()
            if row:
                return dict(row)

            temp_id = -(abs(hash(username)) % 10**9)
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                (temp_id, username, username),
            )
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
                (username,),
            ).fetchone()
            return dict(row) if row else None

    def add_lok(self, receiver_id: int, giver_id: int, chat_id: int):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO loks (receiver_id, giver_id, chat_id) VALUES (?, ?, ?)",
                (receiver_id, giver_id, chat_id),
            )

    def remove_lok(self, receiver_id: int):
        with self._conn() as conn:
            conn.execute(
                """
                DELETE FROM loks WHERE id = (
                    SELECT id FROM loks WHERE receiver_id = ?
                    ORDER BY given_at DESC LIMIT 1
                )
                """,
                (receiver_id,),
            )

    def get_total_loks(self, user_id: int) -> int:
        with self._conn() as conn:
            username_row = conn.execute(
                "SELECT username FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()

            if username_row and username_row["username"]:
                temp_id = -(abs(hash(username_row["username"])) % 10**9)
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM loks WHERE receiver_id = ? OR receiver_id = ?",
                    (user_id, temp_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM loks WHERE receiver_id = ?",
                    (user_id,),
                ).fetchone()

            return row["cnt"] if row else 0

    def get_top(self, days: Optional[int] = None, limit: int = 10) -> list[dict]:
        since_clause = ""
        params: list = []

        if days is not None:
            since = (datetime.utcnow() - timedelta(days=days)).isoformat()
            since_clause = "WHERE l.given_at >= ?"
            params.append(since)

        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    u.user_id,
                    u.username,
                    u.first_name,
                    u.last_name,
                    COUNT(l.id) AS lok_count
                FROM loks l
                JOIN users u ON u.user_id = l.receiver_id
                {since_clause}
                GROUP BY l.receiver_id
                ORDER BY lok_count DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [dict(r) for r in rows]
