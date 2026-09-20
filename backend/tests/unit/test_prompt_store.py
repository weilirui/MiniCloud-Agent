"""Unit tests for prompt versioning and A/B assignment."""

from __future__ import annotations

import json

import pytest

from app.core.prompt_store import PromptExperiment, PromptStore

TEMPLATE_V1 = "你是助手。当前时间 {current_time}。请用{mode}模式回答。"
TEMPLATE_V2 = "你是资深助手。时间：{current_time}。模式：{mode}。请给出结构化回答。"


def _store() -> PromptStore:
    store = PromptStore()
    store.register("chat_system", "v1", TEMPLATE_V1)
    return store


def test_first_registration_becomes_default():
    store = _store()
    assert store.get("chat_system").version == "v1"


def test_render_fills_placeholders():
    store = _store()
    text = store.render("chat_system", current_time="2026-09-20", mode="简洁")
    assert "2026-09-20" in text
    assert "简洁" in text
    assert "{" not in text


def test_multiple_versions_coexist():
    store = _store()
    store.register("chat_system", "v2", TEMPLATE_V2)
    assert store.list_versions("chat_system") == ["v1", "v2"]
    # default stays v1 unless explicitly switched
    assert store.get("chat_system").version == "v1"


def test_set_default_switches_version():
    store = _store()
    store.register("chat_system", "v2", TEMPLATE_V2)
    store.set_default("chat_system", "v2")
    assert store.get("chat_system").version == "v2"
    assert "结构化" in store.render("chat_system", current_time="t", mode="m")


def test_register_with_set_default_flag():
    store = _store()
    store.register("chat_system", "v2", TEMPLATE_V2, set_default=True)
    assert store.get("chat_system").version == "v2"


def test_unknown_prompt_raises():
    with pytest.raises(KeyError):
        _store().get("nope")


def test_unknown_version_raises():
    store = _store()
    with pytest.raises(KeyError):
        store.get("chat_system", "v99")
    with pytest.raises(KeyError):
        store.set_default("chat_system", "v99")


def test_persistence_roundtrip(tmp_path):
    store = PromptStore(storage_dir=tmp_path)
    store.register("chat_system", "v1", TEMPLATE_V1)
    store.register("chat_system", "v2", TEMPLATE_V2, set_default=True)
    store.save("chat_system")

    reloaded = PromptStore(storage_dir=tmp_path)
    assert reloaded.list_versions("chat_system") == ["v1", "v2"]
    assert reloaded.get("chat_system").version == "v2"
    assert reloaded.render("chat_system", current_time="t", mode="m") == store.render(
        "chat_system", current_time="t", mode="m"
    )


def test_persistence_files_are_valid_json(tmp_path):
    store = PromptStore(storage_dir=tmp_path)
    store.register("chat_system", "v1", TEMPLATE_V1)
    store.save("chat_system")

    payload = json.loads((tmp_path / "chat_system.json").read_text(encoding="utf-8"))
    assert payload["name"] == "chat_system"
    assert len(payload["versions"]) == 1


def test_experiment_assignment_is_deterministic():
    store = _store()
    store.register("chat_system", "v2", TEMPLATE_V2)
    store.set_experiment(PromptExperiment("chat_system", [("v1", 50), ("v2", 50)]))

    first = store.assign("chat_system", "session-abc")
    for _ in range(5):
        assert store.assign("chat_system", "session-abc") == first


def test_experiment_splits_traffic():
    store = _store()
    store.register("chat_system", "v2", TEMPLATE_V2)
    store.set_experiment(PromptExperiment("chat_system", [("v1", 50), ("v2", 50)]))

    counts = {"v1": 0, "v2": 0}
    for i in range(400):
        counts[store.assign("chat_system", f"session-{i}")] += 1

    assert counts["v1"] > 100 and counts["v2"] > 100
    ratio = counts["v1"] / 400
    assert 0.3 < ratio < 0.7


def test_experiment_percentages_must_be_sane():
    with pytest.raises(ValueError):
        PromptExperiment("bad", [("v1", 60), ("v2", 60)]).validate()
    with pytest.raises(ValueError):
        PromptExperiment("bad", [("v1", 0)]).validate()


def test_render_for_session_reports_chosen_version():
    store = _store()
    store.register("chat_system", "v2", TEMPLATE_V2)
    store.set_experiment(PromptExperiment("chat_system", [("v1", 100)]))

    text, version = store.render_for_session(
        "chat_system", "session-1", current_time="t", mode="m"
    )
    assert version == "v1"
    assert "t" in text


def test_no_experiment_falls_back_to_default():
    store = _store()
    assert store.assign("chat_system", "any-session") == "v1"
