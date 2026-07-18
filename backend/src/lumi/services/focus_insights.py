"""Deterministic weekly focus aggregates and evidence-backed hypotheses."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.db.models import (
    CalendarEvent,
    CalendarEventStatus,
    CalendarSource,
    FocusAnalysisStatus,
    FocusInsight,
    FocusInsightStatus,
    FocusSession,
    FocusSessionAnalysis,
    User,
)
from lumi.llm.base import LLMMessage
from lumi.llm.gateway import LLMGateway
from lumi.services.focus import FocusService
from lumi.services.realtime import RealtimeEventService
from lumi.utils.time import get_zone, utc_now

MIN_SESSIONS = 3
MIN_DAYS = 2
_RU_DAYPARTS = {
    "morning": "утренних",
    "afternoon": "дневных",
    "evening": "вечерних",
    "night": "ночных",
}
_RU_FRICTIONS = {
    "interruption": "прерывания",
    "unclear_scope": "неясный объём работы",
    "dependency": "зависимость от других",
    "energy": "нехватка энергии",
    "environment": "окружение",
    "tooling": "инструменты",
    "time_pressure": "нехватка времени",
    "other": "другая помеха",
}


@dataclass(slots=True)
class InsightCandidate:
    kind: str
    statement: str
    supporting_session_ids: list[str]
    distinct_days: int
    confidence: float
    evidence: dict[str, Any]


class InsightWording(Protocol):
    async def format(
        self,
        aggregate: dict[str, Any],
        *,
        locale: str,
    ) -> str: ...


class LLMInsightWording:
    """Optional wording-only adapter; generation remains deterministic-first."""

    def __init__(self, llm: LLMGateway | None = None) -> None:
        self.llm = llm or LLMGateway()

    async def format(
        self,
        aggregate: dict[str, Any],
        *,
        locale: str,
    ) -> str:
        language = "Russian" if _normalized_locale(locale) == "ru" else "English"
        result = await self.llm.complete_json(
            messages=[
                LLMMessage(
                    role="user",
                    content=json.dumps(aggregate, ensure_ascii=False, sort_keys=True),
                )
            ],
            system=(
                "Rewrite the validated focus aggregate as one concise observation. "
                "Preserve all numbers and the non-causal qualifier. Do not add advice, "
                f"diagnosis, entities, or unsupported claims. Write in {language}. "
                "Return JSON only."
            ),
            json_schema_hint={
                "type": "object",
                "properties": {
                    "statement": {"type": "string", "maxLength": 400},
                },
                "required": ["statement"],
                "additionalProperties": False,
            },
            request_kind="focus_insight_wording",
            temperature=0.1,
            max_tokens=300,
        )
        return str(result.get("statement") or "")


def insight_wording_payload(
    candidate: InsightCandidate,
    *,
    locale: str = "en",
) -> dict[str, Any]:
    """Provider-safe aggregate: no raw reflections, entity names, or row ids."""

    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: scrub(item)
                for key, item in value.items()
                if "session_id" not in key and "project" not in key and key != "id"
            }
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    return {
        "locale": _normalized_locale(locale),
        "kind": candidate.kind,
        "draft": candidate.statement,
        "support_count": len(candidate.supporting_session_ids),
        "distinct_days": candidate.distinct_days,
        "confidence": _rounded(candidate.confidence),
        "aggregate_evidence": scrub(candidate.evidence),
    }


def _daypart(value: datetime, timezone: str) -> str:
    hour = value.astimezone(get_zone(timezone)).hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def _session_day(value: FocusSession, timezone: str) -> str:
    return value.started_at.astimezone(get_zone(timezone)).date().isoformat()


def _rounded(value: float) -> float:
    return round(value, 2)


def _normalized_locale(locale: str | None) -> str:
    return "ru" if (locale or "").casefold().startswith("ru") else "en"


def _safe_wording(
    candidate: InsightCandidate,
    wording: str,
    *,
    locale: str,
) -> str:
    cleaned = " ".join(wording.split()).strip()
    forbidden = (
        "causes",
        "proves",
        "personality",
        "lazy",
        "вызывает",
        "доказывает",
        "диагностирует",
    )
    normalized_locale = _normalized_locale(locale)
    required_qualifier = (
        "не диагноз"
        if normalized_locale == "ru" and candidate.kind.startswith("friction:")
        else "не причина"
        if normalized_locale == "ru"
        else "not a diagnosis"
        if candidate.kind.startswith("friction:")
        else "not a cause"
    )
    if (
        not cleaned
        or len(cleaned) > 400
        or any(term in cleaned.casefold() for term in forbidden)
        or required_qualifier not in cleaned.casefold()
    ):
        return candidate.statement
    return cleaned


class FocusInsightService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        wording: InsightWording | None = None,
    ) -> None:
        self.session = session
        self.wording = wording

    @staticmethod
    def week_bounds(user: User) -> tuple[datetime, datetime]:
        zone = get_zone(user.timezone)
        today = utc_now().astimezone(zone).date()
        start_local = datetime.combine(
            today - timedelta(days=6),
            time.min,
            tzinfo=zone,
        )
        end_local = datetime.combine(today + timedelta(days=1), time.min, tzinfo=zone)
        return start_local.astimezone(UTC), end_local.astimezone(UTC)

    async def aggregates(
        self,
        user: User,
        *,
        start: datetime,
        end: datetime,
    ) -> tuple[dict[str, Any], list[FocusSession], dict[uuid.UUID, FocusSessionAnalysis]]:
        sessions = await FocusService(self.session).completed_between(user, start, end)
        session_by_id = {item.id: item for item in sessions}
        analyses: dict[uuid.UUID, FocusSessionAnalysis] = {}
        if session_by_id:
            result = await self.session.execute(
                select(FocusSessionAnalysis)
                .where(
                    FocusSessionAnalysis.user_id == user.id,
                    FocusSessionAnalysis.focus_session_id.in_(session_by_id),
                    FocusSessionAnalysis.status == FocusAnalysisStatus.READY,
                )
                .order_by(
                    FocusSessionAnalysis.created_at.desc(),
                    FocusSessionAnalysis.id.desc(),
                )
            )
            for analysis in result.scalars():
                focus_session = session_by_id.get(analysis.focus_session_id)
                if (
                    focus_session is not None
                    and analysis.focus_session_id not in analyses
                    and analysis.input_hash == focus_session.reflection_input_hash
                ):
                    analyses[analysis.focus_session_id] = analysis

        calendar_result = await self.session.execute(
            select(CalendarEvent).where(
                CalendarEvent.user_id == user.id,
                CalendarEvent.source != CalendarSource.INTERNAL,
                CalendarEvent.status != CalendarEventStatus.CANCELLED,
                CalendarEvent.busy.is_(True),
                CalendarEvent.end_at >= start - timedelta(minutes=90),
                CalendarEvent.start_at < end,
            )
        )
        external_events = list(calendar_result.scalars())

        project: dict[str, dict[str, Any]] = defaultdict(lambda: {"session_count": 0, "focus_seconds": 0})
        daypart: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"session_ids": [], "days": set(), "scores": []}
        )
        friction: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"session_ids": [], "days": set(), "confidence": []}
        )
        planned_actual: list[dict[str, Any]] = []
        meeting_context: dict[str, dict[str, Any]] = {
            "after_meeting": {"session_ids": [], "days": set(), "scores": []},
            "otherwise": {"session_ids": [], "days": set(), "scores": []},
        }
        break_count = 0
        scored = []
        total_seconds = 0
        for focus_session in sessions:
            session_id = str(focus_session.id)
            local_day = _session_day(focus_session, user.timezone)
            seconds = focus_session.duration_seconds or 0
            total_seconds += seconds
            if focus_session.focus_score is not None:
                scored.append(focus_session.focus_score)
            if focus_session.break_started_at is not None:
                break_count += 1
            project_key = focus_session.project_snapshot or "unassigned"
            project[project_key]["session_count"] += 1
            project[project_key]["focus_seconds"] += seconds
            part = daypart[_daypart(focus_session.started_at, user.timezone)]
            part["session_ids"].append(session_id)
            part["days"].add(local_day)
            if focus_session.focus_score is not None:
                part["scores"].append(focus_session.focus_score)
            if focus_session.planned_event_id is not None:
                actual_minutes = seconds / 60
                delta_percent = (
                    (actual_minutes - focus_session.planned_minutes) / focus_session.planned_minutes * 100
                )
                planned_actual.append(
                    {
                        "session_id": session_id,
                        "day": local_day,
                        "planned_minutes": focus_session.planned_minutes,
                        "actual_minutes": _rounded(actual_minutes),
                        "delta_percent": _rounded(delta_percent),
                    }
                )
            after_meeting = any(
                event.end_at <= focus_session.started_at
                and event.end_at >= focus_session.started_at - timedelta(minutes=90)
                for event in external_events
            )
            cohort = meeting_context["after_meeting" if after_meeting else "otherwise"]
            cohort["session_ids"].append(session_id)
            cohort["days"].add(local_day)
            if focus_session.focus_score is not None:
                cohort["scores"].append(focus_session.focus_score)
            current_analysis = analyses.get(focus_session.id)
            if current_analysis is not None:
                for item in current_analysis.frictions:
                    label = item.get("label")
                    confidence = item.get("confidence")
                    if not isinstance(label, str):
                        continue
                    bucket = friction[label]
                    bucket["session_ids"].append(session_id)
                    bucket["days"].add(local_day)
                    if isinstance(confidence, (int, float)):
                        bucket["confidence"].append(float(confidence))

        def serialize_buckets(raw: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
            return {
                key: {
                    **{name: value for name, value in bucket.items() if name != "days"},
                    "distinct_days": len(bucket["days"]),
                }
                for key, bucket in raw.items()
            }

        return (
            {
                "window": {"start": start.isoformat(), "end": end.isoformat()},
                "total_sessions": len(sessions),
                "distinct_days": len({_session_day(item, user.timezone) for item in sessions}),
                "total_focus_seconds": total_seconds,
                "average_duration_minutes": (_rounded(total_seconds / len(sessions) / 60) if sessions else 0),
                "average_focus_score": (_rounded(sum(scored) / len(scored)) if scored else None),
                "break_count": break_count,
                "project": dict(project),
                "daypart": serialize_buckets(daypart),
                "planned_actual": planned_actual,
                "meeting_context": serialize_buckets(meeting_context),
                "friction": serialize_buckets(friction),
            },
            sessions,
            analyses,
        )

    @staticmethod
    def candidates(
        aggregate: dict[str, Any],
        *,
        locale: str = "en",
    ) -> list[InsightCandidate]:
        if aggregate["total_sessions"] < MIN_SESSIONS or aggregate["distinct_days"] < MIN_DAYS:
            return []
        ru = _normalized_locale(locale) == "ru"
        candidates: list[InsightCandidate] = []
        planned = aggregate["planned_actual"]
        planned_days = len({item["day"] for item in planned})
        if len(planned) >= 3 and planned_days >= 2:
            mean_abs_delta = sum(abs(item["delta_percent"]) for item in planned) / len(planned)
            if mean_abs_delta >= 20:
                ids = [item["session_id"] for item in planned]
                candidates.append(
                    InsightCandidate(
                        kind="planned_actual_gap",
                        statement=(
                            (
                                "Фактический фокус отличался от запланированной "
                                f"длительности в среднем на {round(mean_abs_delta)}% "
                                f"в {len(ids)} сессиях. Это сигнал для планирования, "
                                "не причина."
                            )
                            if ru
                            else (
                                "Actual focus differed from planned duration by "
                                f"{round(mean_abs_delta)}% on average across {len(ids)} "
                                "sessions. This is a planning signal, not a cause."
                            )
                        ),
                        supporting_session_ids=ids,
                        distinct_days=planned_days,
                        confidence=min(0.95, 0.55 + len(ids) * 0.04),
                        evidence={
                            "metric": "mean_absolute_planned_delta_percent",
                            "value": _rounded(mean_abs_delta),
                            "sessions": planned,
                        },
                    )
                )

        scored_parts = []
        for name, bucket in aggregate["daypart"].items():
            scores = bucket["scores"]
            if len(scores) >= 3 and bucket["distinct_days"] >= 2:
                scored_parts.append(
                    (
                        name,
                        sum(scores) / len(scores),
                        bucket,
                    )
                )
        if len(scored_parts) >= 2:
            scored_parts.sort(key=lambda item: item[1], reverse=True)
            best, comparison = scored_parts[0], scored_parts[-1]
            gap = best[1] - comparison[1]
            if gap >= 0.75:
                ids = best[2]["session_ids"] + comparison[2]["session_ids"]
                candidates.append(
                    InsightCandidate(
                        kind="daypart_score_association",
                        statement=(
                            (
                                "Средняя оценка фокуса — "
                                f"{_rounded(best[1])} в "
                                f"{_RU_DAYPARTS.get(best[0], best[0])} сессиях "
                                f"против {_rounded(comparison[1])} в "
                                f"{_RU_DAYPARTS.get(comparison[0], comparison[0])} "
                                "сессиях. "
                                "Это связь, не причина."
                            )
                            if ru
                            else (
                                f"Focus scores averaged {_rounded(best[1])} in "
                                f"{best[0]} sessions versus "
                                f"{_rounded(comparison[1])} in "
                                f"{comparison[0]} sessions. "
                                "This is an association, not a cause."
                            )
                        ),
                        supporting_session_ids=ids,
                        distinct_days=max(
                            best[2]["distinct_days"],
                            comparison[2]["distinct_days"],
                        ),
                        confidence=min(0.92, 0.58 + len(ids) * 0.025),
                        evidence={
                            "metric": "average_focus_score_by_daypart",
                            "best": {
                                "daypart": best[0],
                                "average": _rounded(best[1]),
                                "session_count": len(best[2]["scores"]),
                            },
                            "comparison": {
                                "daypart": comparison[0],
                                "average": _rounded(comparison[1]),
                                "session_count": len(comparison[2]["scores"]),
                            },
                        },
                    )
                )

        for label, bucket in aggregate["friction"].items():
            ids = list(dict.fromkeys(bucket["session_ids"]))
            if len(ids) < 5 or bucket["distinct_days"] < 3:
                continue
            confidence_values = bucket["confidence"]
            average_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.5
            candidates.append(
                InsightCandidate(
                    kind=f"friction:{label}",
                    statement=(
                        (
                            f"«{_RU_FRICTIONS.get(label, label)}» отмечено "
                            f"в {len(ids)} рефлексиях за "
                            f"{bucket['distinct_days']} дней. Это повторяющаяся "
                            "помеха по записям пользователя, не диагноз."
                        )
                        if ru
                        else (
                            f"“{label}” appeared in {len(ids)} reflections across "
                            f"{bucket['distinct_days']} days. This is repeated "
                            "reported friction, not a diagnosis."
                        )
                    ),
                    supporting_session_ids=ids,
                    distinct_days=bucket["distinct_days"],
                    confidence=min(0.95, average_confidence),
                    evidence={
                        "metric": "extracted_friction_frequency",
                        "label": label,
                        "session_count": len(ids),
                        "distinct_days": bucket["distinct_days"],
                        "share_of_sessions": _rounded(len(ids) / aggregate["total_sessions"]),
                    },
                )
            )

        meeting = aggregate["meeting_context"]
        after = meeting["after_meeting"]
        otherwise = meeting["otherwise"]
        if (
            len(after["scores"]) >= 4
            and len(otherwise["scores"]) >= 4
            and after["distinct_days"] >= 3
            and otherwise["distinct_days"] >= 3
        ):
            after_average = sum(after["scores"]) / len(after["scores"])
            otherwise_average = sum(otherwise["scores"]) / len(otherwise["scores"])
            gap = abs(after_average - otherwise_average)
            if gap >= 0.75:
                ids = after["session_ids"] + otherwise["session_ids"]
                candidates.append(
                    InsightCandidate(
                        kind="meeting_score_association",
                        statement=(
                            (
                                "Средняя оценка фокуса после встреч — "
                                f"{_rounded(after_average)}, в остальных случаях — "
                                f"{_rounded(otherwise_average)}. Это связь, не причина."
                            )
                            if ru
                            else (
                                f"Focus scores averaged {_rounded(after_average)} "
                                "after meetings versus "
                                f"{_rounded(otherwise_average)} otherwise. "
                                "This is an association, not a cause."
                            )
                        ),
                        supporting_session_ids=ids,
                        distinct_days=max(
                            after["distinct_days"],
                            otherwise["distinct_days"],
                        ),
                        confidence=min(0.9, 0.55 + len(ids) * 0.02),
                        evidence={
                            "metric": "average_focus_score_after_meeting",
                            "after_meeting": {
                                "average": _rounded(after_average),
                                "session_count": len(after["scores"]),
                            },
                            "otherwise": {
                                "average": _rounded(otherwise_average),
                                "session_count": len(otherwise["scores"]),
                            },
                        },
                    )
                )
        candidates.sort(
            key=lambda item: (item.confidence, len(item.supporting_session_ids)),
            reverse=True,
        )
        return candidates[:3]

    async def refresh(self, user: User) -> list[FocusInsight]:
        locked_user = await self.session.scalar(
            select(User)
            .where(User.id == user.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked_user is None:
            return []
        start, end = self.week_bounds(locked_user)
        aggregate, _, _ = await self.aggregates(
            locked_user,
            start=start,
            end=end,
        )
        locale = _normalized_locale(locked_user.locale)
        candidates = self.candidates(aggregate, locale=locale)
        now = utc_now()
        existing_result = await self.session.execute(
            select(FocusInsight).where(FocusInsight.user_id == user.id).with_for_update()
        )
        existing = list(existing_result.scalars())
        current = [item for item in existing if item.window_start == start and item.window_end == end]
        existing_by_key = {(item.kind, item.context_hash): item for item in current}
        dismissed_hashes = {
            item.context_hash for item in existing if item.status == FocusInsightStatus.DISMISSED
        }
        active_keys: set[tuple[str, str]] = set()
        refreshed: list[FocusInsight] = []
        for candidate in candidates:
            context_hash = hashlib.sha256(
                json.dumps(
                    {
                        "kind": candidate.kind,
                        "ids": sorted(candidate.supporting_session_ids),
                        "evidence": candidate.evidence,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()[:24]
            if context_hash in dismissed_hashes:
                continue
            key = (candidate.kind, context_hash)
            active_keys.add(key)
            insight = existing_by_key.get(key)
            statement = candidate.statement
            if self.wording is not None:
                try:
                    statement = _safe_wording(
                        candidate,
                        await self.wording.format(
                            insight_wording_payload(candidate, locale=locale),
                            locale=locale,
                        ),
                        locale=locale,
                    )
                except Exception:  # noqa: BLE001 - deterministic wording is complete
                    statement = candidate.statement
            if insight is None:
                insight = FocusInsight(
                    user_id=user.id,
                    kind=candidate.kind,
                    status=FocusInsightStatus.PROPOSED,
                    window_start=start,
                    window_end=end,
                    statement=statement,
                    support_count=len(candidate.supporting_session_ids),
                    distinct_days=candidate.distinct_days,
                    confidence=candidate.confidence,
                    supporting_session_ids=candidate.supporting_session_ids,
                    evidence=candidate.evidence,
                    context_hash=context_hash,
                    first_seen_at=now,
                    last_seen_at=now,
                    expires_at=end + timedelta(days=7),
                )
                self.session.add(insight)
            else:
                insight.last_seen_at = now
                insight.statement = statement
                insight.support_count = len(candidate.supporting_session_ids)
                insight.distinct_days = candidate.distinct_days
                insight.confidence = candidate.confidence
                insight.supporting_session_ids = candidate.supporting_session_ids
                insight.evidence = candidate.evidence
            refreshed.append(insight)

        for insight in existing:
            if insight.status in {
                FocusInsightStatus.PROPOSED,
                FocusInsightStatus.CONFIRMED,
            } and (
                insight.window_start != start
                or insight.window_end != end
                or (insight.kind, insight.context_hash) not in active_keys
            ):
                insight.status = FocusInsightStatus.EXPIRED
        await self.session.flush()
        return refreshed

    async def list(self, user: User, *, limit: int = 3) -> list[FocusInsight]:
        await self.refresh(user)
        now = utc_now()
        result = await self.session.execute(
            select(FocusInsight)
            .where(
                FocusInsight.user_id == user.id,
                FocusInsight.status.in_(
                    [
                        FocusInsightStatus.PROPOSED,
                        FocusInsightStatus.CONFIRMED,
                    ]
                ),
                FocusInsight.expires_at > now,
            )
            .order_by(
                FocusInsight.confidence.desc(),
                FocusInsight.last_seen_at.desc(),
            )
            .limit(min(3, limit))
        )
        return list(result.scalars())

    async def get(
        self,
        user: User,
        insight_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> FocusInsight | None:
        query = select(FocusInsight).where(
            FocusInsight.id == insight_id,
            FocusInsight.user_id == user.id,
        )
        if for_update:
            query = query.with_for_update().execution_options(
                populate_existing=True,
            )
        return await self.session.scalar(query)

    async def _emit(self, insight: FocusInsight, event_type: str) -> None:
        await RealtimeEventService(self.session).emit(
            user_id=insight.user_id,
            topics=["focus"],
            event_type=event_type,
            payload={
                "insight_id": str(insight.id),
                "status": insight.status.value,
            },
        )

    async def try_insight(self, user: User, insight: FocusInsight) -> FocusInsight:
        locked = await self.get(user, insight.id, for_update=True)
        if locked is None:
            raise ValueError("focus_insight_not_found")
        now = utc_now()
        if locked.expires_at <= now:
            raise ValueError("focus_insight_not_available")
        if locked.status == FocusInsightStatus.CONFIRMED:
            return locked
        if locked.status != FocusInsightStatus.PROPOSED:
            raise ValueError("focus_insight_not_available")
        locked.status = FocusInsightStatus.CONFIRMED
        locked.decided_at = now
        await self.session.flush()
        await self._emit(locked, "focus.insight_confirmed")
        return locked

    async def dismiss(self, user: User, insight: FocusInsight) -> FocusInsight:
        locked = await self.get(user, insight.id, for_update=True)
        if locked is None:
            raise ValueError("focus_insight_not_found")
        now = utc_now()
        if locked.expires_at <= now:
            raise ValueError("focus_insight_not_available")
        if locked.status == FocusInsightStatus.DISMISSED:
            return locked
        if locked.status == FocusInsightStatus.EXPIRED:
            raise ValueError("focus_insight_not_available")
        locked.status = FocusInsightStatus.DISMISSED
        locked.decided_at = now
        await self.session.flush()
        await self._emit(locked, "focus.insight_dismissed")
        return locked
