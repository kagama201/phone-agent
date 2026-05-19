"""
app/providers/stt_google.py
────────────────────────────
Google Cloud STT 스트리밍 어댑터.

주요 특이사항:
  - Google STT 단일 스트림 최대 5분 → 자동 재시작
  - 오류 시 지수 백오프 재시작 (1s → 2s → 4s → 최대 16s)
  - gRPC 동기 스트림을 별도 스레드에서 실행
"""
import logging
import queue
import threading
import time
import asyncio
from typing import Callable, Awaitable

from google.cloud import speech

from app.core.interfaces import STTProvider

log = logging.getLogger(__name__)

STREAM_RESTART_SECS = 240   # 4분마다 재시작 (Google 5분 제한 전)
MAX_QUEUE_SIZE      = 200   # 큐 최대 크기 (오디오 유실 방지)


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
            # 큐가 가득 차면 가장 오래된 것 버리고 새 것 삽입
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

    # ── 내부 스트림 루프 ─────────────────────────
    def _stream_loop(self):
        """오류 시 지수 백오프로 재시작"""
        backoff = 1
        while self._running:
            try:
                self._run_once()
                backoff = 1   # 성공 시 리셋
            except Exception as e:
                if not self._running:
                    break
                log.error("STT 스트림 오류 (%.0f초 후 재시작): %s", backoff, e)
                time.sleep(backoff)
                backoff = min(backoff * 2, 16)   # 최대 16초

    def _run_once(self):
        """단일 스트리밍 세션 (최대 STREAM_RESTART_SECS초)"""
        start = time.time()

        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.MULAW,
            sample_rate_hertz=8000,
            language_code="ko-KR",
            enable_automatic_punctuation=True,
            model="default",     # ko-KR 지원 모델
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
        log.info("STT 응답 스트림 연결됨")
        self._process(responses)

    def _process(self, responses):
        buffer = ""
        resp_count = 0
        for response in responses:
            if not self._running:
                break
            resp_count += 1
            if resp_count == 1:
                log.info("STT 첫 응답 수신 (results=%d)", len(response.results))
            if not response.results:
                continue
            for result in response.results:
                if not result.alternatives:
                    continue
                transcript = result.alternatives[0].transcript.strip()
                log.debug("STT interim: is_final=%s text=%s", result.is_final, transcript)
                if transcript and not result.is_final:
                    log.info("STT 중간 인식: %s", transcript)
                if result.is_final and transcript:
                    buffer += " " + transcript
                    full = buffer.strip()
                    buffer = ""
                    if full and self._on_utterance and self._loop:
                        log.info("STT 발화: %s", full)
                        asyncio.run_coroutine_threadsafe(
                            self._on_utterance(full), self._loop
                        )
        log.info("STT _process 종료 (총 응답: %d)", resp_count)
