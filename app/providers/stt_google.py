"""
app/providers/stt_google.py
────────────────────────────
Google Cloud STT 스트리밍 어댑터.

주요 특이사항:
  - Google STT 단일 스트림 최대 5분 → 자동 재시작
  - TTS 재생 중에도 STT 스트림은 유지 (오디오만 무시)
  - gRPC 동기 스트림을 별도 스레드에서 실행
"""
import asyncio
import logging
import queue
import threading
from typing import Callable, Awaitable

from google.cloud import speech

from app.core.interfaces import STTProvider

log = logging.getLogger(__name__)

STREAM_RESTART_SECS = 240   # 4분마다 재시작 (Google 5분 제한 전)


class GoogleSTT(STTProvider):

    def __init__(self):
        self._client  = speech.SpeechClient()
        self._audio_q: queue.Queue[bytes | None] = queue.Queue()
        self._on_utterance: Callable[[str], Awaitable[None]] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running  = False
        self._thread: threading.Thread | None = None

    async def connect(self, on_utterance: Callable[[str], Awaitable[None]]) -> None:
        self._on_utterance = on_utterance
        self._loop = asyncio.get_event_loop()
        self._running = True
        self._start_thread()
        log.info("Google STT 시작")

    def _start_thread(self):
        self._thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._thread.start()

    async def send_audio(self, chunk: bytes) -> None:
        if self._running:
            self._audio_q.put(chunk)

    async def close(self) -> None:
        self._running = False
        self._audio_q.put(None)
        if self._thread:
            self._thread.join(timeout=3)
        log.info("Google STT 종료")

    # ── 내부 스트림 루프 (스레드) ────────────────
    def _stream_loop(self):
        """5분 제한 전 자동 재시작하는 루프"""
        while self._running:
            try:
                self._run_once()
            except Exception as e:
                if self._running:
                    log.error("STT 스트림 오류, 재시작: %s", e)
                    threading.Event().wait(1)  # 1초 대기 후 재시작

    def _run_once(self):
        """단일 스트리밍 세션 실행 (최대 STREAM_RESTART_SECS 초)"""
        import time
        start = time.time()

        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.MULAW,
            sample_rate_hertz=8000,
            language_code="ko-KR",
            enable_automatic_punctuation=True,
            model="latest_short",
        )
        streaming_config = speech.StreamingRecognitionConfig(
            config=config,
            interim_results=True,
        )

        def audio_gen():
            while self._running:
                elapsed = time.time() - start
                if elapsed >= STREAM_RESTART_SECS:
                    log.info("STT 스트림 갱신 (%.0f초 경과)", elapsed)
                    return   # 루프 재시작 트리거
                try:
                    chunk = self._audio_q.get(timeout=1)
                    if chunk is None:
                        return
                    yield speech.StreamingRecognizeRequest(audio_content=chunk)
                except queue.Empty:
                    continue

        try:
            responses = self._client.streaming_recognize(streaming_config, audio_gen())
            self._process(responses)
        except Exception as e:
            if self._running:
                raise

    def _process(self, responses):
        buffer = ""
        for response in responses:
            if not self._running:
                break
            for result in response.results:
                if not result.alternatives:
                    continue
                transcript = result.alternatives[0].transcript.strip()
                if result.is_final and transcript:
                    buffer += " " + transcript
                    full = buffer.strip()
                    buffer = ""
                    if full and self._on_utterance and self._loop:
                        log.info("STT 발화: %s", full)
                        asyncio.run_coroutine_threadsafe(
                            self._on_utterance(full), self._loop
                        )
