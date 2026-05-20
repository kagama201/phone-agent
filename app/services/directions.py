"""
app/services/directions.py
───────────────────────────
Google Maps Directions API로 길 안내 텍스트 생성.

오류 종류:
  NOT_FOUND   — 목적지가 너무 모호 (상호명만 입력 등)
  ZERO_RESULTS — 경로 없음
"""
import logging
import os
import urllib.parse

import httpx

log = logging.getLogger(__name__)

MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")


class DestinationNotFoundError(Exception):
    """목적지가 너무 모호해서 Google Maps가 찾지 못한 경우"""
    pass


async def get_directions(
    origin_lat: float,
    origin_lng: float,
    destination: str,
    mode: str = "transit",
    language: str = "ko",
) -> dict:
    """
    출발지(lat/lng) → 목적지(텍스트) 경로 조회.
    반환: {
        "summary":  음성 안내용 요약,
        "steps":    ["1. ...", "2. ..."],
        "duration": "약 25분",
        "distance": "3.2km",
        "sms_text": SMS 전송용 상세 텍스트,
        "origin_address": 출발지 주소 (역지오코딩 결과),
    }
    예외: DestinationNotFoundError — 목적지 불명확 시
    """
    if not MAPS_API_KEY:
        log.warning("GOOGLE_MAPS_API_KEY 미설정 — 더미 안내 반환")
        return _dummy_directions(destination, origin_lat, origin_lng)

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

        status = data.get("status")

        # 목적지 불명확 → 사용자에게 되물어야 함
        if status == "NOT_FOUND":
            log.warning("Directions NOT_FOUND: destination=%s", destination)
            raise DestinationNotFoundError(destination)

        if status == "ZERO_RESULTS":
            log.warning("Directions ZERO_RESULTS: destination=%s", destination)
            return {
                "summary":  f"{destination}까지 경로를 찾을 수 없습니다. 출발지와 너무 멀거나 대중교통이 없는 경로일 수 있어요.",
                "steps":    [],
                "duration": "알 수 없음",
                "distance": "알 수 없음",
                "sms_text": f"📍 {destination} — 경로를 찾을 수 없습니다.",
                "origin_address": "",
            }

        if status != "OK":
            log.error("Directions API 오류: %s", status)
            return _dummy_directions(destination, origin_lat, origin_lng)

        route = data["routes"][0]
        leg   = route["legs"][0]

        duration       = leg["duration"]["text"]
        distance       = leg["distance"]["text"]
        origin_address = leg.get("start_address", "")
        end_address    = leg.get("end_address", destination)

        steps = []
        for i, step in enumerate(leg["steps"], 1):
            text = _strip_html(step["html_instructions"])
            steps.append(f"{i}. {text}")

        summary = (
            f"{end_address}까지 {mode_ko(mode)}으로 "
            f"{duration} 소요됩니다. 거리는 {distance}입니다."
        )

        sms_text  = f"📍 {end_address} 길 안내\n"
        sms_text += f"이동 수단: {mode_ko(mode)}\n"
        sms_text += f"소요 시간: {duration} / 거리: {distance}\n\n"
        sms_text += "\n".join(steps[:8])
        if len(steps) > 8:
            sms_text += f"\n... 외 {len(steps)-8}단계"

        return {
            "summary":        summary,
            "steps":          steps,
            "duration":       duration,
            "distance":       distance,
            "sms_text":       sms_text,
            "origin_address": origin_address,
        }

    except DestinationNotFoundError:
        raise
    except Exception as e:
        log.error("Directions API 호출 오류: %s", e)
        return _dummy_directions(destination, origin_lat, origin_lng)


async def reverse_geocode(lat: float, lng: float) -> str:
    """
    위도/경도 → 주소 텍스트 (역지오코딩).
    위치 확인 안내에 사용.
    """
    if not MAPS_API_KEY:
        return f"위도 {lat:.4f}, 경도 {lng:.4f}"

    params = {
        "latlng":   f"{lat},{lng}",
        "language": "ko",
        "key":      MAPS_API_KEY,
    }
    url = "https://maps.googleapis.com/maps/api/geocode/json?" + urllib.parse.urlencode(params)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url)
            data = resp.json()
        if data.get("status") == "OK" and data["results"]:
            return data["results"][0]["formatted_address"]
    except Exception as e:
        log.warning("역지오코딩 실패: %s", e)
    return f"위도 {lat:.4f}, 경도 {lng:.4f}"


def mode_ko(mode: str) -> str:
    return {"transit": "대중교통", "walking": "도보", "driving": "자동차"}.get(mode, mode)


def _strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", " ", text).replace("  ", " ").strip()


def _dummy_directions(destination: str, lat: float = 0, lng: float = 0) -> dict:
    return {
        "summary":        f"{destination}까지의 길 안내를 준비했습니다.",
        "steps":          ["1. 현재 위치에서 출발하세요.", f"2. {destination}으로 이동하세요."],
        "duration":       "알 수 없음",
        "distance":       "알 수 없음",
        "sms_text":       f"📍 {destination} 길 안내\n(상세 안내는 지도 앱을 이용해주세요)",
        "origin_address": f"{lat:.4f}, {lng:.4f}",
    }
