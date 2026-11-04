import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import settings
from app.db import SessionLocal, get_session
from app.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    MessageCreate,
    UsageOut,
)
from app.services.context import build_messages
from app.services.llm import friendly_error, stream_chat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    session: AsyncSession = Depends(get_session),
):
    return await crud.create_conversation(session, body.title, body.system_prompt)


@router.get("", response_model=list[ConversationOut])
async def list_conversations(session: AsyncSession = Depends(get_session)):
    return await crud.list_conversations(session)


@router.get("/{conv_id}", response_model=ConversationDetail)
async def get_conversation(
    conv_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    conv = await crud.get_conversation_with_messages(session, conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Диалог не найден")
    return conv


@router.delete("/{conv_id}", status_code=204)
async def delete_conversation(
    conv_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    deleted = await crud.delete_conversation(session, conv_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Диалог не найден")


@router.get("/{conv_id}/usage", response_model=UsageOut)
async def get_usage(
    conv_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    conv = await crud.get_conversation(session, conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Диалог не найден")
    return await crud.get_usage(session, conv_id)


def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


_background: set[asyncio.Task] = set()


async def save_reply(conv_id: uuid.UUID, text: str, usage: dict) -> None:
    async with SessionLocal() as s:
        await crud.add_message(
            s, conv_id, "assistant", text,
            tokens_in=usage.get("in"), tokens_out=usage.get("out"),
        )


def save_in_background(coro) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)  # держим ссылку, иначе задачу может собрать GC
    task.add_done_callback(_background.discard)


@router.post("/{conv_id}/messages")
async def send_message(
    conv_id: uuid.UUID,
    body: MessageCreate,
    session: AsyncSession = Depends(get_session),
):
    conv = await crud.get_conversation(session, conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Диалог не найден")

    history = await crud.get_history(session, conv_id)
    if not history:
        await crud.set_title(session, conv_id, body.content[:40])

    messages = build_messages(
        conv.system_prompt, history, body.content, settings.max_context_tokens
    )
    await crud.add_message(session, conv_id, "user", body.content)

    async def event_stream():
        parts: list[str] = []
        usage: dict = {}
        started = time.perf_counter()
        try:
            async for ev in stream_chat(messages):
                if ev["type"] == "token":
                    parts.append(ev["text"])
                elif ev["type"] == "usage":
                    usage = ev
                yield sse(ev)
            yield sse({"type": "done"})
        except Exception as e:
            logger.exception("Ошибка генерации, диалог %s", conv_id)
            yield sse({"type": "error", "message": friendly_error(e)})
        finally:
            reply = "".join(parts)
            logger.info(
                "chat conv=%s model=%s in=%s out=%s time=%.2fs",
                conv_id, settings.llm_model,
                usage.get("in"), usage.get("out"),
                time.perf_counter() - started,
            )
            if reply:
                save_in_background(save_reply(conv_id, reply, usage))  # без await

    return StreamingResponse(event_stream(), media_type="text/event-stream")