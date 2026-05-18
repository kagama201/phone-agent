"""
app/providers/factory.py
─────────────────────────
설정(LLM_PROVIDER / STT_PROVIDER / TTS_PROVIDER)에 따라
올바른 어댑터 인스턴스를 반환.
새 공급자 추가 시 이 파일에만 등록하면 된다.
"""
from app.config import settings
from app.core.interfaces import LLMProvider, STTProvider, TTSProvider


def get_llm() -> LLMProvider:
    if settings.llm_provider == "gemini":
        from app.providers.llm_gemini import GeminiLLM
        return GeminiLLM()

    if settings.llm_provider == "claude":
        from app.providers.llm_claude import ClaudeLLM
        return ClaudeLLM()

    raise ValueError(f"지원하지 않는 LLM 공급자: {settings.llm_provider}")


def get_stt() -> STTProvider:
    if settings.stt_provider == "google":
        from app.providers.stt_google import GoogleSTT
        return GoogleSTT()

    if settings.stt_provider == "deepgram":
        from app.providers.stt_deepgram import DeepgramSTT
        return DeepgramSTT(api_key=settings.deepgram_api_key)

    if settings.stt_provider == "whisper":
        from app.providers.stt_whisper import WhisperSTT  # 추후 구현
        return WhisperSTT()

    raise ValueError(f"지원하지 않는 STT 공급자: {settings.stt_provider}")


def get_tts() -> TTSProvider:
    if settings.tts_provider == "google":
        from app.providers.tts_google import GoogleTTS
        return GoogleTTS()

    if settings.tts_provider == "elevenlabs":
        from app.providers.tts_elevenlabs import ElevenLabsTTS
        return ElevenLabsTTS(
            api_key=settings.elevenlabs_api_key,
            voice_id=settings.elevenlabs_voice_id,
        )

    if settings.tts_provider == "polly":
        from app.providers.tts_polly import PollyTTS   # 추후 구현
        return PollyTTS()

    raise ValueError(f"지원하지 않는 TTS 공급자: {settings.tts_provider}")
