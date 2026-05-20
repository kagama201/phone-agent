"""
app/core/location_agent.py
───────────────────────────
위치 기반 길 안내 시나리오 처리.

흐름:
  1. 에이전트가 목적지는 알지만 현재 위치를 모를 때 호출
  2. SMS로 위치 동의 링크 발송
  3. 사용자가 웹에서 위치 동의 → /locate/{token}으로 전송
  4. locate.py가 on_location_received() 콜백 호출
  5. 확인된 위치 주소를 사용자에게 안내
  6. 목적지가 모호하면 되묻기
  7. 길 안내 생성 후 음성 + SMS로 전달
"""
import asyncio
import logging
import os
from typing import Callable, Awaitable

from app.db.design_store import upsert_session, get_session_meta
from app.services.directions import get_directions, reverse_geocode, DestinationNotFoundError
from app.services.sms import send_location_request, send_directions

log = logging.getLogger(__name__)

_location_callbacks: dict[str, Callable[[float, float], Awaitable[None]]] = {}
_pending_destinations: dict[str, str] = {}


def register_location_callback(
    call_id: str,
    destination: str,
    callback: Callable[[float, float], Awaitable[None]],
) -> None:
    _location_callbacks[call_id] = callback
    _pending_destinations[call_id] = destination
    log.info("[%s] 위치 콜백 등록 (목적지: %s)", call_id, destination)


def unregister_location_callback(call_id: str) -> None:
    _location_callbacks.pop(call_id, None)
    _pending_destinations.pop(call_id, None)


async def on_location_received(session_id: str, lat: float, lng: float) -> None:
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
    base_url = os.getenv("RENDER_EXTERNAL_URL", "https://localhost:8000").rstrip("/")

    async def on_location(lat: float, lng: float) -> None:
        """위치 수신 후 실행"""

        # 1. 역지오코딩으로 현재 위치 주소 파악
        origin_address = await reverse_geocode(lat, lng)
        await speak_cb(f"확인된 현재 위치는 {origin_address}입니다.")
        log.info("[%s] 확인된 위치: %s (%.5f, %.5f)", call_id, origin_address, lat, lng)

        # 세션에 위치/주소 저장
        upsert_session(call_id, pending_dest=destination)

        # 2. 길 안내 요청 (NOT_FOUND 시 되묻기)
        await speak_cb(f"{destination}까지 길 안내를 찾고 있어요. 잠시만요.")

        try:
            directions = await get_directions(lat, lng, destination)
        except DestinationNotFoundError:
            # 목적지 모호 → 사용자에게 지역 정보 요청
            await speak_cb(
                f"{destination}의 정확한 위치를 찾기 어려워요. "
                f"가까운 지역이나 건물 이름을 함께 말씀해주시겠어요? "
                f"예를 들어 '홍대 다이소' 또는 '강남역 다이소' 처럼요."
            )
            log.warning("[%s] 목적지 불명확: %s", call_id, destination)
            return

        # 3. 음성으로 길 안내
        voice_text = directions["summary"]
        steps_preview = "  ".join(directions["steps"][:3])
        if steps_preview:
            voice_text += f"  {steps_preview}"
        await speak_cb(voice_text)

        # 4. SMS로 상세 길 안내 발송
        if phone_number:
            try:
                await send_directions(phone_number, directions["sms_text"])
                await speak_cb("상세 길 안내를 문자로도 보내드렸어요.")
            except Exception as e:
                log.error("[%s] 길 안내 SMS 발송 실패: %s", call_id, e)

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
