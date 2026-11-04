import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Conversation, Message


async def create_conversation(
    session: AsyncSession,
    title: str = "Новый диалог",
    system_prompt: str | None = None,
) -> Conversation:
    conv = Conversation(title=title, system_prompt=system_prompt)
    session.add(conv)
    await session.commit()
    return conv


async def get_conversation(session: AsyncSession, conv_id: uuid.UUID) -> Conversation | None:
    return await session.get(Conversation, conv_id)


async def get_conversation_with_messages(
    session: AsyncSession, conv_id: uuid.UUID
) -> Conversation | None:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.id == conv_id)
        .options(selectinload(Conversation.messages))
    )
    return result.scalar_one_or_none()


async def list_conversations(session: AsyncSession) -> list[Conversation]:
    result = await session.execute(
        select(Conversation).order_by(Conversation.created_at.desc())
    )
    return list(result.scalars().all())


async def delete_conversation(session: AsyncSession, conv_id: uuid.UUID) -> bool:
    conv = await session.get(Conversation, conv_id)
    if conv is None:
        return False
    await session.delete(conv)
    await session.commit()
    return True


async def set_title(session: AsyncSession, conv_id: uuid.UUID, title: str) -> None:
    conv = await session.get(Conversation, conv_id)
    if conv is not None:
        conv.title = title
        await session.commit()


async def get_history(session: AsyncSession, conv_id: uuid.UUID) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.id)
    )
    return list(result.scalars().all())


async def add_message(
    session: AsyncSession,
    conv_id: uuid.UUID,
    role: str,
    content: str,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
) -> Message:
    msg = Message(
        conversation_id=conv_id,
        role=role,
        content=content,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )
    session.add(msg)
    await session.commit()
    return msg


async def get_usage(session: AsyncSession, conv_id: uuid.UUID) -> dict:
    result = await session.execute(
        select(
            func.count(Message.id),
            func.coalesce(func.sum(Message.tokens_in), 0),
            func.coalesce(func.sum(Message.tokens_out), 0),
        ).where(Message.conversation_id == conv_id)
    )
    count, tokens_in, tokens_out = result.one()
    return {
        "messages_count": count,
        "tokens_in": int(tokens_in),
        "tokens_out": int(tokens_out),
        "tokens_total": int(tokens_in) + int(tokens_out),
    }