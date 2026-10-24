from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from openai import AsyncOpenAI

from backend.app.core.config import settings
from backend.app.services.data.models import Evidence
from backend.app.services.qa.prompts import SYSTEM_PROMPT, evidence_prompt


class LLMUnavailable(RuntimeError):
    pass


class DeepSeekLLM:
    def _client(self) -> AsyncOpenAI:
        if not settings.deepseek_api_key.strip():
            raise LLMUnavailable("DeepSeek API Key 未配置")
        return AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            timeout=settings.llm_timeout_seconds,
        )

    async def stream(
        self,
        question: str,
        hits: list[Evidence],
        history: list[tuple[str, str]],
    ) -> AsyncIterator[str]:
        client = self._client()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *[
                {"role": role, "content": content[:4000]}
                for role, content in history[-8:]
            ],
            {"role": "user", "content": evidence_prompt(question, hits)},
        ]
        stream = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=settings.llm_temperature,
            stream=True,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if content:
                yield content

    async def complete(
        self,
        question: str,
        hits: list[Evidence],
        history: list[tuple[str, str]],
    ) -> str:
        client = self._client()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *[
                {"role": role, "content": content[:4000]}
                for role, content in history[-8:]
            ],
            {"role": "user", "content": evidence_prompt(question, hits)},
        ]
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=settings.llm_temperature,
            stream=False,
        )
        return response.choices[0].message.content or ""


@lru_cache(maxsize=1)
def get_llm() -> DeepSeekLLM:
    return DeepSeekLLM()
