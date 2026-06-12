"""SignalExtractor: structured JSON extraction from a user message."""

from __future__ import annotations

import uuid

from lumi.assistant.prompts import SIGNAL_EXTRACTION_SCHEMA_HINT, SIGNAL_EXTRACTION_SYSTEM
from lumi.assistant.schemas import ExtractedSignals
from lumi.db.models import User
from lumi.llm.base import LLMMessage
from lumi.llm.gateway import LLMGateway
from lumi.logging import get_logger
from lumi.utils.time import local_now

log = get_logger(__name__)


class SignalExtractor:
    def __init__(self, llm: LLMGateway | None = None) -> None:
        self.llm = llm or LLMGateway()

    async def extract(
        self,
        *,
        user: User,
        text: str,
        known_context: str | None = None,
        agent_run_id: uuid.UUID | None = None,
        session=None,
    ) -> ExtractedSignals:
        """Extraction must never break the chat: any failure -> empty signals."""
        now_local = local_now(user.timezone)
        user_content = (
            f"Current datetime: {now_local.strftime('%Y-%m-%dT%H:%M:%S')}\n"
            f"Timezone: {user.timezone}\n"
            f"Known user context: {known_context or '—'}\n"
            f"Message: {text}\n\n"
            "Return JSON matching the schema."
        )
        try:
            raw = await self.llm.complete_json(
                messages=[LLMMessage(role="user", content=user_content)],
                system=SIGNAL_EXTRACTION_SYSTEM,
                json_schema_hint=SIGNAL_EXTRACTION_SCHEMA_HINT,
                request_kind="signal_extraction",
                user_id=user.id,
                agent_run_id=agent_run_id,
                session=session,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("signal extraction LLM call failed", fields={"error": str(exc)})
            return ExtractedSignals.empty()

        try:
            return ExtractedSignals.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 — partial salvage below
            log.warning("signal extraction validation failed", fields={"error": str(exc)[:300]})
            # Salvage what we can field-by-field instead of dropping everything.
            salvaged = ExtractedSignals.empty()
            if isinstance(raw, dict):
                for task_raw in raw.get("tasks", []) or []:
                    try:
                        from lumi.assistant.schemas import ExtractedTask

                        salvaged.tasks.append(ExtractedTask.model_validate(task_raw))
                    except Exception:  # noqa: BLE001
                        continue
                for mem_raw in raw.get("memory_candidates", []) or []:
                    try:
                        from lumi.assistant.schemas import MemoryCandidate

                        salvaged.memory_candidates.append(MemoryCandidate.model_validate(mem_raw))
                    except Exception:  # noqa: BLE001
                        continue
            return salvaged
