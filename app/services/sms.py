"""
app/services/sms.py
────────────────────
Twilio SMS 발송 서비스.

트라이얼 계정 제약:
  - Verified Caller IDs에 등록된 번호로만 발송 가능
  - 메시지 앞에 "Sent from a Twilio Trial account" 자동 추가
  - 하루 50건 제한
"""
import logging
import os

from twilio.rest import Client

log = logging.getLogger(__name__)

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        sid   = os.getenv("TWILIO_ACCOUNT_SID", "")
        token = os.getenv("TWILIO_AUTH_TOKEN", "")
        if not sid or not token:
            raise RuntimeError("TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN 환경변수가 없습니다.")
        _client = Client(sid, token)
    return _client


async def send_sms(to: str, body: str) -> str:
    """
    SMS 발송. to는 E.164 형식 (예: +821012345678).
    반환값: Twilio message SID
    """
    from_number = os.getenv("TWILIO_PHONE_NUMBER", "")
    if not from_number:
        raise RuntimeError("TWILIO_PHONE_NUMBER 환경변수가 없습니다.")

    import asyncio
    loop = asyncio.get_event_loop()

    def _send():
        return _get_client().messages.create(
            body=body,
            from_=from_number,
            to=to,
        )

    # Twilio SDK는 동기 — run_in_executor로 블로킹 방지
    msg = await loop.run_in_executor(None, _send)
    log.info("SMS 발송 완료: to=%s sid=%s", to, msg.sid)
    return msg.sid


async def send_location_request(to: str, session_id: str, base_url: str) -> str:
    """위치 동의 링크 SMS 발송"""
    from app.services.location_store import create_token
    token = create_token(session_id)
    url   = f"{base_url}/locate/{token}"
    body  = f"[AI 안내사] 위치 확인을 위해 아래 링크를 눌러주세요.\n{url}"
    return await send_sms(to, body)


async def send_directions(to: str, directions_text: str) -> str:
    """길 안내 SMS 발송"""
    body = f"[AI 안내사] 길 안내\n\n{directions_text}"
    return await send_sms(to, body)
