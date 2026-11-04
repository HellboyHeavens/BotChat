<div align="center">

# BotChatApi

**A streaming chatbot backend with persistent memory.**
FastAPI · PostgreSQL · Server-Sent Events · any OpenAI-compatible LLM

![Python](https://img.shields.io/badge/python-3.12-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)
![Tests](https://img.shields.io/badge/tests-14%20passing-brightgreen)

![Screenshot](docs/screenshot.png)

</div>

---

## Overview

BotChatApi is a small but production-minded chat service. Conversations are stored in PostgreSQL, so the bot remembers what you told it even after a server restart. Replies are streamed token by token over SSE, and the LLM provider is fully swappable through environment variables: use Groq's free tier, a local Ollama model, OpenRouter, or any other OpenAI-compatible API without touching the code.

It was built as a hands-on project for learning how real LLM applications are put together: context management, streaming, error handling, migrations, tests, and containerized deployment.

## Features

- **Persistent memory.** Conversations and messages live in PostgreSQL and survive restarts.
- **Streaming replies.** Responses arrive token by token via Server-Sent Events, with a Stop button in the UI.
- **Context management.** History is trimmed from the oldest messages to fit a configurable token budget, and it never starts with an orphaned assistant reply.
- **Provider-agnostic.** One OpenAI-compatible client. Switch between Groq, Ollama, OpenRouter, or a paid API by editing `.env`.
- **Token accounting.** Per-conversation usage totals, with a fallback estimate when a provider doesn't report usage while streaming.
- **Resilient by design.** Exponential-backoff retries on rate limits and 5xx errors, request timeouts, friendly error events, and structured logging with latency and token counts.
- **Safe on disconnect.** If the client closes the tab or hits Stop, the partial reply is still saved, via a background task that cancellation can't interrupt.
- **Auto-titled chats.** A conversation is named after its first message.
- **Migrations and tests.** Alembic for schema changes, pytest suite that runs without network access or a real database.
- **One-command deployment.** Docker/Podman Compose runs the app and Postgres together; migrations apply on startup.

## Architecture

```mermaid
flowchart LR
    UI[Browser UI] -->|POST /messages| API[FastAPI router]
    API --> CTX[Context builder]
    CTX -->|history| DB[(PostgreSQL)]
    CTX --> LLM[LLM layer]
    LLM -->|OpenAI-compatible API| P[Groq / Ollama / OpenRouter]
    LLM -->|tokens| API
    API -->|SSE stream| UI
    API -->|save reply in background| DB
```

| Module | Responsibility |
|---|---|
| `app/services/llm.py` | The only code that knows about the provider: streaming, retries, timeouts, usage |
| `app/services/context.py` | Builds the message list for the model within the token budget |
| `app/routers/chat.py` | REST + SSE endpoints, background persistence of replies |
| `app/crud.py` | All database access in one place |
| `app/models.py`, `alembic/` | ORM models and schema migrations |
| `app/static/` | Dependency-free vanilla JS chat interface |

## Quick start

### Run with Docker or Podman

```bash
git clone https://github.com/YOUR_USERNAME/BotChatApi.git
cd BotChatApi

cp .env.example .env        # then put your API key into .env
docker compose up -d --build    # or: podman compose up -d --build
```

Open **http://localhost:8000**. The database schema is created automatically on startup.

### Run locally for development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

docker compose up -d db         # just the database
alembic upgrade head            # apply migrations
uvicorn app.main:app --reload
```

## Configuration

All settings come from environment variables (or `.env`):

| Variable | Description | Example |
|---|---|---|
| `LLM_BASE_URL` | OpenAI-compatible endpoint | `https://api.groq.com/openai/v1` |
| `LLM_API_KEY` | Provider API key | `gsk_...` |
| `LLM_MODEL` | Model name at that provider | `openai/gpt-oss-120b` |
| `DATABASE_URL` | Async SQLAlchemy URL | `postgresql+asyncpg://chat:chat@localhost:5432/chat` |
| `MAX_CONTEXT_TOKENS` | Token budget for history sent to the model | `6000` |

### Choosing a provider

| Provider | `LLM_BASE_URL` | Notes |
|---|---|---|
| Groq | `https://api.groq.com/openai/v1` | Free tier with rate limits, no card required |
| Ollama | `http://localhost:11434/v1` | Fully local, set `LLM_API_KEY=ollama` |
| OpenRouter | `https://openrouter.ai/api/v1` | Includes several free models |

Free-tier limits change over time, so check your provider's current terms.

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/conversations` | Create a conversation (optional `title`, `system_prompt`) |
| `GET` | `/conversations` | List conversations, newest first |
| `GET` | `/conversations/{id}` | Get a conversation with all its messages |
| `DELETE` | `/conversations/{id}` | Delete a conversation and its messages |
| `GET` | `/conversations/{id}/usage` | Message count and token totals |
| `POST` | `/conversations/{id}/messages` | Send a message, receive the reply as an SSE stream |
| `GET` | `/health` | Liveness check |

Interactive docs are available at `/docs`.

### Streaming protocol

`POST /conversations/{id}/messages` returns `text/event-stream`. Each event is a JSON object on a `data:` line:

```
data: {"type": "token", "text": "Hel"}

data: {"type": "token", "text": "lo!"}

data: {"type": "usage", "in": 58, "out": 12}

data: {"type": "done"}
```

| Event | Meaning |
|---|---|
| `token` | A chunk of generated text |
| `usage` | Input/output token counts (`"estimated": true` if the provider didn't report them) |
| `done` | The reply is complete |
| `error` | Generation failed; includes a human-readable `message` |

Try it from the terminal:

```bash
ID=$(curl -s -X POST localhost:8000/conversations \
  -H "Content-Type: application/json" -d '{}' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

curl -N -X POST localhost:8000/conversations/$ID/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "Explain SSE in one sentence"}'
```

## Testing

```bash
python3 -m pytest -v
```

The suite (14 tests) needs no network and no Postgres. The LLM is replaced by a fake generator and the database by in-memory SQLite. It covers context trimming rules, the SSE format, reply persistence, conversation memory reaching the model, usage totals, 404 handling, cascade deletes, and error events.

## Database migrations

```bash
alembic revision --autogenerate -m "describe the change"   # generate
alembic upgrade head                                       # apply
alembic downgrade -1                                       # roll back one step
```

Always review the generated migration before applying it, and generate it against a database that is already at the latest revision.

## Project structure

```
.
├── app/
│   ├── main.py              # app setup, static files, logging
│   ├── config.py            # settings from environment
│   ├── db.py                # async engine and sessions
│   ├── models.py            # Conversation, Message
│   ├── schemas.py           # request/response models
│   ├── crud.py              # database operations
│   ├── routers/chat.py      # endpoints and SSE streaming
│   ├── services/
│   │   ├── llm.py           # provider layer: streaming, retry, errors
│   │   └── context.py       # token-budgeted history builder
│   └── static/index.html    # chat UI
├── alembic/                 # migrations
├── tests/                   # pytest suite
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Design notes

- **Provider isolation.** Everything provider-specific lives in `llm.py`. The rest of the app only sees two event shapes, `token` and `usage`.
- **Retries wrap only the connection.** A stream that has already started is never retried, which would duplicate text for the client.
- **Persistence outside the request.** The assistant reply is saved from a background task rather than inside the streaming generator, because request cancellation can interrupt `await`s in a `finally` block.
- **Token estimation is approximate.** The context builder uses roughly four characters per token. Keep `MAX_CONTEXT_TOKENS` comfortably below the model's real window.

## Roadmap

- [ ] Conversation summaries instead of dropping old messages
- [ ] JWT authentication and per-user conversations
- [ ] Regenerate last response
- [ ] Export a conversation to Markdown
- [ ] RAG over uploaded documents (pgvector)

## License

MIT. See `LICENSE`.
