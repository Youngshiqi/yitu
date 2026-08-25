"""工作流测试基础必须与开发数据库彻底隔离。"""

import json
from uuid import uuid4

import pytest
from conftest import require_test_database_url
from pydantic import ValidationError

from yitu.agent.workflow.contracts import (
    AssistantToolCall,
    WorkflowError,
)


def test_database_tests_reject_non_test_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "YITU_TEST_DATABASE_URL",
        "postgresql+asyncpg://user:pass@localhost/yitu",
    )

    with pytest.raises(RuntimeError, match="_test"):
        require_test_database_url()


def test_agent_tool_call_rejects_identity_and_quote_fields() -> None:
    with pytest.raises(ValidationError):
        AssistantToolCall(
            id="call-1",
            name="get_own_shipment",
            arguments={"user_id": str(uuid4()), "quote_id": str(uuid4())},
        )


def test_workflow_error_is_checkpoint_serializable() -> None:
    error = WorkflowError(
        code="QUOTE_EXPIRED",
        message="报价已失效",
        source_node="create_quote_node",
    )

    assert json.loads(error.model_dump_json())["retryable"] is False


def test_assistant_tool_call_rejects_identity_in_model_arguments() -> None:
    with pytest.raises(ValidationError, match="user_id"):
        AssistantToolCall(
            id="call-1",
            name="get_current_identity",
            arguments={"user_id": str(uuid4())},
        )
