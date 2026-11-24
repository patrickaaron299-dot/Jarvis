"""
Authorised tool registry, permission checks, and audit logging for JARVIS.
"""

from __future__ import annotations

import ast
import json
import operator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from backend.config import Settings
from backend.database import get_connection
from backend.logger import logger
from backend.memory import delete_memory, list_memories, save_memory, search_relevant_memories


class UnknownToolError(Exception):
    """Raised when referencing a tool that is not registered."""


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    default_allowed: bool
    handler: Callable[[Settings, int, dict[str, Any]], dict[str, Any]]


_BIN_OPS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_math_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_math_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_math_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left = _eval_math_node(node.left)
        right = _eval_math_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise ValueError("Exponent is too large.")
        return _BIN_OPS[type(node.op)](left, right)
    raise ValueError("Unsupported math expression.")


def _tool_get_current_time(
    settings: Settings,
    user_id: int,
    args: dict[str, Any],
) -> dict[str, Any]:
    tz_name = str(args.get("timezone") or "UTC").strip()
    try:
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        resolved_tz = tz_name
    except Exception:
        now = datetime.now(timezone.utc)
        resolved_tz = "UTC"

    return {
        "timezone": resolved_tz,
        "iso": now.isoformat(),
        "readable": now.strftime("%A, %B %d, %Y %I:%M %p %Z"),
    }


def _tool_calculate(
    settings: Settings,
    user_id: int,
    args: dict[str, Any],
) -> dict[str, Any]:
    expression = str(args.get("expression") or "").strip()
    if not expression or len(expression) > 200:
        raise ValueError("Provide a math expression up to 200 characters.")

    tree = ast.parse(expression, mode="eval")
    value = _eval_math_node(tree)
    formatted = int(value) if value.is_integer() else round(value, 8)
    return {"expression": expression, "result": formatted}


def _tool_save_memory(
    settings: Settings,
    user_id: int,
    args: dict[str, Any],
) -> dict[str, Any]:
    content = str(args.get("content") or "").strip()
    category = str(args.get("category") or "general").strip()
    importance = int(args.get("importance") or 3)
    mem = save_memory(
        settings=settings,
        user_id=user_id,
        content=content,
        category=category,
        importance=importance,
    )
    return {"saved_memory": mem}


def _tool_recall_memories(
    settings: Settings,
    user_id: int,
    args: dict[str, Any],
) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    limit = max(1, min(int(args.get("limit") or 8), 20))
    if query:
        memories = search_relevant_memories(settings, user_id, query, limit=limit)
    else:
        memories = list_memories(settings, user_id, limit=limit)
    return {"memories": memories}


def _tool_delete_memory(
    settings: Settings,
    user_id: int,
    args: dict[str, Any],
) -> dict[str, Any]:
    memory_id = int(args["memory_id"])
    deleted = delete_memory(settings, user_id, memory_id)
    return {"memory_id": memory_id, "deleted": deleted}


_TOOLS: dict[str, ToolDefinition] = {
    "get_current_time": ToolDefinition(
        name="get_current_time",
        description="Get the current date and time, optionally in a specific IANA timezone like 'Asia/Kolkata' or 'UTC'.",
        parameters={
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "Optional IANA timezone name, e.g. 'Asia/Kolkata' or 'UTC'.",
                }
            },
            "required": [],
        },
        default_allowed=True,
        handler=_tool_get_current_time,
    ),
    "calculate": ToolDefinition(
        name="calculate",
        description="Evaluate a safe arithmetic expression (numbers, +, -, *, /, //, %, **, parentheses).",
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "The math expression to compute, e.g. '(1200 * 0.18) + 45'.",
                }
            },
            "required": ["expression"],
        },
        default_allowed=True,
        handler=_tool_calculate,
    ),
    "save_memory": ToolDefinition(
        name="save_memory",
        description="Save an important fact, preference, or reminder about the user into persistent long-term memory.",
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The clear fact or preference to remember.",
                },
                "category": {
                    "type": "string",
                    "description": "Short category like 'preference', 'profile', 'project', or 'reminder'.",
                },
                "importance": {
                    "type": "integer",
                    "description": "Importance from 1 (low) to 5 (critical).",
                },
            },
            "required": ["content"],
        },
        default_allowed=True,
        handler=_tool_save_memory,
    ),
    "recall_memories": ToolDefinition(
        name="recall_memories",
        description="Search the user's persistent long-term memories by topic or keywords.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords or topic to search for.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of memories to return (1-20).",
                },
            },
            "required": [],
        },
        default_allowed=True,
        handler=_tool_recall_memories,
    ),
    "delete_memory": ToolDefinition(
        name="delete_memory",
        description="Permanently delete a saved long-term memory by its numeric ID. Requires explicit user authorisation.",
        parameters={
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "integer",
                    "description": "The numeric ID of the memory to delete.",
                }
            },
            "required": ["memory_id"],
        },
        default_allowed=False,
        handler=_tool_delete_memory,
    ),
}


