from types import SimpleNamespace

from app.services.context import build_messages, estimate_tokens


def msg(role, content):
    return SimpleNamespace(role=role, content=content)


def test_system_and_new_message_always_present():
    result = build_messages("sys", [], "hi", 1000)
    assert result == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]


def test_no_system_prompt():
    result = build_messages(None, [], "hi", 1000)
    assert result == [{"role": "user", "content": "hi"}]


def test_history_keeps_order():
    history = [msg("user", "q1"), msg("assistant", "a1")]
    result = build_messages(None, history, "q2", 1000)
    assert [m["content"] for m in result] == ["q1", "a1", "q2"]


def test_limit_drops_oldest_messages():
    history = [
        msg("user", "a" * 100),
        msg("assistant", "b" * 100),
        msg("user", "c" * 100),
        msg("assistant", "d" * 100),
    ]
    # каждое сообщение ~29 токенов, system и новое ~8: влезают только два последних
    result = build_messages("s", history, "n", 70)
    contents = [m["content"] for m in result]
    assert "a" * 100 not in contents
    assert "b" * 100 not in contents
    assert "c" * 100 in contents
    assert "d" * 100 in contents


def test_history_never_starts_with_assistant():
    history = [
        msg("user", "a" * 100),
        msg("assistant", "b" * 100),
        msg("user", "c" * 100),
        msg("assistant", "d" * 100),
    ]
    # влезает только последний ответ ассистента: он остался бы без вопроса
    result = build_messages("s", history, "n", 45)
    assert [m["role"] for m in result] == ["system", "user"]


def test_total_stays_within_limit():
    history = [msg("user" if i % 2 == 0 else "assistant", "x" * 200) for i in range(20)]
    limit = 300
    result = build_messages("sys", history, "new", limit)
    total = sum(estimate_tokens(m["content"]) for m in result)
    assert total <= limit