"""
app/providers/llm_gemini.py
────────────────────────────
Google Gemini LLM 어댑터.

기본 모델: gemini-2.5-flash-lite
  - 무료 티어: 분당 30회, 일 1,500회 요청
  - 가장 빠르고 저렴한 Gemini 모델 (전화 응답 latency에 유리)

교체 시: GEMINI_MODEL=gemini-2.5-flash 또는 gemini-2.5-pro 로 변경

인증: GOOGLE_API_KEY 환경변수
  Google AI Studio(https://aistudio.google.com) → Get API Key → 무료 발급
  ※ Google Cloud 서비스 계정(STT/TTS용)과 별개의 키입니다.
"""
import logging

import google.generativeai as genai

from app.config import settings
from app.core.interfaces import LLMProvider

log = logging.getLogger(__name__)


class GeminiLLM(LLMProvider):
    def __init__(self):
        genai.configure(api_key=settings.google_api_key)
        self._model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            system_instruction=settings.system_prompt,
        )

    async def chat_with_system(self, system: str, history: list[dict]) -> str:
        """시스템 프롬프트 동적 지정 — Gemini 네이티브 방식"""
        model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            system_instruction=system,
        )
        gemini_history = []
        msgs = history[:-1]
        for msg in msgs:
            role = "model" if msg["role"] == "assistant" else "user"
            gemini_history.append({"role": role, "parts": [msg["content"]]})
        chat = model.start_chat(history=gemini_history)
        resp = await chat.send_message_async(history[-1]["content"])
        return resp.text.strip()

    async def chat(self, history: list[dict]) -> str:
        """
        history: [{"role": "user"|"assistant", "content": "..."}]
        반환: 에이전트 응답 텍스트
        """
        # Gemini는 "model" role 사용 (OpenAI/Claude의 "assistant"와 다름)
        gemini_history = []
        for msg in history[:-1]:   # 마지막 user 메시지는 별도 전달
            role = "model" if msg["role"] == "assistant" else "user"
            gemini_history.append({"role": role, "parts": [msg["content"]]})

        last_user_msg = history[-1]["content"]

        chat = self._model.start_chat(history=gemini_history)
        resp = await chat.send_message_async(last_user_msg)
        reply = resp.text.strip()
        log.debug("Gemini 응답: %s", reply)
        return reply
