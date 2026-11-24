"""
Persistent memory and conversation history management for the JARVIS backend.
"""

from __future__ import annotations

import re
from typing import Any

from backend.config import Settings
from backend.database import get_connection
from backend.logger import logger

_WORD_PATTERN = re.compile(r"[a-zA-Z0-9_]{3,}")
_STOPWORDS = {
    "the",
    "and",
    "for",
    "are",
    "but",
    "not",
    "you",
    "your",
    "with",
    "that",
    "this",
    "from",
    "have",
    "has",
    "had",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "how",
    "can",
    "could",
    "would",
    "should",
    "will",
    "about",
    "please",
    "jarvis",
}
_VALID_ROLES = {"system", "user", "assistant", "tool"}


class MemoryNotFoundError(Exception):
    """Raised when a requested conversation or memory does not exist."""


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def _extract_keywords(text: str) -> set[str]:
    words = {w.lower() for w in _WORD_PATTERN.findall(text)}
    return {w for w in words if w not in _STOPWORDS}


def create_conversation(
    settings: Settings,
    user_id: int,
    title: str = "New Conversation",
) -> dict[str, Any]:
    """Create a new conversation belonging to the user."""
    clean_title = (title or "New Conversation").strip()[:80] or "New Conversation"
    with get_connection(settings.db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO conversations (user_id, title) VALUES (?, ?)",
            (user_id, clean_title),
        )
        conv_id = int(cursor.lastrowid)
        row = conn.execute(
            "SELECT id, user_id, title, created_at, updated_at FROM conversations WHERE id = ?",
            (conv_id,),
        ).fetchone()
    return _row_to_dict(row)


def get_conversation(
    settings: Settings,
    user_id: int,
    conversation_id: int,
) -> dict[str, Any]:
    """Fetch a single conversation if owned by the user."""
    with get_connection(settings.db_path) as conn:
        row = conn.execute(
            """
            SELECT id, user_id, title, created_at, updated_at
            FROM conversations
            WHERE id = ? AND user_id = ?
            """,
            (conversation_id, user_id),
        ).fetchone()

    if row is None:
        raise MemoryNotFoundError("Conversation not found.")
    return _row_to_dict(row)


def get_or_create_conversation(
    settings: Settings,
    user_id: int,
    conversation_id: int | None = None,
) -> dict[str, Any]:
    """Return the requested conversation or create a new one if none was supplied."""
    if conversation_id is not None:
        return get_conversation(settings, user_id, conversation_id)
    return create_conversation(settings, user_id)


def list_conversations(
    settings: Settings,
    user_id: int,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """List the user's most recently updated conversations."""
    safe_limit = max(1, min(limit, 100))
    with get_connection(settings.db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, title, created_at, updated_at
            FROM conversations
            WHERE user_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, safe_limit),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def delete_conversation(
    settings: Settings,
    user_id: int,
    conversation_id: int,
) -> bool:
    """Delete a conversation and all its messages (owned by the user)."""
    with get_connection(settings.db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        )
    return cursor.rowcount > 0


def add_message(
    settings: Settings,
    user_id: int,
    conversation_id: int,
    role: str,
    content: str,
    tool_name: str | None = None,
) -> dict[str, Any]:
    """Save a message into a conversation owned by the user."""
    if role not in _VALID_ROLES:
        raise ValueError(f"Invalid message role: {role}")

    clean_content = content.strip()
    if not clean_content:
        raise ValueError("Message content cannot be empty.")

    with get_connection(settings.db_path) as conn:
        conv = conn.execute(
            "SELECT id, title FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).fetchone()
        if conv is None:
            raise MemoryNotFoundError("Conversation not found.")

        cursor = conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content, tool_name)
            VALUES (?, ?, ?, ?)
            """,
            (conversation_id, role, clean_content, tool_name),
        )
        msg_id = int(cursor.lastrowid)

        if role == "user" and conv["title"] == "New Conversation":
            snippet = clean_content.replace("\n", " ")[:50]
            if len(clean_content) > 50:
                snippet += "..."
            conn.execute(
                """
                UPDATE conversations
                SET title = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (snippet, conversation_id),
            )
        else:
            conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (conversation_id,),
            )

        row = conn.execute(
            """
            SELECT id, conversation_id, role, content, tool_name, created_at
            FROM messages
            WHERE id = ?
            """,
            (msg_id,),
        ).fetchone()

    return _row_to_dict(row)


