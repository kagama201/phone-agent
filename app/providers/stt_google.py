"""
app/providers/stt_google.py
────────────────────────────
Google Cloud STT 스트리밍 어댑터.

핵심 변경:
  - single_utterance=True 제거 → 연속 대화 가능
  - 침묵 타임아웃(1.5초) 직접 구현 → is_final 안 와도 발화 확정
  - 중간 인식 텍스트가 1.5초 동안 변하지 않으면 발화 완료로 처리
"""
import asyncio
import logging
import queue
import threading
import time
from typing import Callable, Awaitable

from google.cloud import speech

from app.core.interfaces import STTProvider

log = logging.getLogger(__name__)

STREAM_RESTART_SECS = 240
MAX_QUEUE_SIZE      = 200
SILENCE_TIMEOUT     = 1.5   # 초 — 중간 인식 후 이 시간 동안 변화 없으면 발화 완료


class GoogleSTT(STTProvider):

    def __init__(self):
        self._client  = speech.SpeechClient()
        self._audio_q: queue.Queue[bytes | None] = queue.Queue(maxsize=MAX_QUEUE_SIZE)
        self._on_utterance: Callable[[str], Awaitable[None]] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running  = False
        self._thread: threading.Thread | None = None

    async def connect(self, on_utterance: Callable[[str], Awaitable[None]]) -> None:
        self._on_utterance = on_utterance
        self._loop = asyncio.get_event_loop()
        self._running = True
        self._thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._thread.start()
        log.info("Google STT 시작")

    async def send_audio(self, chunk: bytes) -> None:
        if not self._running:
            return
        try:
            self._audio_q.put_nowait(chunk)
        except queue.Full:
            try:
                self._audio_q.get_nowait()
                self._audio_q.put_nowait(chunk)
            except queue.Empty:
                pass

    async def close(self) -> None:
        self._running = False
        try:
            self._audio_q.put_nowait(None)
        except queue.Full:
            pass
        if self._thread:
            self._thread.join(timeout=3)
        log.info("Google STT 종료")

    def _stream_loop(self):
        backoff = 1
        while self._running:
            try:
                self._run_once()
                backoff = 1
            except Exception as e:
                if not self._running:
                    break
                log.error("STT 스트림 오류 (%.0f초 후 재시작): %s", backoff, e)
                time.sleep(backoff)
                backoff = min(backoff * 2, 16)

    def _run_once(self):
        start = time.time()

        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.MULAW,
            sample_rate_hertz=8000,
            language_code="ko-KR",
            enable_automatic_punctuation=True,
            model="default",
        )
        streaming_config = speech.StreamingRecognitionConfig(
            config=config,
            interim_results=True,
        )

        def audio_gen():
            count = 0
            while self._running:
                if time.time() - start >= STREAM_RESTART_SECS:
                    log.info("STT 스트림 갱신")
                    return
                try:
                    chunk = self._audio_q.get(timeout=1)
                    if chunk is None:
                        return
                    count += 1
                    if count == 1:
                        log.info("STT 첫 오디오 수신")
                    if count % 500 == 0:
                        log.info("STT 오디오 누적: %d 청크", count)
                    yield speech.StreamingRecognizeRequest(audio_content=chunk)
                except queue.Empty:
                    continue

        log.info("STT streaming_recognize 시작")
        responses = self._client.streaming_recognize(streaming_config, audio_gen())
        self._process(responses)

    def _process(self, responses):
        """
        is_final=True가 오면 즉시 발화 처리.
        안 오면 SILENCE_TIMEOUT 초 동안 텍스트 변화 없으면 발화 완료로 처리.
        """
        last_interim   = ""
        last_change_t  = time.time()
        silence_timer  = None

        def _fire(text: str):
            """발화 콜백 호출"""
            if text and self._on_utterance and self._loop:
                log.info("STT 발화: %s", text)
                asyncio.run_coroutine_threadsafe(
                    self._on_utterance(text), self._loop
                )

        def _check_silence():
            """별도 스레드에서 침묵 타임아웃 감시"""
            nonlocal last_interim, last_change_t
            while self._running:
                time.sleep(0.1)
                if last_interim and (time.time() - last_change_t) >= SILENCE_TIMEOUT:
                    text = last_interim
                    last_interim  = ""
                    last_change_t = time.time()
                    _fire(text)

        # 침묵 감시 스레드 시작
        silence_t = threading.Thread(target=_check_silence, daemon=True)
        silence_t.start()

        resp_count = 0
        try:
            for response in responses:
                if not self._running:
                    break
                resp_count += 1
                if resp_count == 1:
                    log.info("STT 첫 응답 수신")

                for result in response.results:
                    if not result.alternatives:
                        continue
                    transcript = result.alternatives[0].transcript.strip()
                    if not transcript:
                        continue

                    if result.is_final:
                        # is_final이 오면 즉시 처리
                        last_interim  = ""
                        last_change_t = time.time()
                        _fire(transcript)
                    else:
                        # 중간 결과 — 침묵 타임아웃으로 처리
                        if transcript != last_interim:
                            last_interim  = transcript
                            last_change_t = time.time()
                            log.info("STT 중간 인식: %s", transcript)
        finally:
            log.info("STT _process 종료 (총 응답: %d)", resp_count)
