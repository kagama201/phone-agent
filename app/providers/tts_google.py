"""
app/providers/tts_google.py
────────────────────────────
Google Cloud Text-to-Speech 어댑터.
무료 티어: 표준 음성 월 100만 자, WaveNet 월 100만 자(첫 90일).
GOOGLE_APPLICATION_CREDENTIALS 환경변수로 서비스 계정 JSON 경로 지정.
Render에서는 환경변수에 JSON 내용 자체를 GOOGLE_CREDENTIALS_JSON으로 넣고
애플리케이션 시작 시 파일로 쓰는 방식을 사용한다 (render_startup.sh 참고).
"""
import audioop
import logging

from google.cloud import texttospeech

from app.core.interfaces import TTSProvider

log = logging.getLogger(__name__)


class GoogleTTS(TTSProvider):
    def __init__(self):
        self._client = texttospeech.TextToSpeechAsyncClient()
        self._voice = texttospeech.VoiceSelectionParams(
            language_code="ko-KR",
            name="ko-KR-Standard-A",   # 무료 표준 음성
            # 업그레이드 시: name="ko-KR-Wavenet-A"
        )
        self._audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=8000,    # Twilio μ-law 8kHz에 맞춤
        )

    async def synthesize(self, text: str) -> bytes:
        """텍스트 → μ-law 8kHz PCM bytes"""
        req = texttospeech.SynthesizeSpeechRequest(
            input=texttospeech.SynthesisInput(text=text),
            voice=self._voice,
            audio_config=self._audio_config,
        )
        resp = await self._client.synthesize_speech(request=req)
        # LINEAR16 → μ-law 변환
        pcm_16 = resp.audio_content
        mulaw  = audioop.lin2ulaw(pcm_16, 2)
        log.debug("TTS 합성 완료: %d bytes → %d bytes μ-law", len(pcm_16), len(mulaw))
        return mulaw
