"""LLM gateway: provider selection + observability logging to ``llm_calls``.

All application code calls the gateway, never a provider directly.
Pass the caller's session so the llm_calls row commits atomically with the
agent_run it references; without a session a standalone transaction is used.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from lumi.config import Settings, get_settings
from lumi.db.models import LLMCall
from lumi.db.session import session_scope
from lumi.llm.base import LLMError, LLMMessage, LLMProvider, LLMResponse, LLMTimeoutError
from lumi.llm.minimax import MiniMaxProvider
from lumi.llm.mock import MockLLMProvider
from lumi.logging import get_logger

log = get_logger(__name__)

_provider: LLMProvider | None = None


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    global _provider
    if _provider is None:
        settings = settings or get_settings()
        if settings.llm_provider == "minimax" and settings.minimax_api_key:
            _provider = MiniMaxProvider(
                api_key=settings.minimax_api_key,
                base_url=settings.minimax_base_url,
                model=settings.minimax_model,
                timeout_seconds=settings.llm_timeout_seconds,
                max_retries=settings.llm_max_retries,
            )
        else:
            if settings.llm_provider == "minimax":
                log.warning("MINIMAX_API_KEY is not set — falling back to mock LLM provider")
            _provider = MockLLMProvider()
    return _provider


def reset_llm_provider() -> None:  # for tests
    global _provider
    _provider = None


class LLMGateway:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or get_llm_provider()

    async def complete(
        self,
        *,
        messages: list[LLMMessage],
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        request_kind: str,
        user_id: uuid.UUID | None = None,
        agent_run_id: uuid.UUID | None = None,
        session: AsyncSession | None = None,
    ) -> LLMResponse:
        started = time.monotonic()
        try:
            response = await self.provider.complete(
                messages=messages,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                request_kind=request_kind,
            )
        except LLMError as exc:
            await self._log_call(
                session=session,
                request_kind=request_kind,
                status="timeout" if isinstance(exc, LLMTimeoutError) else "error",
                user_id=user_id,
                agent_run_id=agent_run_id,
                latency_ms=int((time.monotonic() - started) * 1000),
                input_chars=sum(len(m.content) for m in messages) + len(system or ""),
                error_message=str(exc)[:1000],
            )
            raise
        await self._log_call(
            session=session,
            request_kind=request_kind,
            status="success",
            user_id=user_id,
            agent_run_id=agent_run_id,
            latency_ms=response.latency_ms,
            input_chars=response.input_chars,
            output_chars=response.output_chars,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            request_hash=self._hash_messages(messages, system),
        )
        return response

    async def complete_stream(
        self,
        *,
        messages: list[LLMMessage],
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        request_kind: str,
        user_id: uuid.UUID | None = None,
        agent_run_id: uuid.UUID | None = None,
        session: AsyncSession | None = None,
        on_delta=None,
        on_thinking=None,
    ) -> LLMResponse:
        """Streaming completion with llm_calls logging. Providers without
        streaming support fall back to a regular complete()."""
        stream_fn = getattr(self.provider, "complete_stream", None)
        if stream_fn is None:
            return await self.complete(
                messages=messages, system=system, temperature=temperature,
                max_tokens=max_tokens, request_kind=request_kind,
                user_id=user_id, agent_run_id=agent_run_id, session=session,
            )
        started = time.monotonic()
        try:
            response = await stream_fn(
                messages=messages, system=system, temperature=temperature,
                max_tokens=max_tokens, request_kind=request_kind,
                on_delta=on_delta, on_thinking=on_thinking,
            )
        except LLMError as exc:
            await self._log_call(
                session=session,
                request_kind=request_kind,
                status="timeout" if isinstance(exc, LLMTimeoutError) else "error",
                user_id=user_id,
                agent_run_id=agent_run_id,
                latency_ms=int((time.monotonic() - started) * 1000),
                input_chars=sum(len(m.content) for m in messages) + len(system or ""),
                error_message=str(exc)[:1000],
            )
            raise
        await self._log_call(
            session=session,
            request_kind=request_kind,
            status="success",
            user_id=user_id,
            agent_run_id=agent_run_id,
            latency_ms=response.latency_ms,
            input_chars=response.input_chars,
            output_chars=response.output_chars,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            request_hash=self._hash_messages(messages, system),
        )
        return response

    async def complete_json(
        self,
        *,
        messages: list[LLMMessage],
        system: str | None = None,
        json_schema_hint: dict[str, Any] | None = None,
        request_kind: str,
        user_id: uuid.UUID | None = None,
        agent_run_id: uuid.UUID | None = None,
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        input_chars = sum(len(m.content) for m in messages) + len(system or "")
        try:
            result = await self.provider.complete_json(
                messages=messages,
                system=system,
                json_schema_hint=json_schema_hint,
                request_kind=request_kind,
            )
        except LLMError as exc:
            await self._log_call(
                session=session,
                request_kind=request_kind,
                status="timeout" if isinstance(exc, LLMTimeoutError) else "error",
                user_id=user_id,
                agent_run_id=agent_run_id,
                latency_ms=int((time.monotonic() - started) * 1000),
                input_chars=input_chars,
                error_message=str(exc)[:1000],
            )
            raise
        await self._log_call(
            session=session,
            request_kind=request_kind,
            status="success",
            user_id=user_id,
            agent_run_id=agent_run_id,
            latency_ms=int((time.monotonic() - started) * 1000),
            input_chars=input_chars,
            output_chars=len(str(result)),
            request_hash=self._hash_messages(messages, system),
        )
        return result

    @staticmethod
    def _hash_messages(messages: list[LLMMessage], system: str | None) -> str:
        digest = hashlib.sha256()
        digest.update((system or "").encode())
        for m in messages:
            digest.update(m.role.encode())
            digest.update(m.content.encode())
        return digest.hexdigest()[:16]

    async def _log_call(
        self, *, session: AsyncSession | None = None, request_kind: str, status: str, **fields: Any
    ) -> None:
        row = LLMCall(
            provider=self.provider.name,
            model=getattr(self.provider, "model", "unknown"),
            request_kind=request_kind,
            status=status,
            user_id=fields.get("user_id"),
            agent_run_id=fields.get("agent_run_id"),
            latency_ms=fields.get("latency_ms"),
            input_char_count=fields.get("input_chars"),
            output_char_count=fields.get("output_chars"),
            input_token_estimate=fields.get("input_tokens"),
            output_token_estimate=fields.get("output_tokens"),
            request_hash=fields.get("request_hash"),
            error_message=fields.get("error_message"),
        )
        try:
            if session is not None:
                # Same transaction as the caller's agent_run — FK-safe.
                session.add(row)
                await session.flush()
            else:
                async with session_scope() as scope:
                    scope.add(row)
        except Exception:  # noqa: BLE001 — observability must never break the caller
            log.exception("failed to write llm_calls row")
