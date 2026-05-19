"""
app/core/interfaces.py
──────────────────────
LLM / STT / TTS 어댑터 추상 클래스.
새 공급자를 추가할 때 이 인터페이스만 구현하면 된다.
"""
from abc import ABC, abstractmethod
from typing import Callable, Awaitable


# ── LLM ──────────────────────────────────────────────────────────────
class LLMProvider(ABC):
    """
    LLM 어댑터 인터페이스.
    대화 히스토리를 받아 다음 응답 텍스트를 반환한다.
    """

    @abstractmethod
    async def chat(self, history: list[dict]) -> str:
        """
        history: [{"role": "user"|"assistant", "content": "..."}]
        반환: 에이전트 응답 텍스트
        """

    async def chat_with_system(self, system: str, history: list[dict]) -> str:
        """
        시스템 프롬프트를 동적으로 지정해 호출.
        기본 구현: 서브클래스에서 오버라이드 가능.
        """
        # 기본 구현: history 앞에 system 메시지 삽입 방식으로 처리
        # Gemini/Claude 각 어댑터에서 오버라이드해 네이티브 system 파라미터 사용
        nl = "\n"
        msg = f"[시스템 지시]{nl}{system}{nl}{nl}[사용자 메시지]{nl}{history[-1]['content']}"
        augmented = [{"role": "user", "content": msg}]
        return await self.chat(augmented)


# ── STT ──────────────────────────────────────────────────────────────
class STTProvider(ABC):
    """
    실시간 STT 어댑터 인터페이스.
    Twilio μ-law 8kHz PCM 청크를 받아 텍스트로 변환한다.
    """

    @abstractmethod
    async def connect(
        self,
        on_utterance: Callable[[str], Awaitable[None]],
    ) -> None:
        """
        STT 서비스에 연결.
        on_utterance: 발화가 완성되면 호출되는 콜백 (텍스트 전달)
        """

    @abstractmethod
    async def send_audio(self, chunk: bytes) -> None:
        """μ-law 오디오 청크 전달"""

    @abstractmethod
    async def close(self) -> None:
        """연결 종료"""


# ── TTS ──────────────────────────────────────────────────────────────
class TTSProvider(ABC):
    """
    TTS 어댑터 인터페이스.
    텍스트를 μ-law 8kHz PCM bytes로 반환한다.
    """

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """
        텍스트 → μ-law 8kHz PCM bytes.
        반환값은 Twilio Media Stream에 그대로 전송 가능.
        """
