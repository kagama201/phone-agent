"""
app/providers/tts_google.py
────────────────────────────
Google Cloud Text-to-Speech 어댑터.
무료 티어: 표준 음성 월 100만 자.
"""
import logging
try:
    import audioop
except ImportError:
    import audioop_lts as audioop  # Python 3.13+

from google.cloud import texttospeech

from app.core.interfaces import TTSProvider

log = logging.getLogger(__name__)


class GoogleTTS(TTSProvider):
    def __init__(self):
        self._client = texttospeech.TextToSpeechAsyncClient()
        self._voice = texttospeech.VoiceSelectionParams(
            language_code="ko-KR",
            name="ko-KR-Standard-A",
        )
        self._audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=8000,
        )

    async def synthesize(self, text: str) -> bytes:
        req = texttospeech.SynthesizeSpeechRequest(
            input=texttospeech.SynthesisInput(text=text),
            voice=self._voice,
            audio_config=self._audio_config,
        )
        resp = await self._client.synthesize_speech(request=req)

        # LINEAR16 응답에는 WAV 헤더(44바이트)가 포함됨 — 제거 후 변환
        raw_pcm = resp.audio_content
        if raw_pcm[:4] == b"RIFF":   # WAV 헤더 감지
            raw_pcm = raw_pcm[44:]

        mulaw = audioop.lin2ulaw(raw_pcm, 2)
        log.debug("TTS 완료: %d bytes (pcm) → %d bytes (mulaw)", len(raw_pcm), len(mulaw))
        return mulaw
