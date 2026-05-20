"""
app/routes/media_stream.py
───────────────────────────
Twilio Media Stream WebSocket + 브라우저 모니터링 WS.

  WS /media-stream   Twilio 오디오 스트림
  WS /ws/calls       브라우저 실시간 모니터링 구독
  GET /calls         활성 통화 목록 (REST)
"""
import asyncio
import json
import logging
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.agent import CallAgent
from app.core.call_event_bus import bus
from app.providers.factory import get_llm, get_stt, get_tts

log = logging.getLogger(__name__)
router = APIRouter()

_active: Dict[str, CallAgent] = {}


# ── Twilio 미디어 스트림 ──────────────────────────
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
                # 발신자 번호 — WS 쿼리스트링 우선, 없으면 customParameters
                custom = meta.get("customParameters", {})
                phone  = (
                    _ws_phone or
                    custom.get("From") or
                    meta.get("from") or
                    meta.get("From") or
                    ""
                )
                log.info("발신자 번호: %s", phone or "(없음)")
                log.info("통화 시작: %s", call_id)

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


# ── 브라우저 모니터링 구독 ────────────────────────
@router.websocket("/ws/calls")
async def calls_ws(ws: WebSocket):
    await ws.accept()
    await bus.subscribe(ws)

    async def ping_loop():
        """Render 60초 타임아웃 방지 — 30초마다 서버 ping"""
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
                data = await asyncio.wait_for(ws.receive_text(), timeout=60)
                # 클라이언트 pong 수신 — 무시
            except asyncio.TimeoutError:
                pass  # 타임아웃은 정상, 계속 유지
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        ping_task.cancel()
        bus.unsubscribe(ws)


# ── 활성 통화 목록 REST ───────────────────────────
@router.get("/calls")
async def get_calls():
    return {
        "count": len(_active),
        "calls": bus.get_active_calls(),
    }


def active_call_count() -> int:
    return len(_active)
