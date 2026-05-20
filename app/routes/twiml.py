"""
app/routes/twiml.py
────────────────────
Twilio Webhook — 전화 수신 시 WS 미디어 스트림 연결.

발신자 번호 전달 방식 (이중 보장):
  1. WS URL 쿼리스트링: ?from=+821071373554
  2. TwiML <Parameter name="CallerPhone">: start 이벤트 customParameters에 포함

Twilio From 번호 형식: +821071373554 (E.164)
"""
import logging
import os
import urllib.parse
from typing import Optional

from fastapi import APIRouter, Request, Form
from fastapi.responses import Response

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/incoming-call")
async def incoming_call(
    request: Request,
    From:        Optional[str] = Form(default=""),
    To:          Optional[str] = Form(default=""),
    CallSid:     Optional[str] = Form(default=""),
    CallStatus:  Optional[str] = Form(default=""),
):
    """
    Twilio POST body 파라미터:
      From      발신자 번호 (예: +821071373554)
      To        수신자 번호 (Twilio 구입 번호)
      CallSid   통화 고유 ID
    """
    # From이 비어있으면 request body에서 직접 파싱
    if not From:
        try:
            body = await request.body()
            body_str = body.decode()
            for part in body_str.split("&"):
                if part.startswith("From="):
                    From = urllib.parse.unquote_plus(part[5:])
                    break
        except Exception:
            pass

    log.info("incoming-call: From=%s To=%s CallSid=%s", From, To, CallSid)

    base_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")

    if base_url:
        ws_base = base_url.replace("https://", "wss://").replace("http://", "ws://")
    else:
        host   = request.headers.get("host", "localhost")
        proto  = request.headers.get("x-forwarded-proto", request.url.scheme)
        scheme = "wss" if proto == "https" else "ws"
        ws_base = f"{scheme}://{host}"

    # 번호 정규화 — E.164 형식 보장
    from_normalized = _normalize(From)

    # WS URL에 쿼리스트링으로 포함
    qs = ""
    if from_normalized:
        qs = "?" + urllib.parse.urlencode({"from": from_normalized})

    ws_url = f"{ws_base}/media-stream{qs}"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}">
            <Parameter name="CallerPhone" value="{from_normalized}"/>
        </Stream>
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


def _normalize(number: str) -> str:
    """전화번호를 E.164 형식으로 정규화 (+821071373554 형식)"""
    import re
    if not number:
        return ""
    cleaned = re.sub(r"[^\d+]", "", number).strip()
    if cleaned.startswith("+"):
        return cleaned
    if cleaned.startswith("82") and len(cleaned) >= 11:
        return "+" + cleaned
    if cleaned.startswith("0") and len(cleaned) >= 10:
        return "+82" + cleaned[1:]
    return "+" + cleaned if cleaned else ""
