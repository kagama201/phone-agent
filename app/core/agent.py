"""
app/core/agent.py
──────────────────
한 통화(call_id)를 담당하는 AI 에이전트.
LLMProvider / STTProvider / TTSProvider 인터페이스에만 의존하므로
공급자를 교체해도 이 파일은 변경 불필요.
"""
import asyncio
import base64
import logging
from typing import Callable, Awaitable

from app.config import settings
from app.core.interfaces import LLMProvider, STTProvider, TTSProvider

log = logging.getLogger(__name__)


class CallAgent:
    def __init__(
        self,
        call_id: str,
        stream_sid: str,
        llm: LLMProvider,
        stt: STTProvider,
        tts: TTSProvider,
        send_audio_cb: Callable[[str, str], Awaitable[None]],
    ):
        self.call_id     = call_id
        self.stream_sid  = stream_sid
        self._llm        = llm
        self._stt        = stt
        self._tts        = tts
        self._send_audio = send_audio_cb   # (stream_sid, base64_mulaw)
        self._history: list[dict] = []
        self._speaking   = False   # TTS 재생 중엔 STT 무시 (에코 방지)

    # ── 시작 ───────────────────────────────────
    async def start(self) -> None:
        await self._stt.connect(on_utterance=self._on_utterance)
        log.info("[%s] 에이전트 시작 (LLM: %s)", self.call_id, settings.llm_provider)
        await self._speak("안녕하세요! AI 상담사 아리입니다. 무엇을 도와드릴까요?")

    # ── Twilio 오디오 청크 수신 ─────────────────
    async def receive_audio(self, payload_b64: str) -> None:
        if self._speaking:   # 에코 방지
            return
        await self._stt.send_audio(base64.b64decode(payload_b64))

    # ── 발화 완성 콜백 (STT → LLM) ─────────────
    async def _on_utterance(self, text: str) -> None:
        if self._speaking:
            return
        log.info("[%s] 사용자: %s", self.call_id, text)
        self._history.append({"role": "user", "content": text})
        await self._ask_llm()

    # ── LLM 호출 ───────────────────────────────
    async def _ask_llm(self) -> None:
        try:
            reply = await self._llm.chat(self._history)
            log.info("[%s] 에이전트: %s", self.call_id, reply)
            self._history.append({"role": "assistant", "content": reply})
            await self._speak(reply)
        except Exception as e:
            log.error("[%s] LLM 오류: %s", self.call_id, e)
            await self._speak("죄송합니다, 잠시 후 다시 말씀해주세요.")

    # ── TTS → Twilio 전송 ──────────────────────
    async def _speak(self, text: str) -> None:
        self._speaking = True
        try:
            mulaw = await self._tts.synthesize(text)
            chunk_size = 160 * 10   # 200ms 단위
            for i in range(0, len(mulaw), chunk_size):
                b64 = base64.b64encode(mulaw[i:i + chunk_size]).decode()
                await self._send_audio(self.stream_sid, b64)
                await asyncio.sleep(0)
        except Exception as e:
            log.error("[%s] TTS 오류: %s", self.call_id, e)
        finally:
            self._speaking = False

    # ── 종료 ───────────────────────────────────
    async def close(self) -> None:
        await self._stt.close()
        log.info("[%s] 에이전트 종료", self.call_id)
