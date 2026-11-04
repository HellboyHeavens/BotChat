import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app
from app.routers import chat as chat_router


@pytest.fixture
def llm_calls():
    """Сюда фейковая модель записывает все списки сообщений, которые ей отправили."""
    return []


@pytest_asyncio.fixture
async def client(monkeypatch, llm_calls):
    # база в памяти: быстро, без Postgres
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    TestSession = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session():
        async with TestSession() as session:
            yield session

    async def fake_stream_chat(messages):
        llm_calls.append(messages)
        for t in ["При", "вет", "!"]:
            yield {"type": "token", "text": t}
        yield {"type": "usage", "in": 10, "out": 3}

    app.dependency_overrides[get_session] = override_get_session
    # фоновое сохранение ответа использует SessionLocal напрямую, подменяем и его
    monkeypatch.setattr(chat_router, "SessionLocal", TestSession)
    monkeypatch.setattr(chat_router, "stream_chat", fake_stream_chat)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
    await engine.dispose()


async def wait_background():
    """Ответ ассистента сохраняется фоновой задачей: дожидаемся её."""
    if chat_router._background:
        await asyncio.gather(*chat_router._background)