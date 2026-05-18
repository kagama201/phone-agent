"""
app/routes/chat.py
───────────────────
에이전트 로직 테스트용 텍스트 채팅 엔드포인트.
통신망/STT/TTS 없이 HTTP + WebSocket으로 대화.

엔드포인트:
  POST /chat/session              새 세션 시작 → 첫 인사 반환
  POST /chat/session/{id}/message 메시지 전송 → 응답 반환
  GET  /chat/session/{id}/history 대화 히스토리 조회
  DELETE /chat/session/{id}       세션 종료
  WS   /chat/ws/{id}              WebSocket 스트리밍 (선택)
"""
import logging
import uuid
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

from app.core.text_agent import TextAgent
from app.providers.factory import get_llm

log = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat-test"])

# 세션 저장소 (메모리, 대용량 시 Redis로 교체)
_sessions: Dict[str, TextAgent] = {}


# ── 요청/응답 스키마 ──────────────────────────────
class SessionResponse(BaseModel):
    session_id: str
    greeting: str

class MessageRequest(BaseModel):
    text: str

class MessageResponse(BaseModel):
    session_id: str
    user: str
    agent: str


# ── 세션 시작 ─────────────────────────────────────
@router.post("/session", response_model=SessionResponse)
async def create_session():
    """새 통화 세션 시작. 에이전트 첫 인사를 반환."""
    session_id = str(uuid.uuid4())[:8]
    agent = TextAgent(session_id=session_id, llm=get_llm())
    _sessions[session_id] = agent

    greeting = await agent.greet()
    log.info("세션 생성: %s", session_id)
    return SessionResponse(session_id=session_id, greeting=greeting)


# ── 메시지 전송 ───────────────────────────────────
@router.post("/session/{session_id}/message", response_model=MessageResponse)
async def send_message(session_id: str, body: MessageRequest):
    """텍스트 메시지 전송 → 에이전트 응답 반환."""
    agent = _sessions.get(session_id)
    if not agent:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    reply = await agent.chat(body.text)
    return MessageResponse(session_id=session_id, user=body.text, agent=reply)


# ── 히스토리 조회 ──────────────────────────────────
@router.get("/session/{session_id}/history")
async def get_history(session_id: str):
    agent = _sessions.get(session_id)
    if not agent:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return {"session_id": session_id, "history": agent.get_history()}


# ── 세션 종료 ──────────────────────────────────────
@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    if session_id in _sessions:
        del _sessions[session_id]
        log.info("세션 종료: %s", session_id)
    return {"session_id": session_id, "status": "closed"}


# ── 활성 세션 목록 ─────────────────────────────────
@router.get("/sessions")
async def list_sessions():
    return {
        "count": len(_sessions),
        "sessions": list(_sessions.keys()),
    }


# ── WebSocket 스트리밍 ─────────────────────────────
@router.websocket("/ws/{session_id}")
async def chat_ws(ws: WebSocket, session_id: str):
    """
    WebSocket 실시간 채팅.
    클라이언트: {"text": "메시지"}
    서버:       {"type": "agent", "text": "응답"} 또는 {"type": "error", "text": "..."}
    """
    await ws.accept()
    agent = _sessions.get(session_id)

    if not agent:
        await ws.send_json({"type": "error", "text": "세션을 찾을 수 없습니다."})
        await ws.close()
        return

    log.info("WS 연결: %s", session_id)
    try:
        async for data in ws.iter_json():
            user_text = data.get("text", "").strip()
            if not user_text:
                continue
            reply = await agent.chat(user_text)
            await ws.send_json({"type": "agent", "text": reply})
    except WebSocketDisconnect:
        log.info("WS 연결 종료: %s", session_id)
