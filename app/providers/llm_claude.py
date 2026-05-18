"""
app/providers/llm_claude.py
────────────────────────────
Anthropic Claude LLM 어댑터.
LLM_PROVIDER=claude 로 설정하면 Gemini 대신 이 어댑터가 사용된다.
"""
import logging

from anthropic import AsyncAnthropic

from app.config import settings
from app.core.interfaces import LLMProvider

log = logging.getLogger(__name__)


class ClaudeLLM(LLMProvider):
    def __init__(self):
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def chat(self, history: list[dict]) -> str:
        resp = await self._client.messages.create(
            model=settings.claude_model,
            max_tokens=300,
            system=settings.system_prompt,
            messages=history,
        )
        reply = resp.content[0].text.strip()
        log.debug("Claude 응답: %s", reply)
        return reply
