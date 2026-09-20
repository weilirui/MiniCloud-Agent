"""Token and cost accounting.

Every LLM call the platform makes should be measurable: how many tokens, how
much money, how long it took. Without this, "优化" is guesswork.

``CostTracker`` keeps an in-memory aggregate (cheap, always on) and optionally
forwards each record to a sink (e.g. a DB writer) for durable history.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from app.utils.logging import get_logger

logger = get_logger(__name__)

#: USD per 1M tokens: (input, output). Keys are matched by substring.
MODEL_PRICING_USD_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    "qwen-plus": (0.11, 0.30),
    "qwen-turbo": (0.05, 0.20),
    "moonshot-v1-8k": (0.17, 0.17),
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
}

DEFAULT_PRICING: tuple[float, float] = (0.15, 0.60)


def get_pricing(model: str) -> tuple[float, float]:
    """Look up pricing for a model name; unknown models fall back to a default."""
    if not model:
        return DEFAULT_PRICING
    lowered = model.lower()
    for key, price in MODEL_PRICING_USD_PER_1M.items():
        if key in lowered:
            return price
    return DEFAULT_PRICING


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimated USD cost of one LLM call."""
    in_price, out_price = get_pricing(model)
    return round(
        (prompt_tokens / 1_000_000) * in_price + (completion_tokens / 1_000_000) * out_price,
        8,
    )


@dataclass
class UsageRecord:
    """One measured LLM call."""

    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    endpoint: str = ""
    session_id: str | None = None
    latency_ms: int = 0
    cost_usd: float = 0.0
    created_at: float = field(default_factory=time.time)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total_tokens"] = self.total_tokens
        return data


class CostTracker:
    """Aggregate token usage and cost, optionally persisting each record."""

    def __init__(self, sink: Callable[[UsageRecord], Awaitable[None]] | None = None) -> None:
        self.sink = sink
        self._records: list[UsageRecord] = []

    # ---------- write ----------

    def record(
        self,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        *,
        endpoint: str = "",
        session_id: str | None = None,
        latency_ms: int = 0,
    ) -> UsageRecord:
        rec = UsageRecord(
            model=model,
            prompt_tokens=int(prompt_tokens or 0),
            completion_tokens=int(completion_tokens or 0),
            endpoint=endpoint,
            session_id=session_id,
            latency_ms=int(latency_ms or 0),
            cost_usd=estimate_cost(model, prompt_tokens, completion_tokens),
        )
        self._records.append(rec)
        return rec

    async def track(self, *args: Any, **kwargs: Any) -> UsageRecord:
        """Record and hand the record to the sink (if configured)."""
        rec = self.record(*args, **kwargs)
        if self.sink is not None:
            try:
                await self.sink(rec)
            except Exception as exc:  # never break the request path on telemetry
                logger.warning("usage_sink_failed", error=str(exc))
        return rec

    def record_from_usage(
        self,
        usage: dict[str, Any] | None,
        model: str,
        **kwargs: Any,
    ) -> UsageRecord:
        """Build a record from an OpenAI-style ``usage`` payload."""
        usage = usage or {}
        return self.record(
            model=model,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            **kwargs,
        )

    # ---------- read ----------

    def aggregate(self, group_by: str = "model") -> dict[str, dict[str, float]]:
        """Aggregate totals grouped by ``model`` or ``endpoint``."""
        out: dict[str, dict[str, float]] = {}
        for rec in self._records:
            key = getattr(rec, group_by, "") or "unknown"
            bucket = out.setdefault(
                key,
                {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0, "latency_ms": 0},
            )
            bucket["calls"] += 1
            bucket["prompt_tokens"] += rec.prompt_tokens
            bucket["completion_tokens"] += rec.completion_tokens
            bucket["cost_usd"] += rec.cost_usd
            bucket["latency_ms"] += rec.latency_ms
        for bucket in out.values():
            bucket["cost_usd"] = round(bucket["cost_usd"], 6)
            bucket["avg_latency_ms"] = round(bucket["latency_ms"] / max(bucket["calls"], 1), 2)
        return out

    def totals(self) -> dict[str, float]:
        agg = self.aggregate()
        return {
            "calls": float(sum(b["calls"] for b in agg.values())),
            "prompt_tokens": float(sum(b["prompt_tokens"] for b in agg.values())),
            "completion_tokens": float(sum(b["completion_tokens"] for b in agg.values())),
            "cost_usd": round(sum(b["cost_usd"] for b in agg.values()), 6),
        }

    def snapshot(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._records]

    def reset(self) -> None:
        self._records.clear()


_tracker: CostTracker | None = None


def get_tracker() -> CostTracker:
    """Process-wide tracker (tests create their own instances)."""
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker


def db_usage_sink(session_factory):
    """Build a sink that writes every ``UsageRecord`` into the ``llm_usage`` table.

    Wire it once at startup::

        get_tracker().sink = db_usage_sink(get_session_factory())

    The import of the ORM models is deferred so that importing this module
    never pulls in the database layer.
    """

    async def sink(record: UsageRecord) -> None:
        from uuid import UUID

        from app.db.models import LLMUsage

        def as_uuid(value):
            try:
                return UUID(str(value)) if value else None
            except (ValueError, AttributeError, TypeError):
                return None

        async with session_factory() as db:
            db.add(
                LLMUsage(
                    session_id=as_uuid(record.session_id),
                    model=record.model,
                    endpoint=record.endpoint,
                    prompt_tokens=record.prompt_tokens,
                    completion_tokens=record.completion_tokens,
                    latency_ms=record.latency_ms,
                    cost_usd=record.cost_usd,
                )
            )
            await db.commit()

    return sink
