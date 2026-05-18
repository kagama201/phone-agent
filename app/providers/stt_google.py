"""
app/providers/stt_google.py
────────────────────────────
Google Cloud Speech-to-Text v2 스트리밍 어댑터.

무료 티어:
  - STT v1: 월 60분 무료 (표준 모델)
  - STT v2: 월 0~60분 무료 구간 있음
  - 초과 시 $0.006/15초

Twilio 오디오 포맷: μ-law 8kHz mono
Google STT 설정:  encoding=MULAW, sample_rate=8000

인증: GOOGLE_APPLICATION_CREDENTIALS 환경변수
      (Render에서는 GOOGLE_CREDENTIALS_JSON → 파일로 변환, render_startup.sh 참고)
"""
import asyncio
import logging
import queue
import threading
from typing import Callable, Awaitable

from google.cloud import speech

from app.core.interfaces import STTProvider

log = logging.getLogger(__name__)

# 1초 침묵 후 발화 완료로 간주
_SILENCE_TIMEOUT = 1.0


class GoogleSTT(STTProvider):
    """
    Google Cloud STT 스트리밍.
    Google STT는 양방향 gRPC 스트리밍을 사용하므로
    별도 스레드에서 동기 스트림을 실행하고
    asyncio 이벤트 루프와 queue로 연결한다.
    """

    def __init__(self):
        self._client = speech.SpeechClient()
        self._audio_queue: queue.Queue[bytes | None] = queue.Queue()
        self._on_utterance: Callable[[str], Awaitable[None]] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._interim_buffer = ""

    # ── STTProvider 인터페이스 구현 ──────────────
    async def connect(
        self, on_utterance: Callable[[str], Awaitable[None]]
    ) -> None:
        self._on_utterance = on_utterance
        self._loop = asyncio.get_event_loop()
        self._running = True

        # 동기 gRPC 스트림을 별도 스레드에서 실행
        self._thread = threading.Thread(
            target=self._run_stream, daemon=True
        )
        self._thread.start()
        log.info("Google STT 스트리밍 시작")

    async def send_audio(self, chunk: bytes) -> None:
        """μ-law 오디오 청크를 큐에 넣음 (스레드 안전)"""
        if self._running:
            self._audio_queue.put(chunk)

    async def close(self) -> None:
        self._running = False
        self._audio_queue.put(None)   # 스트림 종료 시그널
        if self._thread:
            self._thread.join(timeout=3)
        log.info("Google STT 종료")

    # ── 내부: 동기 gRPC 스트림 스레드 ──────────
    def _audio_generator(self):
        """큐에서 오디오를 꺼내 Google STT request로 변환"""
        while True:
            chunk = self._audio_queue.get()
            if chunk is None:
                return
            yield speech.StreamingRecognizeRequest(audio_content=chunk)

    def _run_stream(self):
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.MULAW,
            sample_rate_hertz=8000,
            language_code="ko-KR",
            enable_automatic_punctuation=True,
            model="latest_short",   # 전화 통화에 최적화된 모델
        )
        streaming_config = speech.StreamingRecognitionConfig(
            config=config,
            interim_results=True,
        )

        try:
            responses = self._client.streaming_recognize(
                streaming_config,
                self._audio_generator(),
            )
            self._process_responses(responses)
        except Exception as e:
            if self._running:
                log.error("Google STT 스트림 오류: %s", e)

    def _process_responses(self, responses):
        """STT 결과 처리 — 발화 완성 시 콜백 호출"""
        buffer = ""

        for response in responses:
            if not self._running:
                break
            for result in response.results:
                alt = result.alternatives[0] if result.alternatives else None
                if not alt:
                    continue

                transcript = alt.transcript.strip()

                if result.is_final:
                    buffer += " " + transcript
                    full_text = buffer.strip()
                    buffer = ""
                    if full_text and self._on_utterance and self._loop:
                        log.info("발화 완료: %s", full_text)
                        # asyncio 루프로 콜백 전달
                        asyncio.run_coroutine_threadsafe(
                            self._on_utterance(full_text),
                            self._loop,
                        )
