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

# 세션 히스토리 + 전화번호 저장소 (메모리)
_sessions: Dict[str, list] = {}
_phones: Dict[str, str] = {}


class SessionResponse(BaseModel):
    session_id: str
    greeting: str

class SessionRequest(BaseModel):
    phone_number: str = ""   # 테스트용 전화번호 (SMS 발송에 사용)

class MessageRequest(BaseModel):
    text: str


@router.post("/session", response_model=SessionResponse)
async def create_session(body: SessionRequest = None):
    session_id = str(uuid.uuid4())[:8]
    phone = (body.phone_number or "").strip() if body else ""
    _sessions[session_id] = []
    _phones[session_id] = phone   # 전화번호 저장
    design = get_design()

    # 첫 인사를 LLM이 메인 프롬프트를 보고 직접 생성
    from app.providers.factory import get_llm
    llm = get_llm()
    try:
        greeting = await llm.chat_with_system(
            design.main.prompt,
            [{"role": "user", "content": "전화가 연결됐어. 첫 인사를 해줘. 한 문장으로."}],
        )
    except Exception as e:
        log.warning("첫 인사 생성 실패, 기본값 사용: %s", e)
        greeting = "안녕하세요! 무엇을 도와드릴까요?"

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
    phone  = _phones.get(session_id, "")

    # 사용자 메시지 히스토리에 추가
    history.append({"role": "user", "content": body.text})

    # 테스트 세션의 전화번호를 location_agent에서 사용할 수 있도록 DB에 저장
    if phone:
        from app.db.design_store import upsert_session
        upsert_session(session_id, phone_number=phone)

    async def event_stream():
        final_text = ""
        try:
            async for chunk in runner.run(body.text, history[:-1], design):
                data = json.dumps(chunk, ensure_ascii=False)
                yield f"data: {data}\n\n"
                if chunk.get("type") == "action":
                    act = chunk.get("action")
                    if act == "request_location":
                        dest = chunk.get("destination", "목적지")
                        # 테스트 채팅에서도 SMS 발송
                        import asyncio as _aio
                        async def _req_loc():
                            try:
                                from app.core.location_agent import request_location_and_guide
                                import os
                                async def _speak(text):
                                    pass  # 텍스트 채팅은 음성 불필요
                                await request_location_and_guide(
                                    call_id=session_id,
                                    phone_number=phone,
                                    destination=dest,
                                    speak_cb=_speak,
                                )
                            except Exception as e:
                                log.error("location_guide 오류: %s", e)
                        _aio.create_task(_req_loc())
                        data_out = json.dumps({"type": "action", "action": act,
                                               "destination": dest, "text": f"📍 {dest} 위치 링크 SMS 발송 중..."},
                                              ensure_ascii=False)
                        yield f"data: {data_out}\n\n"
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
    _phones.pop(session_id, None)
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
