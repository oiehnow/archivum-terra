"""계정당 일일 질문 수 제한.

무료 제공이므로 남용을 막아야 한다. Gemini 무료 티어가 1,500 요청/일이라
계정당 20질문이면 하루 75명까지 감당한다.

HF Space 는 재시작하면 파일이 사라진다. 쿼터가 초기화되어도 서비스는 계속 돌아가야
하므로 치명적이지 않지만, 영속 볼륨이 있으면 그쪽에 둔다.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("QUOTA_DB", "/data/quota.sqlite3"))
DAILY_QUOTA = int(os.getenv("DAILY_QUESTION_QUOTA", "20"))

KST = timezone(timedelta(hours=9))

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                sub        TEXT PRIMARY KEY,
                email      TEXT,
                name       TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS usage (
                sub   TEXT NOT NULL,
                day   TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (sub, day)
            );
            """
        )
        _conn.commit()
    return _conn


def _today() -> str:
    """자정(KST) 기준 날짜."""
    return datetime.now(KST).strftime("%Y-%m-%d")


def seconds_until_reset() -> int:
    now = datetime.now(KST)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((tomorrow - now).total_seconds())


def ensure_user(sub: str, email: str | None, name: str | None) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT OR IGNORE INTO users (sub, email, name, created_at) VALUES (?, ?, ?, ?)",
            (sub, email, name, datetime.now(KST).isoformat()),
        )
        conn.commit()


def remaining(sub: str) -> int:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT count FROM usage WHERE sub = ? AND day = ?", (sub, _today())
        ).fetchone()
    used = row[0] if row else 0
    return max(0, DAILY_QUOTA - used)


def consume(sub: str) -> int:
    """질문 1건을 차감하고 남은 수를 돌려준다. 한도를 넘으면 -1."""
    with _lock:
        conn = _connect()
        day = _today()
        row = conn.execute(
            "SELECT count FROM usage WHERE sub = ? AND day = ?", (sub, day)
        ).fetchone()
        used = row[0] if row else 0

        if used >= DAILY_QUOTA:
            return -1

        conn.execute(
            "INSERT INTO usage (sub, day, count) VALUES (?, ?, 1) "
            "ON CONFLICT(sub, day) DO UPDATE SET count = count + 1",
            (sub, day),
        )
        conn.commit()
    return DAILY_QUOTA - (used + 1)
