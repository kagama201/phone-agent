"""
app/routes/prompt_api.py
─────────────────────────
에이전트 설계 저장/로드 + 멀티에이전트 테스트 실행 API.

  GET  /prompt/design          현재 설계 조회
  POST /prompt/design          설계 저장
  POST /prompt/reset           기본값으로 초기화
  POST /prompt/run             멀티에이전트 테스트 실행 (SSE 스트리밍)
"""
import json
import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.multi_agent import (
    AgentDesign, MainAgentConfig, SubAgentConfig,
    DEFAULT_DESIGN, get_design, set_design, MultiAgentRunner,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/prompt", tags=["prompt-design"])


# ── Pydantic 스키마 ──────────────────────────────
class SubAgentSchema(BaseModel):
    id: str
    name: str
    description: str
    prompt: str
    enabled: bool = True
    next_agents: list[str] = []


class MainAgentSchema(BaseModel):
    prompt: str
    smalltalk_prompt: str
    max_sub_agents: int = 3


class DesignSchema(BaseModel):
    main: MainAgentSchema
    sub_agents: list[SubAgentSchema]


class RunRequest(BaseModel):
    message: str
    history: list[dict] = []


# ── 헬퍼 ────────────────────────────────────────
def design_to_schema(d: AgentDesign) -> dict:
    return {
        "main": {
            "prompt": d.main.prompt,
            "smalltalk_prompt": d.main.smalltalk_prompt,
            "max_sub_agents": d.main.max_sub_agents,
        },
        "sub_agents": [
            {
                "id": a.id, "name": a.name,
                "description": a.description, "prompt": a.prompt,
                "enabled": a.enabled, "next_agents": a.next_agents,
            }
            for a in d.sub_agents
        ],
    }


def schema_to_design(s: DesignSchema) -> AgentDesign:
    return AgentDesign(
        main=MainAgentConfig(
            prompt=s.main.prompt,
            smalltalk_prompt=s.main.smalltalk_prompt,
            max_sub_agents=s.main.max_sub_agents,
        ),
        sub_agents=[
            SubAgentConfig(
                id=a.id, name=a.name,
                description=a.description, prompt=a.prompt,
                enabled=a.enabled, next_agents=a.next_agents,
            )
            for a in s.sub_agents
        ],
    )


# ── 엔드포인트 ───────────────────────────────────
@router.get("/design")
async def get_design_api():
    return design_to_schema(get_design())


@router.post("/design")
async def save_design(body: DesignSchema):
    set_design(schema_to_design(body))
    return {"status": "saved"}


@router.post("/reset")
async def reset_design():
    set_design(DEFAULT_DESIGN)
    return {"status": "reset", "design": design_to_schema(DEFAULT_DESIGN)}


@router.post("/run")
async def run_agent(body: RunRequest):
    """멀티에이전트 실행 — SSE 스트리밍으로 단계별 결과 전송"""
    design = get_design()
    runner = MultiAgentRunner()

    async def event_stream():
        try:
            async for chunk in runner.run(body.message, body.history, design):
                data = json.dumps(chunk, ensure_ascii=False)
                yield f"data: {data}\n\n"
        except Exception as e:
            log.exception("run_agent 오류")
            err = json.dumps({"type": "error", "text": str(e)}, ensure_ascii=False)
            yield f"data: {err}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
