"""
app/routes/twiml.py
────────────────────
Twilio Webhook — 전화 수신 시 WS 미디어 스트림 연결.

발신자 번호(From)를 WS URL 쿼리스트링으로 전달해
media_stream.py에서 phone 번호를 정확히 파악할 수 있도록 함.
"""
import os
import urllib.parse
from fastapi import APIRouter, Request, Form
from fastapi.responses import Response
from typing import Optional

router = APIRouter()


@router.post("/incoming-call")
async def incoming_call(
    request: Request,
    From: Optional[str] = Form(default=""),
    To:   Optional[str] = Form(default=""),
):
    """
    Twilio가 POST body로 From(발신자), To(수신자) 등을 전달.
    From 번호를 WS URL 쿼리스트링에 포함시켜 에이전트에서 SMS 발송에 활용.
    """
    base_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")

    if base_url:
        ws_base = base_url.replace("https://", "wss://").replace("http://", "ws://")
    else:
        host   = request.headers.get("host", "localhost")
        proto  = request.headers.get("x-forwarded-proto", request.url.scheme)
        scheme = "wss" if proto == "https" else "ws"
        ws_base = f"{scheme}://{host}"

    # From 번호를 쿼리스트링으로 전달
    params = {}
    if From:
        params["from"] = From
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    ws_url = f"{ws_base}/media-stream{qs}"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}" />
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")
