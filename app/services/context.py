def estimate_tokens(text: str) -> int:
    # грубая оценка: примерно 4 символа на токен, плюс накладные расходы на сообщение
    return len(text) // 4 + 4


def build_messages(system_prompt, history, new_message: str, limit: int) -> list[dict]:
    """Собирает список сообщений для LLM.

    system_prompt: строка или None
    history: список объектов Message из БД (в порядке добавления)
    new_message: текст нового сообщения пользователя
    limit: максимум токенов на весь контекст
    """
    system = [{"role": "system", "content": system_prompt}] if system_prompt else []
    new = {"role": "user", "content": new_message}

    # system-промпт и новое сообщение всегда остаются, считаем их сразу
    used = sum(estimate_tokens(m["content"]) for m in system + [new])

    kept: list[dict] = []
    for m in reversed(history):  # идём с конца: свежие сообщения важнее
        cost = estimate_tokens(m.content)
        if used + cost > limit:
            break
        kept.append({"role": m.role, "content": m.content})
        used += cost
    kept.reverse()

    # история не должна начинаться с ответа ассистента
    while kept and kept[0]["role"] != "user":
        kept.pop(0)

    return system + kept + [new]