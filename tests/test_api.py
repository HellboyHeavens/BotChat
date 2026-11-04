import json

from tests.conftest import wait_background


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block[6:]))
    return events


async def create_conv(client, **kwargs) -> str:
    r = await client.post("/conversations", json=kwargs)
    assert r.status_code == 201
    return r.json()["id"]


async def test_create_and_list(client):
    await create_conv(client, title="Тест")
    r = await client.get("/conversations")
    assert r.status_code == 200
    assert [c["title"] for c in r.json()] == ["Тест"]


async def test_sse_format_and_saving(client):
    conv_id = await create_conv(client)

    r = await client.post(f"/conversations/{conv_id}/messages", json={"content": "Привет"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    events = parse_sse(r.text)
    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert "".join(tokens) == "Привет!"
    assert events[-1] == {"type": "done"}

    await wait_background()
    conv = (await client.get(f"/conversations/{conv_id}")).json()
    assert [(m["role"], m["content"]) for m in conv["messages"]] == [
        ("user", "Привет"),
        ("assistant", "Привет!"),
    ]


async def test_memory_history_goes_to_llm(client, llm_calls):
    conv_id = await create_conv(client, system_prompt="Отвечай кратко.")

    await client.post(f"/conversations/{conv_id}/messages", json={"content": "Меня зовут Артём"})
    await wait_background()
    await client.post(f"/conversations/{conv_id}/messages", json={"content": "Как меня зовут?"})

    second_call = llm_calls[1]
    assert second_call[0] == {"role": "system", "content": "Отвечай кратко."}
    assert {"role": "user", "content": "Меня зовут Артём"} in second_call
    assert {"role": "assistant", "content": "Привет!"} in second_call
    assert second_call[-1] == {"role": "user", "content": "Как меня зовут?"}


async def test_title_from_first_message(client):
    conv_id = await create_conv(client)
    await client.post(f"/conversations/{conv_id}/messages", json={"content": "Первый вопрос"})
    await wait_background()
    conv = (await client.get(f"/conversations/{conv_id}")).json()
    assert conv["title"] == "Первый вопрос"


async def test_usage(client):
    conv_id = await create_conv(client)
    await client.post(f"/conversations/{conv_id}/messages", json={"content": "Привет"})
    await wait_background()

    usage = (await client.get(f"/conversations/{conv_id}/usage")).json()
    assert usage == {
        "messages_count": 2,
        "tokens_in": 10,
        "tokens_out": 3,
        "tokens_total": 13,
    }


async def test_unknown_conversation_returns_404(client):
    fake_id = "00000000-0000-0000-0000-000000000000"
    assert (await client.get(f"/conversations/{fake_id}")).status_code == 404
    assert (await client.delete(f"/conversations/{fake_id}")).status_code == 404
    r = await client.post(f"/conversations/{fake_id}/messages", json={"content": "x"})
    assert r.status_code == 404


async def test_delete_removes_conversation_and_messages(client):
    conv_id = await create_conv(client)
    await client.post(f"/conversations/{conv_id}/messages", json={"content": "Привет"})
    await wait_background()

    assert (await client.delete(f"/conversations/{conv_id}")).status_code == 204
    assert (await client.get(f"/conversations/{conv_id}")).status_code == 404
    assert (await client.get("/conversations")).json() == []


async def test_llm_error_is_sent_as_event(client, monkeypatch):
    from app.routers import chat as chat_router

    async def broken_stream(messages):
        raise RuntimeError("boom")
        yield  # делает функцию генератором

    monkeypatch.setattr(chat_router, "stream_chat", broken_stream)

    conv_id = await create_conv(client)
    r = await client.post(f"/conversations/{conv_id}/messages", json={"content": "Привет"})
    assert r.status_code == 200  # статус уже отправлен, ошибка идёт событием

    events = parse_sse(r.text)
    assert events[-1]["type"] == "error"

    await wait_background()
    conv = (await client.get(f"/conversations/{conv_id}")).json()
    # вопрос сохранён, пустой ответ ассистента не сохраняется
    assert [m["role"] for m in conv["messages"]] == ["user"]