"""Unit tests for token / cost accounting."""

from __future__ import annotations

from app.observability.cost import (
    CostTracker,
    estimate_cost,
    get_pricing,
)


def test_pricing_known_model():
    in_price, out_price = get_pricing("gpt-4o-mini")
    assert in_price == 0.15 and out_price == 0.60


def test_pricing_unknown_model_falls_back():
    assert get_pricing("totally-unknown-model") == (0.15, 0.60)


def test_pricing_empty_model():
    assert get_pricing("") == (0.15, 0.60)


def test_estimate_cost_scales_with_tokens():
    cheap = estimate_cost("gpt-4o-mini", 1000, 1000)
    expensive = estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000)
    assert expensive > cheap
    assert expensive > 0


def test_estimate_cost_zero_tokens():
    assert estimate_cost("gpt-4o-mini", 0, 0) == 0.0


def test_record_computes_total_and_cost():
    tracker = CostTracker()
    rec = tracker.record("gpt-4o-mini", prompt_tokens=1_000_000, completion_tokens=0)
    assert rec.total_tokens == 1_000_000
    assert rec.cost_usd > 0


def test_record_captures_endpoint_and_session():
    tracker = CostTracker()
    rec = tracker.record(
        "gpt-4o-mini", 10, 5, endpoint="chat/stream", session_id="s-1", latency_ms=123
    )
    assert rec.endpoint == "chat/stream"
    assert rec.session_id == "s-1"
    assert rec.latency_ms == 123


def test_aggregate_groups_by_model():
    tracker = CostTracker()
    tracker.record("gpt-4o-mini", 100, 50)
    tracker.record("gpt-4o-mini", 100, 50)
    tracker.record("gpt-4o", 100, 50)

    agg = tracker.aggregate(group_by="model")
    assert agg["gpt-4o-mini"]["calls"] == 2
    assert agg["gpt-4o"]["calls"] == 1
    assert agg["gpt-4o"]["cost_usd"] > agg["gpt-4o-mini"]["cost_usd"]


def test_aggregate_groups_by_endpoint():
    tracker = CostTracker()
    tracker.record("gpt-4o-mini", 10, 5, endpoint="a")
    tracker.record("gpt-4o-mini", 10, 5, endpoint="b")
    agg = tracker.aggregate(group_by="endpoint")
    assert set(agg) == {"a", "b"}


def test_totals_sum_everything():
    tracker = CostTracker()
    tracker.record("gpt-4o-mini", 100, 50)
    tracker.record("gpt-4o-mini", 200, 80)
    totals = tracker.totals()
    assert totals["calls"] == 2
    assert totals["prompt_tokens"] == 300
    assert totals["completion_tokens"] == 130


def test_empty_tracker_totals():
    assert CostTracker().totals()["calls"] == 0


def test_record_from_usage_payload():
    tracker = CostTracker()
    rec = tracker.record_from_usage(
        {"prompt_tokens": 120, "completion_tokens": 30}, "gpt-4o-mini"
    )
    assert rec.prompt_tokens == 120
    assert rec.completion_tokens == 30


def test_record_from_usage_handles_missing_payload():
    tracker = CostTracker()
    rec = tracker.record_from_usage(None, "gpt-4o-mini")
    assert rec.total_tokens == 0


async def test_track_forwards_to_sink():
    seen = []

    async def sink(rec):
        seen.append(rec)

    tracker = CostTracker(sink=sink)
    await tracker.track("gpt-4o-mini", 10, 5, endpoint="chat/stream")
    assert len(seen) == 1
    assert seen[0].endpoint == "chat/stream"


async def test_track_survives_sink_failure():
    async def broken_sink(_rec):
        raise RuntimeError("db down")

    tracker = CostTracker(sink=broken_sink)
    rec = await tracker.track("gpt-4o-mini", 10, 5)
    assert rec.total_tokens == 15


def test_reset_and_snapshot():
    tracker = CostTracker()
    tracker.record("gpt-4o-mini", 10, 5)
    assert len(tracker.snapshot()) == 1
    tracker.reset()
    assert tracker.snapshot() == []


class _Session:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *exc):
        return False


class _FakeDB:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


async def test_db_usage_sink_writes_an_orm_row():
    from app.observability.cost import db_usage_sink

    db = _FakeDB()
    sink = db_usage_sink(lambda: _Session(db))

    tracker = CostTracker(sink=sink)
    await tracker.track("gpt-4o-mini", 1200, 300, endpoint="chat/stream", latency_ms=800)

    assert db.commits == 1
    row = db.added[0]
    assert row.model == "gpt-4o-mini"
    assert row.endpoint == "chat/stream"
    assert row.prompt_tokens == 1200
    assert row.completion_tokens == 300
    assert row.latency_ms == 800


async def test_db_usage_sink_tolerates_bad_session_id():
    from app.observability.cost import db_usage_sink

    db = _FakeDB()
    sink = db_usage_sink(lambda: _Session(db))

    tracker = CostTracker(sink=sink)
    await tracker.track("gpt-4o-mini", 1, 1, session_id="not-a-uuid")

    assert db.commits == 1
    assert db.added[0].session_id is None
