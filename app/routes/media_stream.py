"""
app/routes/media_stream.py
───────────────────────────
Twilio Media Stream WebSocket + 브라우저 모니터링 WS.

  WS /media-stream   Twilio 오디오 스트림
  WS /ws/calls       브라우저 실시간 모니터링 구독
  GET /calls         활성 통화 목록
"""
import asyncio
import json
import logging
import re
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.agent import CallAgent
from app.core.call_event_bus import bus
from app.providers.factory import get_llm, get_stt, get_tts

log = logging.getLogger(__name__)
router = APIRouter()

_active: Dict[str, CallAgent] = {}


def _normalize_phone(number: str) -> str:
    """전화번호 E.164 정규화 (+821071373554 형식)"""
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


@router.websocket("/media-stream")
async def media_stream(ws: WebSocket):
    await ws.accept()
    agent: CallAgent | None = None
    stream_sid = ""

    # WS URL 쿼리스트링에서 발신자 번호 파싱 (twiml.py에서 전달)
    _ws_phone = ws.query_params.get("from", "")

    async def send_audio(sid: str, b64: str):
        await ws.send_text(json.dumps({
            "event": "media",
            "streamSid": sid,
            "media": {"payload": b64},
        }))

    try:
        async for raw in ws.iter_text():
            data  = json.loads(raw)
            event = data.get("event")

            if event == "start":
                meta       = data["start"]
                stream_sid = meta["streamSid"]
                call_id    = meta.get("callSid", stream_sid)

                # 발신자 번호 — 우선순위:
                # 1. WS 쿼리스트링 (?from=+821071373554)
                # 2. customParameters.CallerPhone (twiml <Parameter>)
                # 3. customParameters.From
                # 4. meta.from / meta.From
                custom = meta.get("customParameters", {})
                raw_phone = (
                    _ws_phone
                    or custom.get("CallerPhone", "")
                    or custom.get("From", "")
                    or meta.get("from", "")
                    or meta.get("From", "")
                )
                phone = _normalize_phone(raw_phone)
                log.info("통화 시작: %s | 발신자: %s → 정규화: %s",
                         call_id, raw_phone or "(없음)", phone or "(없음)")

                agent = CallAgent(
                    call_id       = call_id,
                    stream_sid    = stream_sid,
                    llm           = get_llm(),
                    stt           = get_stt(),
                    tts           = get_tts(),
                    send_audio_cb = send_audio,
                    phone         = phone,
                )
                _active[call_id] = agent
                asyncio.create_task(agent.start())

            elif event == "media" and agent:
                await agent.receive_audio(data["media"]["payload"])

            elif event == "stop":
                log.info("통화 종료: %s", stream_sid)
                break

    except WebSocketDisconnect:
        log.info("WS 연결 끊김: %s", stream_sid)
    except Exception as e:
        log.exception("media_stream 오류: %s", e)
    finally:
        if agent:
            await agent.close()
            _active.pop(agent.call_id, None)


@router.websocket("/ws/calls")
async def calls_ws(ws: WebSocket):
    await ws.accept()
    await bus.subscribe(ws)

    async def ping_loop():
        try:
            while True:
                await asyncio.sleep(30)
                await ws.send_text(json.dumps({"type": "ping"}))
        except Exception:
            pass

    ping_task = asyncio.create_task(ping_loop())
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        ping_task.cancel()
        bus.unsubscribe(ws)


@router.get("/calls")
async def get_calls():
    return {
        "count": len(_active),
        "calls": bus.get_active_calls(),
    }


def active_call_count() -> int:
    return len(_active)
