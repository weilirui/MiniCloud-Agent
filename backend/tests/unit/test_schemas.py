"""Contract tests for the Pydantic schemas.

These exist because a schema typo only shows up at runtime as a 422, usually
after the frontend is already written against it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatRequest, ToolCallInfo
from app.schemas.mcp import MCPRestartResponse, MCPServersResponse, MCPServerStatus
from app.schemas.rag import QueryHit, QueryRequest, QueryResponse, UploadResponse
from app.schemas.session import MessageOut, SessionCreate, SessionDetail, SessionOut
from app.schemas.skill import SkillInfo, SkillInvokeRequest, SkillInvokeResponse

NOW = datetime(2026, 9, 20, 10, 0, 0)


def test_chat_request_requires_message():
    with pytest.raises(ValidationError):
        ChatRequest()


def test_chat_request_defaults():
    req = ChatRequest(message="你好")
    assert req.session_id is None
    assert req.stream is True
    assert req.temperature == 0.7


def test_chat_request_accepts_session_id():
    sid = uuid.uuid4()
    assert ChatRequest(message="hi", session_id=sid).session_id == sid


def test_tool_call_info_defaults_arguments():
    assert ToolCallInfo(id="c1", name="rag_search").arguments == {}


def test_message_out_serialises_datetime_as_iso():
    msg = MessageOut(id=uuid.uuid4(), role="user", content="hi", created_at=NOW)
    assert msg.model_dump(mode="json")["created_at"].startswith("2026-09-20")


def test_message_out_requires_content():
    with pytest.raises(ValidationError):
        MessageOut(id=uuid.uuid4(), role="user", created_at=NOW)


def test_chat_message_out_uses_string_timestamp():
    from app.schemas.chat import MessageOut as ChatMessageOut

    msg = ChatMessageOut(id=uuid.uuid4(), role="user", content="hi", created_at="2026-09-20T10:00:00")
    assert msg.model_dump(mode="json")["created_at"] == "2026-09-20T10:00:00"


def test_session_create_is_all_optional():
    create = SessionCreate()
    assert create.title is None and create.model is None and create.system_prompt is None


def test_session_out_requires_core_fields():
    with pytest.raises(ValidationError):
        SessionOut()


def test_session_out_roundtrip():
    out = SessionOut(id=uuid.uuid4(), title="t", model="m", created_at=NOW, updated_at=NOW)
    assert out.message_count == 0


def test_session_detail_defaults_messages():
    detail = SessionDetail(id=uuid.uuid4(), title="t", model="m", created_at=NOW, updated_at=NOW)
    assert detail.messages == []
    assert detail.system_prompt is None


def test_skill_invoke_request_defaults_arguments():
    assert SkillInvokeRequest(name="echo").arguments == {}


def test_skill_invoke_response_shape():
    assert SkillInvokeResponse(name="echo", result="ok").model_dump() == {
        "name": "echo",
        "result": "ok",
    }


def test_skill_info_requires_name_and_description():
    with pytest.raises(ValidationError):
        SkillInfo(name="echo")
    info = SkillInfo(name="echo", description="回显")
    assert info.parameters == {}
    assert info.source == "builtin"


def test_rag_query_request_defaults():
    req = QueryRequest(query="RAG 参数")
    assert req.top_k == 5
    assert req.score_threshold == 0.5
    assert req.filters is None


def test_rag_query_hit_defaults_metadata():
    assert QueryHit(text="t", source="s", score=0.9).metadata == {}


def test_rag_query_response_requires_hits():
    with pytest.raises(ValidationError):
        QueryResponse(query="q", count=0)


def test_rag_upload_response_requires_a_doc():
    with pytest.raises(ValidationError):
        UploadResponse()


def test_mcp_schemas_are_importable():
    assert MCPServerStatus is not None
    assert MCPServersResponse is not None
    assert MCPRestartResponse is not None
