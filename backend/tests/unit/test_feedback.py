"""Unit tests for the feedback service (bad-case回流)."""

from __future__ import annotations

import json

import pytest

from app.feedback.service import FeedbackService


async def test_submit_records_feedback():
    service = FeedbackService()
    rec = await service.submit("s-1", 5, message_id="m-1", query="q", answer="a")
    assert rec.rating == 5
    assert rec.session_id == "s-1"
    assert len(service.all()) == 1


@pytest.mark.parametrize("bad", [0, 6, "3", None])
async def test_submit_rejects_invalid_rating(bad):
    service = FeedbackService()
    with pytest.raises(ValueError):
        await service.submit("s-1", bad)


async def test_negative_detection():
    service = FeedbackService()
    await service.submit("s-1", 2)
    await service.submit("s-2", 5)
    await service.submit("s-3", 3)

    assert [r.session_id for r in service.negative()] == ["s-1", "s-3"]


async def test_stats():
    service = FeedbackService()
    await service.submit("s-1", 1)
    await service.submit("s-2", 5)

    stats = service.stats()
    assert stats["total"] == 2
    assert stats["negative"] == 1
    assert stats["negative_rate"] == 0.5
    assert stats["avg_rating"] == 3.0


def test_stats_on_empty_service():
    assert FeedbackService().stats()["total"] == 0


async def test_sink_receives_records():
    seen = []

    async def sink(rec):
        seen.append(rec)

    service = FeedbackService(sink=sink)
    await service.submit("s-1", 4)
    assert len(seen) == 1


async def test_sink_failure_does_not_break_submit():
    async def broken(_rec):
        raise RuntimeError("db down")

    service = FeedbackService(sink=broken)
    rec = await service.submit("s-1", 4)
    assert rec.rating == 4


async def test_export_jsonl_writes_labeled_candidates(tmp_path):
    service = FeedbackService()
    await service.submit("s-1", 1, query="问题A", answer="错误回答", tags=["幻觉"])
    await service.submit("s-2", 5, query="问题B", answer="正确回答")

    path = service.export_jsonl(tmp_path / "feedback.jsonl")
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert len(lines) == 2
    assert lines[0]["label"] == "bad"
    assert lines[1]["label"] == "good"
    assert lines[0]["tags"] == ["幻觉"]
    assert lines[0]["query"] == "问题A"


async def test_export_uses_default_directory(tmp_path):
    service = FeedbackService(export_dir=tmp_path / "annotations")
    await service.submit("s-1", 1)

    path = service.export_jsonl()
    assert path.exists()
    assert path.parent.name == "annotations"