def is_tool_allowed(settings: Settings, user_id: int, tool_name: str) -> bool:
    """Check whether the user has authorised a given tool."""
    tool = _TOOLS.get(tool_name)
    if tool is None:
        return False

    with get_connection(settings.db_path) as conn:
        row = conn.execute(
            """
            SELECT is_allowed
            FROM tool_permissions
            WHERE user_id = ? AND tool_name = ?
            """,
            (user_id, tool_name),
        ).fetchone()

    if row is None:
        return tool.default_allowed
    return bool(row["is_allowed"])


def set_tool_permission(
    settings: Settings,
    user_id: int,
    tool_name: str,
    is_allowed: bool,
) -> dict[str, Any]:
    """Enable or disable a tool for the user."""
    if tool_name not in _TOOLS:
        raise UnknownToolError(f"Unknown tool: {tool_name}")

    allowed_int = 1 if is_allowed else 0
    with get_connection(settings.db_path) as conn:
        conn.execute(
            """
            INSERT INTO tool_permissions (user_id, tool_name, is_allowed, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(user_id, tool_name) DO UPDATE SET
                is_allowed = excluded.is_allowed,
                updated_at = datetime('now')
            """,
            (user_id, tool_name, allowed_int),
        )

    logger.info(
        "Updated tool permission: user_id=%s tool=%s allowed=%s",
        user_id,
        tool_name,
        bool(allowed_int),
    )
    return {
        "tool_name": tool_name,
        "is_allowed": bool(allowed_int),
    }


def list_user_tools(settings: Settings, user_id: int) -> list[dict[str, Any]]:
    """List all tools and whether each one is currently authorised for the user."""
    with get_connection(settings.db_path) as conn:
        rows = conn.execute(
            "SELECT tool_name, is_allowed FROM tool_permissions WHERE user_id = ?",
            (user_id,),
        ).fetchall()

    overrides = {row["tool_name"]: bool(row["is_allowed"]) for row in rows}
    result = []
    for tool in _TOOLS.values():
        result.append(
            {
                "name": tool.name,
                "description": tool.description,
                "default_allowed": tool.default_allowed,
                "is_allowed": overrides.get(tool.name, tool.default_allowed),
            }
        )
    return result


def get_authorized_openai_tools(settings: Settings, user_id: int) -> list[dict[str, Any]]:
    """Return tool schemas in OpenAI/Fireworks format for authorised tools only."""
    schemas: list[dict[str, Any]] = []
    for tool in _TOOLS.values():
        if is_tool_allowed(settings, user_id, tool.name):
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
    return schemas


def _log_tool_audit(
    settings: Settings,
    user_id: int,
    tool_name: str,
    arguments_json: str,
    status: str,
    result_summary: str,
) -> None:
    with get_connection(settings.db_path) as conn:
        conn.execute(
            """
            INSERT INTO tool_audit_logs (user_id, tool_name, arguments_json, status, result_summary)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, tool_name, arguments_json[:1000], status, result_summary[:500]),
        )


def execute_tool(
    settings: Settings,
    user_id: int,
    tool_name: str,
    arguments: dict[str, Any] | str | None = None,
) -> dict[str, Any]:
    """
    Safely execute an authorised tool and record an audit log entry.
    Returns a JSON-friendly result dictionary.
    """
    if isinstance(arguments, str):
        raw_args = arguments.strip() or "{}"
        try:
            parsed_args = json.loads(raw_args)
            if not isinstance(parsed_args, dict):
                parsed_args = {}
        except json.JSONDecodeError:
            parsed_args = {}
    elif isinstance(arguments, dict):
        parsed_args = arguments
        raw_args = json.dumps(parsed_args)
    else:
        parsed_args = {}
        raw_args = "{}"

    tool = _TOOLS.get(tool_name)
    if tool is None:
        _log_tool_audit(settings, user_id, tool_name, raw_args, "failed", "Unknown tool")
        return {"ok": False, "status": "failed", "error": f"Unknown tool: {tool_name}"}

    if not is_tool_allowed(settings, user_id, tool_name):
        _log_tool_audit(
            settings,
            user_id,
            tool_name,
            raw_args,
            "denied",
            "User has not authorised this tool",
        )
        return {
            "ok": False,
            "status": "denied",
            "error": (
                f"Tool '{tool_name}' is not authorised. "
                "The user can enable it in the Authorised Tools settings."
            ),
        }

    try:
        result = tool.handler(settings, user_id, parsed_args)
        summary = json.dumps(result, default=str)[:500]
        _log_tool_audit(settings, user_id, tool_name, raw_args, "executed", summary)
        return {"ok": True, "status": "executed", "result": result}
    except Exception as exc:
        logger.warning("Tool execution failed (%s): %s", tool_name, exc)
        _log_tool_audit(settings, user_id, tool_name, raw_args, "failed", str(exc))
        return {"ok": False, "status": "failed", "error": str(exc)}


def list_tool_audit_logs(
    settings: Settings,
    user_id: int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return recent tool activity logs for the user."""
    safe_limit = max(1, min(limit, 200))
    with get_connection(settings.db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, tool_name, arguments_json, status, result_summary, created_at
            FROM tool_audit_logs
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, safe_limit),
        ).fetchall()
    return [dict(row) for row in rows]