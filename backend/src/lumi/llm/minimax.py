"""MiniMax M3 provider via the OpenAI-compatible chat completions API."""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from lumi.llm.base import (
    LLMError,
    LLMMessage,
    LLMResponse,
    LLMResponseFormatError,
    LLMTimeoutError,
    estimate_tokens,
)
from lumi.llm.json_utils import extract_json
from lumi.logging import get_logger

log = get_logger(__name__)


_THINK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>\s*", re.DOTALL)


def strip_reasoning(text: str) -> str:
    """M3 is a reasoning model: the OpenAI-compatible endpoint returns its
    chain-of-thought inside <think>…</think> in content. Users must never see it."""
    return _THINK_RE.sub("", text).strip()




class ThinkStreamFilter:
    """Incrementally strips <think>…</think> from a streamed completion.

    feed(delta) returns only NEW visible characters. Tags split across
    deltas are handled by re-deriving the visible prefix from the full
    accumulated text on every feed (text is small, so O(n^2) is fine).
    """

    _OPEN = "<think"

    def __init__(self) -> None:
        self.raw = ""
        self._emitted = 0
        self.thinking = False  # currently inside an unclosed think block

    def feed(self, delta: str) -> str:
        self.raw += delta
        visible = re.sub(
            r"<think(?:ing)?>.*?(?:</think(?:ing)?>|\Z)", "", self.raw, flags=re.DOTALL
        )
        # Hold back a trailing partial "<think" opener until disambiguated.
        tail = visible[-7:]
        for i in range(len(tail), 0, -1):
            if self._OPEN.startswith(tail[-i:]):
                visible = visible[: len(visible) - i]
                break
        self.thinking = bool(
            re.search(r"<think(?:ing)?>(?!.*</think(?:ing)?>)", self.raw, flags=re.DOTALL)
        )
        new = visible[self._emitted:]
        self._emitted = len(visible)
        return new


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException | httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return False


class MiniMaxProvider:
    name = "minimax"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.minimax.io/v1",
        model: str = "MiniMax-M3",
        timeout_seconds: int = 90,
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self.model = model
        self._timeout = timeout_seconds
        self._max_retries = max(1, max_retries)

    async def _chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=15),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )
        async def _call() -> dict[str, Any]:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()

        try:
            return await _call()
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"MiniMax timed out after {self._timeout}s") from exc
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500]
            raise LLMError(f"MiniMax HTTP {exc.response.status_code}: {body}") from exc
        except httpx.TransportError as exc:
            raise LLMError(f"MiniMax transport error: {exc}") from exc

    @staticmethod
    def _build_messages(messages: list[LLMMessage], system: str | None) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if system:
            out.append({"role": "system", "content": system})
        out.extend({"role": m.role, "content": m.content} for m in messages)
        return out

    async def complete(
        self,
        *,
        messages: list[LLMMessage],
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        request_kind: str,
        metadata: dict[str, Any] | None = None,
        force_json: bool = False,
    ) -> LLMResponse:
        api_messages = self._build_messages(messages, system)
        input_chars = sum(len(m["content"]) for m in api_messages)
        started = time.monotonic()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            # M3 spends tokens on reasoning before the visible answer —
            # give headroom so the answer itself never gets truncated.
            "max_tokens": max_tokens + 4096,
        }
        if force_json:
            # Hard guarantee: the model must emit a JSON object after reasoning.
            payload["response_format"] = {"type": "json_object"}
        data = await self._chat(payload)
        latency_ms = int((time.monotonic() - started) * 1000)

        try:
            choice = data["choices"][0]
            raw_content = choice["message"]["content"] or ""
            text = strip_reasoning(raw_content)
            if choice.get("finish_reason") == "length":
                log.warning("minimax output truncated by max_tokens",
                            fields={"request_kind": request_kind,
                                    "raw_chars": len(raw_content)})
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseFormatError(f"unexpected MiniMax response shape: {list(data)[:8]}") from exc

        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            provider=self.name,
            model=data.get("model", self.model),
            latency_ms=latency_ms,
            input_chars=input_chars,
            output_chars=len(text),
            input_tokens=usage.get("prompt_tokens") or estimate_tokens(" ".join(m["content"] for m in api_messages)),
            output_tokens=usage.get("completion_tokens") or estimate_tokens(text),
        )


    async def complete_stream(
        self,
        *,
        messages: list[LLMMessage],
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        request_kind: str,
        metadata: dict[str, Any] | None = None,
        on_delta=None,
        on_thinking=None,
    ) -> LLMResponse:
        """Stream a completion. on_delta(visible_so_far) fires as text arrives;
        on_thinking() fires while the model is still inside its reasoning block."""
        api_messages = self._build_messages(messages, system)
        input_chars = sum(len(m["content"]) for m in api_messages)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens + 4096,
            "stream": True,
        }
        started = time.monotonic()
        think_filter = ThinkStreamFilter()
        visible = ""
        timeout = httpx.Timeout(connect=10, read=self._timeout, write=30, pool=10)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = (choices[0].get("delta") or {}).get("content") or ""
                        if not delta:
                            continue
                        new_visible = think_filter.feed(delta)
                        if new_visible:
                            visible += new_visible
                            if on_delta is not None:
                                await on_delta(visible)
                        elif think_filter.thinking and on_thinking is not None:
                            await on_thinking()
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"MiniMax stream timed out after {self._timeout}s") from exc
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"MiniMax HTTP {exc.response.status_code}") from exc
        except httpx.TransportError as exc:
            raise LLMError(f"MiniMax transport error: {exc}") from exc

        text = visible.strip()
        latency_ms = int((time.monotonic() - started) * 1000)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            latency_ms=latency_ms,
            input_chars=input_chars,
            output_chars=len(text),
            input_tokens=estimate_tokens(" ".join(m["content"] for m in api_messages)),
            output_tokens=estimate_tokens(text),
        )

    async def complete_json(
        self,
        *,
        messages: list[LLMMessage],
        system: str | None = None,
        json_schema_hint: dict[str, Any] | None = None,
        request_kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        json_system = (system or "") + (
            "\n\nОтветь строго одним валидным JSON-объектом. Без markdown, без комментариев, без текста до или после."
        )
        if json_schema_hint:
            json_system += "\nJSON schema hint:\n" + json.dumps(json_schema_hint, ensure_ascii=False)

        last_error: Exception | None = None
        for attempt in range(2):  # one re-ask on malformed JSON
            response = await self.complete(
                messages=messages,
                system=json_system,
                temperature=0.0 if attempt == 0 else 0.1,
                max_tokens=4096,
                request_kind=request_kind,
                metadata=metadata,
                force_json=True,
            )
            try:
                return extract_json(response.text)
            except ValueError as exc:
                last_error = exc
                log.warning(
                    "minimax returned non-JSON, retrying",
                    fields={"request_kind": request_kind, "attempt": attempt,
                            "head": response.text[:180]},
                )
        raise LLMResponseFormatError(str(last_error))
