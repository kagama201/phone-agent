"""
app/config.py
─────────────
모든 설정을 한 곳에서 관리.
LLM_PROVIDER / STT_PROVIDER / TTS_PROVIDER 값만 바꾸면 구현체가 교체됨.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal


class Settings(BaseSettings):
    # ── LLM ─────────────────────────────────────
    llm_provider: Literal["gemini", "claude"] = Field("gemini", env="LLM_PROVIDER")

    # Gemini (llm_provider=gemini 일 때) — 기본값
    google_api_key: str = Field("", env="GOOGLE_API_KEY")
    gemini_model: str   = Field("gemini-2.5-flash-lite", env="GEMINI_MODEL")

    # Claude (llm_provider=claude 일 때)
    anthropic_api_key: str = Field("", env="ANTHROPIC_API_KEY")
    claude_model: str      = Field("claude-sonnet-4-20250514", env="CLAUDE_MODEL")

    system_prompt: str = Field(
        "당신은 친절한 AI 전화 상담사 '아리'입니다. "
        "응답은 2~3문장 이내 구어체로 말하세요.",
        env="SYSTEM_PROMPT",
    )

    # ── STT ─────────────────────────────────────
    stt_provider: Literal["deepgram", "google", "whisper"] = Field(
        "google", env="STT_PROVIDER"
    )
    deepgram_api_key: str = Field("", env="DEEPGRAM_API_KEY")

    # ── TTS ─────────────────────────────────────
    tts_provider: Literal["google", "elevenlabs", "polly"] = Field(
        "google", env="TTS_PROVIDER"
    )
    elevenlabs_api_key: str  = Field("", env="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field("21m00Tcm4TlvDq8ikWAM", env="ELEVENLABS_VOICE_ID")

    # ── Twilio ───────────────────────────────────
    twilio_account_sid:  str = Field("", env="TWILIO_ACCOUNT_SID")
    twilio_auth_token:   str = Field("", env="TWILIO_AUTH_TOKEN")
    twilio_phone_number: str = Field("", env="TWILIO_PHONE_NUMBER")

    # ── 서버 ─────────────────────────────────────
    port: int      = Field(8000,   env="PORT")
    log_level: str = Field("info", env="LOG_LEVEL")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
