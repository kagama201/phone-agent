"""
app/providers/stt_google.py
────────────────────────────
Google Cloud STT 스트리밍 어댑터.

핵심:
  - 발화 완료(is_final 또는 침묵 1.5초) 후 스트림 재시작
    → 이전 발화가 다음 발화에 누적되는 문제 방지
  - 4분마다 스트림 갱신 (Google 5분 제한)
  - 지수 백오프 재시작
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

STREAM_RESTART_SECS = 240   # 4분
MAX_QUEUE_SIZE      = 200
SILENCE_TIMEOUT     = 1.5   # 발화 완료 판정 침묵 시간(초)


class GoogleSTT(STTProvider):

    def __init__(self):
        self._client  = speech.SpeechClient()
        self._audio_q: queue.Queue[bytes | None] = queue.Queue(maxsize=MAX_QUEUE_SIZE)
        self._on_utterance: Callable[[str], Awaitable[None]] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running  = False
        self._thread: threading.Thread | None = None
        # 발화 완료 후 스트림 재시작 플래그
        self._restart_event = threading.Event()

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

    # ── 스트림 루프 ──────────────────────────────
    def _stream_loop(self):
        """발화 완료 또는 오류 시 스트림 재시작"""
        backoff = 1
        while self._running:
            self._restart_event.clear()
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
            while self._running and not self._restart_event.is_set():
                if time.time() - start >= STREAM_RESTART_SECS:
                    log.info("STT 스트림 갱신 (4분 경과)")
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
        발화 처리:
          is_final=True  → 즉시 fire + 스트림 재시작
          침묵 1.5초     → fire + 스트림 재시작
        스트림 재시작으로 누적 방지.
        """
        last_interim  = ""
        last_change_t = time.time()
        fired         = False   # 이미 fire된 발화 중복 방지

        def _fire(text: str):
            nonlocal fired
            if not text or fired:
                return
            fired = True
            log.info("STT 발화 확정: %s", text)
            if self._on_utterance and self._loop:
                asyncio.run_coroutine_threadsafe(
                    self._on_utterance(text), self._loop
                )
            # 스트림 재시작 트리거 — 다음 발화는 새 컨텍스트에서 시작
            self._restart_event.set()

        def _silence_watcher():
            nonlocal last_interim, last_change_t, fired
            while self._running and not self._restart_event.is_set():
                time.sleep(0.1)
                if last_interim and not fired:
                    elapsed = time.time() - last_change_t
                    if elapsed >= SILENCE_TIMEOUT:
                        text = last_interim
                        last_interim = ""
                        _fire(text)

        watcher = threading.Thread(target=_silence_watcher, daemon=True)
        watcher.start()

        resp_count = 0
        try:
            for response in responses:
                if not self._running or self._restart_event.is_set():
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
                        last_interim = ""
                        _fire(transcript)
                        return   # 스트림 재시작 (_run_once 재호출)
                    else:
                        if transcript != last_interim:
                            last_interim  = transcript
                            last_change_t = time.time()
                            fired = False   # 새 중간 결과 → 다시 fire 가능
                            log.info("STT 중간 인식: %s", transcript)
        finally:
            log.info("STT _process 종료 (총 응답: %d)", resp_count)
