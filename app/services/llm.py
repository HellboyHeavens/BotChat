import logging
import time

from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)

# max_retries=0: повторами управляем сами через tenacity, иначе они удвоятся
client = AsyncOpenAI(
    base_url=settings.llm_base_url,
    api_key=settings.llm_api_key,
    timeout=60,
    max_retries=0,
)


def _is_retryable(e: BaseException) -> bool:
    if isinstance(e, (RateLimitError, APIConnectionError)):  # 429, сеть, таймаут
        return True
    return isinstance(e, APIStatusError) and e.status_code >= 500


def friendly_error(e: Exception) -> str:
    if isinstance(e, RateLimitError):
        return "Превышен лимит запросов, подождите минуту"
    if isinstance(e, AuthenticationError):
        return "Неверный API-ключ"
    if isinstance(e, APIConnectionError):
        return "Не удалось связаться с моделью"
    return "Ошибка модели"


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _open_stream(messages: list[dict]):
    return await client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
    )


async def stream_chat(messages: list[dict]):
    started = time.perf_counter()
    stream = await _open_stream(messages)

    got_usage = False
    out_chars = 0
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            text = chunk.choices[0].delta.content
            out_chars += len(text)
            yield {"type": "token", "text": text}
        if getattr(chunk, "usage", None):
            got_usage = True
            yield {
                "type": "usage",
                "in": chunk.usage.prompt_tokens,
                "out": chunk.usage.completion_tokens,
            }

    if not got_usage:  # провайдер не прислал usage: грубая оценка
        in_chars = sum(len(m["content"]) for m in messages)
        yield {"type": "usage", "in": in_chars // 4, "out": out_chars // 4, "estimated": True}

    logger.info("LLM ответил за %.2f с", time.perf_counter() - started)