"""
app/routes/twiml.py
────────────────────
전화 수신 Webhook. TwiML로 양방향 미디어 스트림 설정.

핵심:
  track="both_tracks"  — 수신(사용자) + 송신(에이전트) 모두 스트리밍
  <Parameter>          — Twilio가 WS start 이벤트에 메타데이터 포함
"""
from fastapi import APIRouter, Request
from fastapi.responses import Response

router = APIRouter()


@router.post("/incoming-call")
async def incoming_call(request: Request):
    host   = request.headers.get("host", "localhost")
    scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{scheme}://{host}/media-stream"

    # 발신자 번호를 WS start 이벤트에 전달
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="ko-KR">잠시만 기다려 주세요.</Say>
    <Connect>
        <Stream url="{ws_url}" track="both_tracks">
            <Parameter name="From" value="{{{{From}}}}"/>
        </Stream>
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")
