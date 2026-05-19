"""
app/core/agent.py
──────────────────
한 통화(call_id)를 담당하는 AI 에이전트.
STT/LLM/TTS 각 단계에서 call_event_bus에 이벤트를 발행해
브라우저 모니터링 UI에 실시간으로 표시된다.
"""
import asyncio
import base64
import logging
from typing import Callable, Awaitable

from app.config import settings
from app.core.interfaces import LLMProvider, STTProvider, TTSProvider
from app.core.call_event_bus import bus

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
        phone: str = "",
    ):
        self.call_id     = call_id
        self.stream_sid  = stream_sid
        self._llm        = llm
        self._stt        = stt
        self._tts        = tts
        self._send_audio = send_audio_cb
        self._phone      = phone
        self._history: list[dict] = []
        self._speaking   = False

    # ── 시작 ───────────────────────────────────
    async def start(self) -> None:
        await bus.call_start(self.call_id, self._phone)
        await self._stt.connect(on_utterance=self._on_utterance)
        log.info("[%s] 에이전트 시작", self.call_id)

        from app.core.multi_agent import get_design
        design = get_design()
        try:
            greeting = await self._llm.chat_with_system(
                design.main.prompt,
                [{"role": "user", "content": "전화가 연결됐어. 첫 인사를 해줘. 한 문장으로."}],
            )
        except Exception:
            greeting = "안녕하세요! 무엇을 도와드릴까요?"

        await bus.publish(self.call_id, "agent", text=greeting, phase="greeting")
        await self._speak(greeting)

    # ── Twilio 오디오 수신 ──────────────────────
    async def receive_audio(self, payload_b64: str) -> None:
        if self._speaking:
            return
        await self._stt.send_audio(base64.b64decode(payload_b64))

    # ── STT 발화 완성 ───────────────────────────
    async def _on_utterance(self, text: str) -> None:
        if self._speaking:
            return
        log.info("[%s] 사용자: %s", self.call_id, text)
        # STT 결과 브라우저에 발행
        await bus.publish(self.call_id, "stt", text=text)
        self._history.append({"role": "user", "content": text})
        await self._ask_llm()

    # ── LLM 호출 ───────────────────────────────
    async def _ask_llm(self) -> None:
        try:
            # 멀티에이전트 실행 (스몰톡·서브결과·최종 모두 발행)
            from app.core.multi_agent import MultiAgentRunner, get_design
            design = get_design()
            runner = MultiAgentRunner()
            final_text = ""

            async for chunk in runner.run(
                self._history[-1]["content"],
                self._history[:-1],
                design,
            ):
                ctype = chunk.get("type")
                if ctype == "smalltalk":
                    await bus.publish(self.call_id, "smalltalk", text=chunk["text"])
                elif ctype == "sub_result":
                    await bus.publish(
                        self.call_id, "sub_result",
                        text=chunk["text"],
                        agent_id=chunk.get("meta", {}).get("agent_id", ""),
                        agent_name=chunk.get("meta", {}).get("agent_name", ""),
                    )
                elif ctype == "final":
                    final_text = chunk["text"]
                    await bus.publish(self.call_id, "agent", text=final_text, phase="reply")

            if final_text:
                self._history.append({"role": "assistant", "content": final_text})
                await self._speak(final_text)
            else:
                fallback = "죄송합니다, 잠시 후 다시 말씀해주세요."
                await bus.publish(self.call_id, "agent", text=fallback, phase="reply")
                await self._speak(fallback)

        except Exception as e:
            log.error("[%s] LLM 오류: %s", self.call_id, e)
            err_msg = "죄송합니다, 잠시 후 다시 말씀해주세요."
            await bus.publish(self.call_id, "agent", text=err_msg, phase="error")
            await self._speak(err_msg)

    # ── TTS → Twilio 전송 ──────────────────────
    async def _speak(self, text: str) -> None:
        self._speaking = True
        await bus.publish(self.call_id, "tts_start", text=text)
        try:
            mulaw = await self._tts.synthesize(text)
            # Twilio 권장: 160바이트(20ms) 단위로 전송
            # 너무 크게 보내면 버퍼 오버플로 → 무음 발생
            chunk_size = 160
            for i in range(0, len(mulaw), chunk_size):
                b64 = base64.b64encode(mulaw[i:i + chunk_size]).decode()
                await self._send_audio(self.stream_sid, b64)
                await asyncio.sleep(0.02)   # 20ms 간격 — 실시간 재생 속도 맞춤
        except Exception as e:
            log.error("[%s] TTS 오류: %s", self.call_id, e)
        finally:
            self._speaking = False
            await bus.publish(self.call_id, "tts_end")

    # ── 종료 ───────────────────────────────────
    async def close(self) -> None:
        await self._stt.close()
        await bus.call_end(self.call_id)
        log.info("[%s] 에이전트 종료", self.call_id)
