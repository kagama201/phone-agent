"""
app/routes/chat.py
───────────────────
에이전트 로직 테스트용 텍스트 채팅 엔드포인트.
/prompt에서 저장한 에이전트 설계(get_design())를 그대로 사용해
설계 변경이 즉시 테스트에 반영된다.

엔드포인트:
  POST /chat/session              새 세션 시작 → 첫 인사 반환
  POST /chat/session/{id}/message 메시지 전송 → SSE 스트리밍 응답
  GET  /chat/session/{id}/history 대화 히스토리 조회
  DELETE /chat/session/{id}       세션 종료
  GET  /chat/sessions             활성 세션 목록
"""
import json
import logging
import uuid
from typing import Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.multi_agent import MultiAgentRunner, get_design

log = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat-test"])

# 세션 히스토리 저장소 (메모리)
_sessions: Dict[str, list] = {}


class SessionResponse(BaseModel):
    session_id: str
    greeting: str

class MessageRequest(BaseModel):
    text: str


@router.post("/session", response_model=SessionResponse)
async def create_session():
    session_id = str(uuid.uuid4())[:8]
    _sessions[session_id] = []
    design = get_design()
    greeting = "안녕하세요! AI 상담사 아리입니다. 무엇을 도와드릴까요?"
    _sessions[session_id].append({"role": "assistant", "content": greeting})
    log.info("세션 생성: %s (design: %d sub-agents)", session_id, len(design.sub_agents))
    return SessionResponse(session_id=session_id, greeting=greeting)


@router.post("/session/{session_id}/message")
async def send_message(session_id: str, body: MessageRequest):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    history = _sessions[session_id]
    design = get_design()
    runner = MultiAgentRunner()

    # 사용자 메시지 히스토리에 추가
    history.append({"role": "user", "content": body.text})

    async def event_stream():
        final_text = ""
        try:
            async for chunk in runner.run(body.text, history[:-1], design):
                data = json.dumps(chunk, ensure_ascii=False)
                yield f"data: {data}\n\n"
                if chunk.get("type") == "final":
                    final_text = chunk.get("text", "")
        except Exception as e:
            log.exception("send_message 오류")
            err = json.dumps({"type": "error", "text": str(e)}, ensure_ascii=False)
            yield f"data: {err}\n\n"
        finally:
            if final_text:
                history.append({"role": "assistant", "content": final_text})
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/session/{session_id}/history")
async def get_history(session_id: str):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return {"session_id": session_id, "history": _sessions[session_id]}


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    _sessions.pop(session_id, None)
    return {"session_id": session_id, "status": "closed"}


@router.get("/sessions")
async def list_sessions():
    design = get_design()
    return {
        "count": len(_sessions),
        "sessions": list(_sessions.keys()),
        "active_design": {
            "sub_agents": [a.id for a in design.sub_agents if a.enabled],
            "main_prompt_preview": design.main.prompt[:80] + "...",
        }
    }
