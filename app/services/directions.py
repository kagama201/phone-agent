"""
app/services/directions.py
───────────────────────────
Google Maps Directions API로 길 안내 텍스트 생성.

무료 한도: 월 $200 크레딧 (약 10,000회 요청)
API 키:   GOOGLE_MAPS_API_KEY 환경변수
키 발급:  console.cloud.google.com → Directions API 활성화
"""
import logging
import os
import urllib.parse

import httpx

log = logging.getLogger(__name__)

MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")


async def get_directions(
    origin_lat: float,
    origin_lng: float,
    destination: str,
    mode: str = "transit",       # transit | walking | driving
    language: str = "ko",
) -> dict:
    """
    출발지(lat/lng) → 목적지(텍스트) 경로 조회.
    반환: {
        "summary": "전체 요약 (음성 안내용)",
        "steps": ["1. ...", "2. ..."],
        "duration": "약 25분",
        "distance": "3.2km",
        "sms_text": "SMS 전송용 상세 텍스트",
    }
    """
    if not MAPS_API_KEY:
        log.warning("GOOGLE_MAPS_API_KEY 미설정 — 더미 안내 반환")
        return _dummy_directions(destination)

    origin = f"{origin_lat},{origin_lng}"
    params = {
        "origin":      origin,
        "destination": destination,
        "mode":        mode,
        "language":    language,
        "key":         MAPS_API_KEY,
    }
    url = "https://maps.googleapis.com/maps/api/directions/json?" + urllib.parse.urlencode(params)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "OK":
            log.error("Directions API 오류: %s", data.get("status"))
            return _dummy_directions(destination)

        route    = data["routes"][0]
        leg      = route["legs"][0]
        duration = leg["duration"]["text"]
        distance = leg["distance"]["text"]

        # 단계별 안내 텍스트 (HTML 태그 제거)
        steps = []
        for i, step in enumerate(leg["steps"], 1):
            raw  = step["html_instructions"]
            text = _strip_html(raw)
            steps.append(f"{i}. {text}")

        summary = (
            f"{destination}까지 {mode_ko(mode)}으로 "
            f"{duration} 소요됩니다. 거리는 {distance}입니다."
        )

        sms_text = f"📍 {destination} 길 안내\n"
        sms_text += f"이동 수단: {mode_ko(mode)}\n"
        sms_text += f"소요 시간: {duration} / 거리: {distance}\n\n"
        sms_text += "\n".join(steps[:8])   # SMS는 8단계까지
        if len(steps) > 8:
            sms_text += f"\n... 외 {len(steps)-8}단계"

        return {
            "summary":  summary,
            "steps":    steps,
            "duration": duration,
            "distance": distance,
            "sms_text": sms_text,
        }

    except Exception as e:
        log.error("Directions API 호출 오류: %s", e)
        return _dummy_directions(destination)


def mode_ko(mode: str) -> str:
    return {"transit": "대중교통", "walking": "도보", "driving": "자동차"}.get(mode, mode)


def _strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", " ", text).replace("  ", " ").strip()


def _dummy_directions(destination: str) -> dict:
    """API 키 없을 때 반환하는 더미 (테스트용)"""
    return {
        "summary":  f"{destination}까지의 길 안내를 준비했습니다.",
        "steps":    ["1. 현재 위치에서 출발하세요.", f"2. {destination}으로 이동하세요."],
        "duration": "알 수 없음",
        "distance": "알 수 없음",
        "sms_text": f"📍 {destination} 길 안내\n(상세 안내는 지도 앱을 이용해주세요)",
    }
