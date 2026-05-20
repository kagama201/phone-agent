"""
app/routes/chat.py
───────────────────
에이전트 로직 테스트용 텍스트 채팅 엔드포인트.
/prompt에서 저장한 에이전트 설계를 실시간 반영.

위치 수신 후 메시지 흐름:
  location_agent가 speak_cb 호출
  → _session_queues[session_id]에 메시지 push
  → GET /chat/session/{id}/stream SSE로 브라우저에 전달
"""
import asyncio
import json
import logging
import uuid
from typing import Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.multi_agent import MultiAgentRunner, get_design
from app.db.design_store import upsert_session

log = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat-test"])

# 세션 저장소
_sessions: Dict[str, list] = {}
_phones:   Dict[str, str]  = {}
# 위치 수신 후 메시지를 브라우저로 push하는 큐
_session_queues: Dict[str, asyncio.Queue] = {}


class SessionResponse(BaseModel):
    session_id: str
    greeting: str

class SessionRequest(BaseModel):
    phone_number: str = ""

class MessageRequest(BaseModel):
    text: str


# ── 세션 시작 ─────────────────────────────────────
@router.post("/session", response_model=SessionResponse)
async def create_session(body: SessionRequest = None):
    session_id = str(uuid.uuid4())[:8]
    phone = (body.phone_number or "").strip() if body else ""
    _sessions[session_id] = []
    _phones[session_id]   = phone
    _session_queues[session_id] = asyncio.Queue()
    log.info("세션 생성: %s phone=%s", session_id, phone or "(없음)")

    design = get_design()
    from app.providers.factory import get_llm
    llm = get_llm()
    try:
        greeting = await llm.chat_with_system(
            design.main.prompt,
            [{"role": "user", "content": "전화가 연결됐어. 첫 인사를 해줘. 한 문장으로."}],
        )
    except Exception as e:
        log.warning("인사 생성 실패: %s", e)
        greeting = "안녕하세요! 무엇을 도와드릴까요?"

    _sessions[session_id].append({"role": "assistant", "content": greeting})
    return SessionResponse(session_id=session_id, greeting=greeting)


# ── 메시지 전송 ───────────────────────────────────
@router.post("/session/{session_id}/message")
async def send_message(session_id: str, body: MessageRequest):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    history = _sessions[session_id]
    design  = get_design()
    runner  = MultiAgentRunner()
    phone   = _phones.get(session_id, "")
    log.info("세션 %s phone=%s", session_id, phone or "(없음)")

    history.append({"role": "user", "content": body.text})

    if phone:
        upsert_session(session_id, phone_number=phone)

    # speak_cb: 위치 수신 후 메시지를 세션 큐에 push → SSE 스트림으로 전달
    q = _session_queues.get(session_id)

    async def speak_to_queue(text: str):
        """location_agent의 speak_cb — 큐에 push"""
        if q:
            await q.put({"type": "agent", "text": text, "source": "location"})
        log.info("[%s] location speak: %s", session_id, text)

    async def event_stream():
        final_text = ""
        action_triggered = False
        try:
            async for chunk in runner.run(body.text, history[:-1], design):
                ctype = chunk.get("type")

                # action — send_sms (문자 요청)
                if ctype == "action" and chunk.get("action") == "send_sms":
                    action_triggered = True
                    async def _run_sms():
                        try:
                            from app.core.location_agent import send_directions_on_demand
                            msg = await send_directions_on_demand(session_id)
                            if q:
                                await q.put({"type": "agent", "text": msg, "source": "sms"})
                        except Exception as e:
                            log.error("send_sms 오류: %s", e)
                    asyncio.create_task(_run_sms())
                    sms_msg = {"type": "agent", "text": "📨 상세 길 안내를 문자로 보내드릴게요.", "source": "action"}
                    yield "data: " + json.dumps(sms_msg, ensure_ascii=False) + "\n\n"
                    continue

                # action — 위치 요청
                if ctype == "action" and chunk.get("action") == "request_location":
                    action_triggered = True
                    dest = chunk.get("destination", "목적지")

                    # 큐에 진행 중 메시지 push
                    sms_msg = {"type": "agent", "text": f"📍 {dest} 위치 링크를 SMS로 발송합니다.", "source": "action"}
                    yield f"data: {json.dumps(sms_msg, ensure_ascii=False)}\n\n"

                    # location_agent 비동기 실행 (speak_cb → 큐)
                    async def _run_location(d=dest):
                        try:
                            from app.core.location_agent import request_location_and_guide
                            await request_location_and_guide(
                                call_id=session_id,
                                phone_number=phone,
                                destination=d,
                                speak_cb=speak_to_queue,
                            )
                        except Exception as e:
                            log.error("location_guide 오류: %s", e)
                            if q:
                                await q.put({"type": "agent", "text": "위치 요청 처리 중 오류가 발생했습니다.", "source": "error"})
                    asyncio.create_task(_run_location())
                    continue

                # sub_result / smalltalk / final
                if ctype in ("sub_result", "smalltalk"):
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

                if ctype == "final" and not action_triggered:
                    final_text = chunk.get("text", "")
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

        except Exception as e:
            log.exception("send_message 오류")
            err = json.dumps({"type": "error", "text": str(e)}, ensure_ascii=False)
            yield f"data: {err}\n\n"
        finally:
            if final_text:
                history.append({"role": "assistant", "content": final_text})
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 위치 수신 후 메시지 SSE 스트림 ────────────────
@router.get("/session/{session_id}/stream")
async def session_stream(session_id: str):
    """
    위치 수신 후 location_agent가 speak_cb로 push한 메시지를
    브라우저에 SSE로 전달. 테스트 UI가 이 엔드포인트를 구독.
    """
    if session_id not in _session_queues:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    q = _session_queues[session_id]

    async def stream():
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=60)
                if msg is None:   # 종료 시그널
                    yield "data: [DONE]\n\n"
                    break
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                # keep-alive ping
                yield "data: {\"type\":\"ping\"}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── 히스토리 조회 ──────────────────────────────────
@router.get("/session/{session_id}/history")
async def get_history(session_id: str):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return {"session_id": session_id, "history": _sessions[session_id]}


# ── 세션 종료 ──────────────────────────────────────
@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    _sessions.pop(session_id, None)
    _phones.pop(session_id, None)
    q = _session_queues.pop(session_id, None)
    if q:
        await q.put(None)  # 스트림 종료
    return {"session_id": session_id, "status": "closed"}


# ── 활성 세션 목록 ─────────────────────────────────
@router.get("/sessions")
async def list_sessions():
    design = get_design()
    return {
        "count": len(_sessions),
        "sessions": list(_sessions.keys()),
        "active_design": {
            "sub_agents": [a.id for a in design.sub_agents if a.enabled],
        }
    }
