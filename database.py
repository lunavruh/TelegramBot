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
                    reason      TEXT,
                    type        TEXT NOT NULL DEFAULT 'plus',
                    given_at    TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_loks_receiver ON loks(receiver_id);
                CREATE INDEX IF NOT EXISTS idx_loks_given_at ON loks(given_at);
                CREATE INDEX IF NOT EXISTS idx_loks_chat     ON loks(chat_id);

                CREATE TABLE IF NOT EXISTS whitelist (
                    user_id     INTEGER PRIMARY KEY,
                    username    TEXT,
                    added_at    TEXT DEFAULT (datetime('now'))
                );
            """)
            try:
                conn.execute("ALTER TABLE loks ADD COLUMN reason TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE loks ADD COLUMN type TEXT NOT NULL DEFAULT 'plus'")
            except Exception:
                pass

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

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None

    def add_lok(self, receiver_id: int, giver_id: int, chat_id: int, reason: Optional[str] = None):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO loks (receiver_id, giver_id, chat_id, reason, type) VALUES (?, ?, ?, ?, 'plus')",
                (receiver_id, giver_id, chat_id, reason),
            )

    def remove_lok(self, receiver_id: int, reason: Optional[str] = None):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT giver_id, chat_id FROM loks WHERE receiver_id = ? AND type = 'plus' ORDER BY given_at DESC LIMIT 1",
                (receiver_id,),
            ).fetchone()
            if row:
                conn.execute(
                    "INSERT INTO loks (receiver_id, giver_id, chat_id, reason, type) VALUES (?, ?, ?, ?, 'minus')",
                    (receiver_id, row["giver_id"], row["chat_id"], reason),
                )

    def get_total_loks(self, user_id: int) -> int:
        with self._conn() as conn:
            username_row = conn.execute(
                "SELECT username FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()

            if username_row and username_row["username"]:
                temp_id = -(abs(hash(username_row["username"])) % 10**9)
                ids = (user_id, temp_id)
                plus = conn.execute(
                    "SELECT COUNT(*) as cnt FROM loks WHERE receiver_id IN (?, ?) AND type = 'plus'", ids
                ).fetchone()["cnt"]
                minus = conn.execute(
                    "SELECT COUNT(*) as cnt FROM loks WHERE receiver_id IN (?, ?) AND type = 'minus'", ids
                ).fetchone()["cnt"]
            else:
                plus = conn.execute(
                    "SELECT COUNT(*) as cnt FROM loks WHERE receiver_id = ? AND type = 'plus'", (user_id,)
                ).fetchone()["cnt"]
                minus = conn.execute(
                    "SELECT COUNT(*) as cnt FROM loks WHERE receiver_id = ? AND type = 'minus'", (user_id,)
                ).fetchone()["cnt"]

            return max(0, plus - minus)

    def get_history(self, user_id: int, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            username_row = conn.execute(
                "SELECT username FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()

            if username_row and username_row["username"]:
                temp_id = -(abs(hash(username_row["username"])) % 10**9)
                rows = conn.execute(
                    """
                    SELECT type, reason, given_at FROM loks
                    WHERE receiver_id IN (?, ?)
                    ORDER BY given_at DESC LIMIT ?
                    """,
                    (user_id, temp_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT type, reason, given_at FROM loks
                    WHERE receiver_id = ?
                    ORDER BY given_at DESC LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()

            return [dict(r) for r in rows]

    def get_top(self, days: Optional[int] = None, limit: int = 10) -> list[dict]:
        since_clause = ""
        params: list = []

        if days is not None:
            since = (datetime.utcnow() - timedelta(days=days)).isoformat()
            since_clause = "AND l.given_at >= ?"
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
                    SUM(CASE WHEN l.type = 'plus' THEN 1 ELSE -1 END) AS lok_count
                FROM loks l
                JOIN users u ON u.user_id = l.receiver_id
                WHERE 1=1 {since_clause}
                GROUP BY l.receiver_id
                HAVING lok_count > 0
                ORDER BY lok_count DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [dict(r) for r in rows]

    # --- Whitelist ---

    def whitelist_add(self, user_id: int, username: Optional[str]) -> bool:
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT 1 FROM whitelist WHERE user_id = ?", (user_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE whitelist SET username = ? WHERE user_id = ?",
                    (username, user_id),
                )
                return False
            conn.execute(
                "INSERT INTO whitelist (user_id, username) VALUES (?, ?)",
                (user_id, username),
            )
            return True

    def whitelist_remove(self, user_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM whitelist WHERE user_id = ?", (user_id,))
            return cur.rowcount > 0

    def whitelist_remove_by_username(self, username: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM whitelist WHERE username = ? COLLATE NOCASE", (username,)
            )
            return cur.rowcount > 0

    def whitelist_check(self, user_id: int) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM whitelist WHERE user_id = ?", (user_id,)
            ).fetchone()
            return row is not None

    def whitelist_get_all(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT user_id, username, added_at FROM whitelist ORDER BY added_at"
            ).fetchall()
            return [dict(r) for r in rows]

    def whitelist_get_by_username(self, username: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT user_id, username FROM whitelist WHERE username = ? COLLATE NOCASE",
                (username,),
            ).fetchone()
            return dict(row) if row else None
