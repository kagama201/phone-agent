"""
app/routes/media_stream.py
───────────────────────────
Twilio Media Stream WebSocket 엔드포인트.
통화 한 건 = 하나의 WS 연결 = 하나의 CallAgent.
"""
import asyncio
import json
import logging
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.agent import CallAgent
from app.providers.factory import get_llm, get_stt, get_tts

log = logging.getLogger(__name__)
router = APIRouter()

_active: Dict[str, CallAgent] = {}


@router.websocket("/media-stream")
async def media_stream(ws: WebSocket):
    await ws.accept()
    agent: CallAgent | None = None
    stream_sid = ""

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
                log.info("통화 시작: %s", call_id)

                agent = CallAgent(
                    call_id      = call_id,
                    stream_sid   = stream_sid,
                    llm          = get_llm(),
                    stt          = get_stt(),
                    tts          = get_tts(),
                    send_audio_cb = send_audio,
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


def active_call_count() -> int:
    return len(_active)
