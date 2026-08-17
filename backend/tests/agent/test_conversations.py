"""Agent 会话持久化、隔离和 SSE 关键契约。"""

from uuid import uuid4

import pytest
from sqlalchemy import delete

from yitu.agent.model_adapter import FixedModelAdapter
from yitu.agent.models import AgentConversation
from yitu.agent.service import AgentConversationService
from yitu.agent.sse import agent_message_events
from yitu.demo.seed import seed_demo_users
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser
from yitu.platform.database import SessionFactory
from yitu.platform.errors import AppError

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_conversation_is_isolated_and_recovers_messages() -> None:
    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        owner_row = next(user for user in users if user.demo_key == "customer")
        other_row = next(user for user in users if user.demo_key == "operations")
        owner = CurrentUser(owner_row.id, Role.CUSTOMER, None)
        other = CurrentUser(other_row.id, Role.OPERATIONS_ADMIN, None)

    async with SessionFactory() as session:
        service = AgentConversationService(session)
        conversation = await service.create(owner, title="恢复测试")
        turn = await service.send_message(
            conversation.id,
            owner,
            "查询运单",
            FixedModelAdapter(),
        )

    # 新建会话和服务实例，模拟 API 进程重启后从数据库恢复。
    async with SessionFactory() as session:
        service = AgentConversationService(session)
        messages = await service.list_messages(conversation.id, owner)
        assert [message.id for message in messages] == [
            turn.user_message.id,
            turn.assistant_message.id,
        ]
        with pytest.raises(AppError) as error:
            await service.get_owned(conversation.id, other)
        assert error.value.code == "AGENT_CONVERSATION_NOT_FOUND"

    async with SessionFactory() as session, session.begin():
        await session.execute(
            delete(AgentConversation).where(AgentConversation.id == conversation.id)
        )


async def test_sse_reconnect_returns_only_newer_messages() -> None:
    async with SessionFactory() as session, session.begin():
        users = await seed_demo_users(session)
        owner_row = next(user for user in users if user.demo_key == "customer")
        owner = CurrentUser(owner_row.id, Role.CUSTOMER, None)

    async with SessionFactory() as session:
        service = AgentConversationService(session)
        conversation = await service.create(owner, title=f"SSE-{uuid4()}")
        turn = await service.send_message(
            conversation.id,
            owner,
            "续传测试",
            FixedModelAdapter(),
        )

    async with SessionFactory() as session:
        events = [
            event
            async for event in agent_message_events(
                session,
                conversation.id,
                last_event_id=turn.user_message.id,
            )
        ]

    assert all(str(turn.user_message.id) not in event for event in events)
    assert any(str(turn.assistant_message.id) in event for event in events)
    assert events[-1] == ": heartbeat\n\n"

    async with SessionFactory() as session, session.begin():
        await session.execute(
            delete(AgentConversation).where(AgentConversation.id == conversation.id)
        )
