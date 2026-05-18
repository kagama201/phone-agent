"""
app/core/text_agent.py
───────────────────────
통신망(Twilio), STT, TTS 없이 텍스트 입출력만으로
에이전트 핵심 로직(LLM 대화 흐름, 시스템 프롬프트, 히스토리)을 테스트.

CallAgent와 동일한 LLMProvider를 사용하므로
여기서 검증된 동작은 실제 통화에서도 동일하게 동작한다.
"""
import logging

from app.config import settings
from app.core.interfaces import LLMProvider

log = logging.getLogger(__name__)


class TextAgent:
    """
    세션 하나 = 통화 하나에 대응.
    session_id로 구분하며 대화 히스토리를 메모리에 유지.
    """

    def __init__(self, session_id: str, llm: LLMProvider):
        self.session_id = session_id
        self._llm = llm
        self._history: list[dict] = []
        log.info("[%s] TextAgent 시작 (LLM: %s)", session_id, settings.llm_provider)

    async def greet(self) -> str:
        """첫 인사 — CallAgent.start()의 첫 speak()와 동일한 텍스트"""
        greeting = "안녕하세요! AI 상담사 아리입니다. 무엇을 도와드릴까요?"
        self._history.append({"role": "assistant", "content": greeting})
        return greeting

    async def chat(self, user_text: str) -> str:
        """사용자 입력 → LLM 응답 반환"""
        log.info("[%s] 사용자: %s", self.session_id, user_text)
        self._history.append({"role": "user", "content": user_text})

        reply = await self._llm.chat(self._history)

        log.info("[%s] 에이전트: %s", self.session_id, reply)
        self._history.append({"role": "assistant", "content": reply})
        return reply

    def get_history(self) -> list[dict]:
        return list(self._history)

    def reset(self) -> None:
        """히스토리 초기화 — 새 통화 시뮬레이션"""
        self._history = []
        log.info("[%s] 히스토리 초기화", self.session_id)
