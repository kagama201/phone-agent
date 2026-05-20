"""
app/core/location_agent.py
───────────────────────────
위치 기반 길 안내 시나리오 처리.

흐름:
  1. 에이전트가 목적지는 알지만 현재 위치를 모를 때 호출
  2. SMS로 위치 동의 링크 발송
  3. 사용자가 웹에서 위치 동의 → /locate/{token}으로 전송
  4. locate.py가 on_location_received() 콜백 호출
  5. 에이전트가 길 안내 생성 후 음성 + SMS로 전달

외부 의존:
  - app.services.sms         Twilio SMS
  - app.services.directions  Google Maps
  - app.db.design_store      세션 위치 저장
"""
import asyncio
import logging
import os
from typing import Callable, Awaitable

from app.db.design_store import upsert_session, get_session_meta
from app.services.directions import get_directions
from app.services.sms import send_location_request, send_directions

log = logging.getLogger(__name__)

# call_id → 콜백 맵 (위치 수신 시 에이전트에 알림)
_location_callbacks: dict[str, Callable[[float, float], Awaitable[None]]] = {}
# call_id → 대기 중인 목적지
_pending_destinations: dict[str, str] = {}


def register_location_callback(
    call_id: str,
    destination: str,
    callback: Callable[[float, float], Awaitable[None]],
) -> None:
    """에이전트가 위치 수신을 기다릴 때 등록"""
    _location_callbacks[call_id] = callback
    _pending_destinations[call_id] = destination
    log.info("[%s] 위치 콜백 등록 (목적지: %s)", call_id, destination)


def unregister_location_callback(call_id: str) -> None:
    _location_callbacks.pop(call_id, None)
    _pending_destinations.pop(call_id, None)


async def on_location_received(session_id: str, lat: float, lng: float) -> None:
    """
    locate.py가 위치를 수신했을 때 호출.
    session_id = call_id (통화 세션과 동일하게 사용)
    """
    cb = _location_callbacks.pop(session_id, None)
    if cb:
        log.info("[%s] 위치 수신 → 에이전트 콜백 호출", session_id)
        await cb(lat, lng)
    else:
        log.warning("[%s] 위치 수신됐지만 대기 중인 콜백 없음", session_id)


async def request_location_and_guide(
    call_id: str,
    phone_number: str,
    destination: str,
    speak_cb: Callable[[str], Awaitable[None]],
) -> None:
    """
    위치를 모를 때:
    1. 음성으로 SMS 발송 안내
    2. SMS 발송
    3. 위치 수신 대기 (콜백 등록)
    4. 위치 수신 후 길 안내
    """
    base_url = os.getenv("RENDER_EXTERNAL_URL", "https://localhost:8000").rstrip("/")

    async def on_location(lat: float, lng: float) -> None:
        """위치 수신 후 길 안내 실행"""
        await speak_cb(f"{destination}까지 길 안내를 시작할게요. 잠시만요.")

        # Google Maps 길 안내 요청
        directions = await get_directions(lat, lng, destination)

        # 음성 안내
        voice_text = directions["summary"]
        steps_preview = "  ".join(directions["steps"][:3])
        if steps_preview:
            voice_text += f"  {steps_preview}"
        await speak_cb(voice_text)

        # SMS 길 안내 자동 발송
        if phone_number:
            try:
                await send_directions(phone_number, directions["sms_text"])
                await speak_cb("상세 길 안내를 문자로도 보내드렸어요.")
            except Exception as e:
                log.error("[%s] 길 안내 SMS 발송 실패: %s", call_id, e)

        # 세션에 목적지 저장
        upsert_session(call_id, pending_dest=destination)

    # 콜백 등록
    register_location_callback(call_id, destination, on_location)

    # 음성 안내 + SMS 발송
    await speak_cb(
        "정확한 위치를 파악하기 위해 SMS로 링크를 보내드릴게요. "
        "문자로 오는 링크를 눌러 위치를 공유해주세요."
    )

    if phone_number:
        try:
            await send_location_request(phone_number, call_id, base_url)
            log.info("[%s] 위치 요청 SMS 발송 완료: %s", call_id, phone_number)
        except Exception as e:
            log.error("[%s] 위치 요청 SMS 발송 실패: %s", call_id, e)
            await speak_cb("문자 발송에 문제가 생겼어요. 직접 주소를 말씀해주시겠어요?")
    else:
        log.warning("[%s] 전화번호 없음 — SMS 발송 불가", call_id)
        await speak_cb("전화번호를 확인할 수 없어요. 현재 계신 주소를 말씀해주시겠어요?")
