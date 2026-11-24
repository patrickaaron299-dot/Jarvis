"""
Fireworks AI (Kimi K2) and OpenAI-compatible LLM client with memory and tool calling.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from backend.config import Settings
from backend.logger import logger
from backend.memory import (
    add_message,
    format_memories_for_prompt,
    get_or_create_conversation,
    get_recent_messages,
    search_relevant_memories,
)
from backend.tools import execute_tool, get_authorized_openai_tools

_FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"
_DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
_MAX_TOOL_ROUNDS = 5


class LLMError(Exception):
    """Base error raised when calling the AI model."""


class LLMConfigError(LLMError):
    """Raised when no usable AI API key is configured."""


def _resolve_provider(settings: Settings) -> tuple[str, str, str, str]:
    """
    Pick the active provider based on Settings.
    Returns (provider_name, base_url, api_key, model).
    """
    preferred = (settings.default_provider or "fireworks").lower()

    if preferred == "fireworks":
        if settings.fireworks_api_key:
            return (
                "fireworks",
                _FIREWORKS_BASE_URL,
                settings.fireworks_api_key,
                settings.fireworks_model,
            )
        if settings.openai_api_key:
            return (
                "openai",
                (settings.openai_base_url or _DEFAULT_OPENAI_BASE_URL).rstrip("/"),
                settings.openai_api_key,
                settings.openai_model,
            )
    else:
        if settings.openai_api_key:
            return (
                "openai",
                (settings.openai_base_url or _DEFAULT_OPENAI_BASE_URL).rstrip("/"),
                settings.openai_api_key,
                settings.openai_model,
            )
        if settings.fireworks_api_key:
            return (
                "fireworks",
                _FIREWORKS_BASE_URL,
                settings.fireworks_api_key,
                settings.fireworks_model,
            )

    raise LLMConfigError(
        "No AI API key configured. Set FIREWORKS_API_KEY (or OPENAI_API_KEY) on the server."
    )


def _build_system_prompt(username: str, memories_text: str) -> str:
    return (
        "You are JARVIS, a helpful, intelligent, and concise personal AI assistant "
        f"assisting {username} on their Android phone.\n"
        "Guidelines:\n"
        "- Speak naturally and clearly, since your replies may be read aloud via text-to-speech.\n"
        "- Be accurate and honest. Never pretend to run a tool or know something you did not verify.\n"
        "- You have persistent long-term memory. When the user shares important personal facts, "
        "preferences, or reminders, use the save_memory tool if it is available.\n"
        "- Only use authorised tools provided to you. If an action is denied, politely inform the "
        "user that they can enable that tool in Authorised Tools settings.\n\n"
        "Relevant Persistent Memories for this user:\n"
        f"{memories_text}"
    )


def _call_chat_completions(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.3,
) -> dict[str, Any]:
    """Send a synchronous POST request to an OpenAI-compatible /chat/completions endpoint."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        detail = exc.response.text[:300]
        logger.error("LLM HTTP error %s from %s: %s", status, base_url, detail)
        raise LLMError(f"AI provider returned HTTP {status}.") from exc
    except httpx.RequestError as exc:
        logger.error("Network error calling %s: %s", base_url, exc)
        raise LLMError("Could not reach the AI provider. Please try again.") from exc


def chat_with_jarvis(
    settings: Settings,
    user_id: int,
    username: str,
    user_message: str,
    conversation_id: int | None = None,
) -> dict[str, Any]:
    """
    Process a user message with persistent memory and authorised tool calling,
    then persist and return JARVIS's response.
    """
    clean_message = user_message.strip()
    if not clean_message:
        raise ValueError("Message cannot be empty.")

    provider_name, base_url, api_key, model_name = _resolve_provider(settings)

    conversation = get_or_create_conversation(settings, user_id, conversation_id)
    conv_id = int(conversation["id"])

    add_message(
        settings=settings,
        user_id=user_id,
        conversation_id=conv_id,
        role="user",
        content=clean_message,
    )

    relevant_memories = search_relevant_memories(
        settings=settings,
        user_id=user_id,
        query=clean_message,
        limit=8,
    )
    memories_text = format_memories_for_prompt(relevant_memories)

    history = get_recent_messages(
        settings=settings,
        user_id=user_id,
        conversation_id=conv_id,
        limit=20,
    )

    working_messages: list[dict[str, Any]] = [
        {"role": "system", "content": _build_system_prompt(username, memories_text)}
    ]
    for msg in history:
        if msg["role"] in {"user", "assistant"}:
            working_messages.append({"role": msg["role"], "content": msg["content"]})

    authorized_tools = get_authorized_openai_tools(settings, user_id)
    tools_used: list[dict[str, Any]] = []
    final_reply = ""

    for round_idx in range(_MAX_TOOL_ROUNDS):
        allow_tools = authorized_tools if round_idx < _MAX_TOOL_ROUNDS - 1 else None
        data = _call_chat_completions(
            base_url=base_url,
            api_key=api_key,
            model=model_name,
            messages=working_messages,
            tools=allow_tools,
            temperature=0.2 if allow_tools else 0.4,
        )

        choices = data.get("choices") or []
        if not choices:
            raise LLMError("AI provider returned an empty response.")

        assistant_msg = choices[0].get("message") or {}
        tool_calls = assistant_msg.get("tool_calls") or []

        if not tool_calls:
            final_reply = (assistant_msg.get("content") or "").strip()
            break

        working_messages.append(
            {
                "role": "assistant",
                "content": assistant_msg.get("content") or "",
                "tool_calls": tool_calls,
            }
        )

        for call in tool_calls:
            call_id = call.get("id") or "tool_call"
            func = call.get("function") or {}
            tool_name = str(func.get("name") or "")
            raw_args = func.get("arguments") or "{}"

            outcome = execute_tool(
                settings=settings,
                user_id=user_id,
                tool_name=tool_name,
                arguments=raw_args,
            )
            tools_used.append(
                {
                    "tool_name": tool_name,
                    "status": outcome.get("status", "unknown"),
                }
            )
            working_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(outcome, default=str),
                }
            )

    if not final_reply:
        final_reply = "I completed the requested actions, though I have nothing further to add."

    saved_assistant_msg = add_message(
        settings=settings,
        user_id=user_id,
        conversation_id=conv_id,
        role="assistant",
        content=final_reply,
    )

    return {
        "conversation_id": conv_id,
        "message_id": saved_assistant_msg["id"],
        "reply": final_reply,
        "provider": provider_name,
        "model": model_name,
        "tools_used": tools_used,
        "memories_used_count": len(relevant_memories),
    }