def get_recent_messages(
    settings: Settings,
    user_id: int,
    conversation_id: int,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Fetch recent messages for a conversation in chronological order."""
    safe_limit = max(1, min(limit, 100))
    with get_connection(settings.db_path) as conn:
        conv = conn.execute(
            "SELECT id FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).fetchone()
        if conv is None:
            raise MemoryNotFoundError("Conversation not found.")

        rows = conn.execute(
            """
            SELECT id, conversation_id, role, content, tool_name, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (conversation_id, safe_limit),
        ).fetchall()

    return [_row_to_dict(r) for r in reversed(rows)]


def save_memory(
    settings: Settings,
    user_id: int,
    content: str,
    category: str = "general",
    importance: int = 3,
) -> dict[str, Any]:
    """
    Store a long-term memory for the user.
    If the exact same memory already exists, update it instead of duplicating.
    """
    clean_content = content.strip()
    if not clean_content:
        raise ValueError("Memory content cannot be empty.")

    clean_category = (category or "general").strip().lower()[:40] or "general"
    clamped_importance = max(1, min(5, int(importance)))

    with get_connection(settings.db_path) as conn:
        existing = conn.execute(
            """
            SELECT id, importance
            FROM memories
            WHERE user_id = ? AND LOWER(TRIM(content)) = LOWER(?)
            """,
            (user_id, clean_content),
        ).fetchone()

        if existing is not None:
            new_importance = max(int(existing["importance"]), clamped_importance)
            conn.execute(
                """
                UPDATE memories
                SET category = ?, importance = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (clean_category, new_importance, int(existing["id"])),
            )
            row = conn.execute(
                """
                SELECT id, user_id, category, content, importance, created_at, updated_at
                FROM memories
                WHERE id = ?
                """,
                (int(existing["id"]),),
            ).fetchone()
            logger.info("Updated existing memory id=%s for user_id=%s", existing["id"], user_id)
            return _row_to_dict(row)

        cursor = conn.execute(
            """
            INSERT INTO memories (user_id, category, content, importance)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, clean_category, clean_content, clamped_importance),
        )
        mem_id = int(cursor.lastrowid)
        row = conn.execute(
            """
            SELECT id, user_id, category, content, importance, created_at, updated_at
            FROM memories
            WHERE id = ?
            """,
            (mem_id,),
        ).fetchone()

    logger.info("Saved new memory id=%s for user_id=%s", mem_id, user_id)
    return _row_to_dict(row)


def list_memories(
    settings: Settings,
    user_id: int,
    category: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List saved long-term memories for the user."""
    safe_limit = max(1, min(limit, 500))
    with get_connection(settings.db_path) as conn:
        if category:
            rows = conn.execute(
                """
                SELECT id, user_id, category, content, importance, created_at, updated_at
                FROM memories
                WHERE user_id = ? AND category = ?
                ORDER BY importance DESC, updated_at DESC, id DESC
                LIMIT ?
                """,
                (user_id, category.strip().lower(), safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, user_id, category, content, importance, created_at, updated_at
                FROM memories
                WHERE user_id = ?
                ORDER BY importance DESC, updated_at DESC, id DESC
                LIMIT ?
                """,
                (user_id, safe_limit),
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def delete_memory(settings: Settings, user_id: int, memory_id: int) -> bool:
    """Delete a memory owned by the user."""
    with get_connection(settings.db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM memories WHERE id = ? AND user_id = ?",
            (memory_id, user_id),
        )
    return cursor.rowcount > 0


def search_relevant_memories(
    settings: Settings,
    user_id: int,
    query: str,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """
    Find the most relevant long-term memories for the user's current message.
    Combines keyword matching with memory importance so core facts are always recalled.
    """
    all_memories = list_memories(settings, user_id, limit=300)
    if not all_memories:
        return []

    query_keywords = _extract_keywords(query)
    scored: list[tuple[float, dict[str, Any]]] = []

    for mem in all_memories:
        mem_words = _extract_keywords(f"{mem['category']} {mem['content']}")
        overlap = len(query_keywords & mem_words) if query_keywords else 0
        importance_score = float(mem["importance"]) * 0.5
        total_score = (overlap * 3.0) + importance_score
        scored.append((total_score, mem))

    scored.sort(key=lambda item: (item[0], item[1]["id"]), reverse=True)
    return [mem for _, mem in scored[: max(1, limit)]]


def format_memories_for_prompt(memories: list[dict[str, Any]]) -> str:
    """Format recalled memories cleanly for inclusion in the AI system prompt."""
    if not memories:
        return "No saved long-term memories yet."

    lines = [
        f"- [{mem['category']}] (importance {mem['importance']}/5): {mem['content']}"
        for mem in memories
    ]
    return "\n".join(lines)