"""
FastAPI server entry point for the JARVIS online backend.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from backend.auth import (
    AuthError,
    InvalidCredentialsError,
    InvalidTokenError,
    RegistrationDisabledError,
    UserAlreadyExistsError,
    authenticate_user,
    get_user_by_id,
    register_user,
    verify_access_token,
)
from backend.config import Settings
from backend.database import init_db
from backend.llm_client import LLMConfigError, LLMError, chat_with_jarvis
from backend.logger import logger
from backend.memory import (
    MemoryNotFoundError,
    delete_conversation,
    delete_memory,
    get_recent_messages,
    list_conversations,
    list_memories,
    save_memory,
)
from backend.tools import (
    UnknownToolError,
    list_tool_audit_logs,
    list_user_tools,
    set_tool_permission,
)

_bearer_scheme = HTTPBearer(auto_error=False)


class _SecretRedactingFilter(logging.Filter):
    """Mask configured secret values before any log record is written."""

    def __init__(self, secrets_to_mask: list[str]) -> None:
        super().__init__()
        self._secrets = [s for s in secrets_to_mask if s]

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secrets:
            return True
        rendered = record.getMessage()
        changed = False
        for secret in self._secrets:
            if secret in rendered:
                rendered = rendered.replace(secret, "[REDACTED]")
                changed = True
        if changed:
            record.msg = rendered
            record.args = ()
        return True


def _configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level, logging.INFO)
    logger.setLevel(level)

    logger.filters = [f for f in logger.filters if not isinstance(f, _SecretRedactingFilter)]
    redactor = _SecretRedactingFilter(settings.registered_secrets())
    logger.addFilter(redactor)
    for handler in logger.handlers:
        handler.filters = [f for f in handler.filters if not isinstance(f, _SecretRedactingFilter)]
        handler.addFilter(redactor)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    conversation_id: int | None = None


class CreateMemoryRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    category: str = Field(default="general", min_length=1, max_length=40)
    importance: int = Field(default=3, ge=1, le=5)


class ToolPermissionRequest(BaseModel):
    is_allowed: bool


def create_app(custom_settings: Settings | None = None) -> FastAPI:
    settings = custom_settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        _configure_logging(settings)
        init_db(settings.db_path)
        if settings.ephemeral_auth_secret:
            logger.warning(
                "JARVIS_AUTH_SECRET is not set; using an ephemeral secret. "
                "Existing logins will reset if the server restarts."
            )
        logger.info("JARVIS backend started (provider=%s)", settings.default_provider)
        yield
        logger.info("JARVIS backend shutting down")

    app = FastAPI(
        title="JARVIS Personal AI Backend",
        version="1.0.0",
        lifespan=lifespan,
    )

    allow_all_origins = settings.allowed_origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins or ["*"],
        allow_credentials=not allow_all_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    ) -> dict[str, Any]:
        if credentials is None or not credentials.credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
            )
        try:
            payload = verify_access_token(credentials.credentials, settings.auth_secret)
        except InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            ) from exc

        user = get_user_by_id(settings, int(payload["sub"]))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account no longer exists.",
            )
        return user

    @app.get("/health")
    def health_check() -> dict[str, Any]:
        active_model = (
            settings.fireworks_model
            if settings.default_provider == "fireworks"
            else settings.openai_model
        )
        return {
            "status": "online",
            "service": "jarvis-backend",
            "provider": settings.default_provider,
            "model": active_model,
            "registration_open": settings.allow_registration,
        }

    @app.post("/auth/register", status_code=status.HTTP_201_CREATED)
    def auth_register(body: RegisterRequest) -> dict[str, Any]:
        try:
            return register_user(settings, body.username, body.password)
        except RegistrationDisabledError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        except UserAlreadyExistsError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except AuthError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.post("/auth/login")
    def auth_login(body: LoginRequest) -> dict[str, Any]:
        try:
            return authenticate_user(settings, body.username, body.password)
        except InvalidCredentialsError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    @app.get("/auth/me")
    def auth_me(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        return {"user": current_user}

    @app.post("/chat")
    def chat(
        body: ChatRequest,
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        try:
            return chat_with_jarvis(
                settings=settings,
                user_id=int(current_user["id"]),
                username=current_user["username"],
                user_message=body.message,
                conversation_id=body.conversation_id,
            )
        except MemoryNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except LLMConfigError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        except LLMError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    @app.get("/conversations")
    def get_conversations(
        limit: int = Query(default=30, ge=1, le=100),
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        items = list_conversations(settings, int(current_user["id"]), limit=limit)
        return {"conversations": items}

    @app.get("/conversations/{conversation_id}/messages")
    def get_conversation_messages(
        conversation_id: int,
        limit: int = Query(default=50, ge=1, le=100),
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        try:
            items = get_recent_messages(
                settings,
                int(current_user["id"]),
                conversation_id,
                limit=limit,
            )
            return {"conversation_id": conversation_id, "messages": items}
        except MemoryNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.delete("/conversations/{conversation_id}")
    def remove_conversation(
        conversation_id: int,
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        deleted = delete_conversation(settings, int(current_user["id"]), conversation_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
        return {"deleted": True, "conversation_id": conversation_id}

    @app.get("/memories")
    def get_memories(
        category: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        items = list_memories(
            settings,
            int(current_user["id"]),
            category=category,
            limit=limit,
        )
        return {"memories": items}

    @app.post("/memories", status_code=status.HTTP_201_CREATED)
    def create_memory(
        body: CreateMemoryRequest,
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        try:
            item = save_memory(
                settings=settings,
                user_id=int(current_user["id"]),
                content=body.content,
                category=body.category,
                importance=body.importance,
            )
            return {"memory": item}
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.delete("/memories/{memory_id}")
    def remove_memory(
        memory_id: int,
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        deleted = delete_memory(settings, int(current_user["id"]), memory_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found.")
        return {"deleted": True, "memory_id": memory_id}

    @app.get("/tools")
    def get_tools(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        items = list_user_tools(settings, int(current_user["id"]))
        return {"tools": items}

    @app.put("/tools/{tool_name}")
    def update_tool_permission(
        tool_name: str,
        body: ToolPermissionRequest,
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        try:
            return set_tool_permission(
                settings=settings,
                user_id=int(current_user["id"]),
                tool_name=tool_name,
                is_allowed=body.is_allowed,
            )
        except UnknownToolError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.get("/tools/logs")
    def get_tool_logs(
        limit: int = Query(default=50, ge=1, le=200),
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        logs = list_tool_audit_logs(settings, int(current_user["id"]), limit=limit)
        return {"logs": logs}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)