"""
app/routes/twiml.py
────────────────────
전화 수신 시 Twilio가 호출하는 Webhook.
TwiML <Stream> 명령으로 오디오를 WebSocket 서버로 전달.
"""
import os
from fastapi import APIRouter, Request
from fastapi.responses import Response

router = APIRouter()


@router.post("/incoming-call")
async def incoming_call(request: Request):
    """
    Twilio Console → Phone Numbers → Voice Webhook URL:
      https://<your-render-app>.onrender.com/incoming-call
    """
    host   = request.headers.get("host", "localhost")
    scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{scheme}://{host}/media-stream"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="ko-KR">잠시만 기다려 주세요.</Say>
    <Connect>
        <Stream url="{ws_url}" />
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")
