"""
SQLite database setup and connection helper for the JARVIS backend.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from backend.logger import logger


def _prepare_db_path(db_path: str | Path) -> str:
    """Ensure the parent folder for the SQLite file exists."""
    raw_path = str(db_path)
    if raw_path == ":memory:":
        return raw_path

    resolved = Path(raw_path).expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return str(resolved)


@contextmanager
def get_connection(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """
    Open a SQLite connection, commit automatically if everything succeeds,
    roll back on error, and always close the connection.
    """
    target = _prepare_db_path(db_path)
    conn = sqlite3.connect(target, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        if target != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str | Path) -> None:
    """
    Create all required JARVIS tables if they do not exist yet.
    Safe to run every time the server starts.
    """
    with get_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT 'New Conversation',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
                content TEXT NOT NULL,
                tool_name TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                content TEXT NOT NULL,
                importance INTEGER NOT NULL DEFAULT 1 CHECK (importance BETWEEN 1 AND 5),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tool_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                tool_name TEXT NOT NULL,
                is_allowed INTEGER NOT NULL DEFAULT 0 CHECK (is_allowed IN (0, 1)),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE (user_id, tool_name),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tool_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                tool_name TEXT NOT NULL,
                arguments_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL CHECK (status IN ('allowed', 'denied', 'executed', 'failed')),
                result_summary TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_conversations_user
                ON conversations(user_id);

            CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_id);

            CREATE INDEX IF NOT EXISTS idx_memories_user
                ON memories(user_id);

            CREATE INDEX IF NOT EXISTS idx_tool_audit_user
                ON tool_audit_logs(user_id);
            """
        )

    logger.info("Database initialized successfully at %s", db_path)