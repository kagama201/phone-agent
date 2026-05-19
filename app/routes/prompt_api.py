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

from app.db.design_store import list_designs, delete_design, load_design, save_design
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


# ── 설계 목록 조회 ────────────────────────────────
@router.get("/designs")
async def list_all_designs():
    """저장된 설계 이름 목록 반환"""
    return {"designs": list_designs()}


# ── 이름 붙여 저장 ────────────────────────────────
@router.post("/design/{name}")
async def save_named_design(name: str, body: DesignSchema):
    """현재 설계를 특정 이름으로 저장 (스냅샷)"""
    from app.db.design_store import save_design as _save
    _save(body.model_dump(), name)
    return {"status": "saved", "name": name}


# ── 이름으로 불러오기 ──────────────────────────────
@router.get("/design/{name}")
async def load_named_design(name: str):
    """저장된 특정 설계 로드"""
    data = load_design(name)
    if not data:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"설계 '{name}'을 찾을 수 없습니다.")
    return data


# ── 이름으로 삭제 ──────────────────────────────────
@router.delete("/design/{name}")
async def delete_named_design(name: str):
    """저장된 설계 삭제 (default는 삭제 불가)"""
    ok = delete_design(name)
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="default 설계는 삭제할 수 없습니다.")
    return {"status": "deleted", "name": name}


# ── 이름으로 불러와서 현재 설계로 적용 ────────────────
@router.post("/design/{name}/apply")
async def apply_named_design(name: str):
    """저장된 설계를 현재 활성 설계로 적용"""
    data = load_design(name)
    if not data:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"설계 '{name}'을 찾을 수 없습니다.")
    from app.core.multi_agent import _dict_to_design, set_design
    set_design(_dict_to_design(data))
    return {"status": "applied", "name": name}
