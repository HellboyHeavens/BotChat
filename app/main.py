from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import chat

app = FastAPI(title="BotChatApi")
app.include_router(chat.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


# mount ВСЕГДА в самом конце, после всех роутов
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")