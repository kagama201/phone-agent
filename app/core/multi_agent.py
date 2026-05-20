"""
app/core/multi_agent.py
────────────────────────
멀티에이전트 실행 엔진.

구조:
  MainAgent  — 사용자 의도 파악 → 서브 에이전트 선택 → 결과 취합 → 최종 응답
               응답이 길어질 경우 스몰톡으로 대기 커버
  SubAgent   — 각 도메인 전담 (교통/여행/예약/검색/문의 등)

에이전트 설계(AgentConfig)는 /prompt UI에서 편집하고
런타임에 메모리에서 로드한다. 향후 DB 저장으로 확장 가능.
"""
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.providers.factory import get_llm
from app.db.design_store import save_design, load_design

log = logging.getLogger(__name__)


# ── 에이전트 설정 데이터 구조 ────────────────────
@dataclass
class SubAgentConfig:
    id: str
    name: str
    description: str          # 메인 에이전트가 호출 여부를 판단하는 설명
    prompt: str               # 서브 에이전트 시스템 프롬프트
    enabled: bool = True
    next_agents: list[str] = field(default_factory=list)   # 후속 호출 에이전트 ID


@dataclass
class MainAgentConfig:
    prompt: str
    smalltalk_prompt: str
    max_sub_agents: int = 3   # 한 번에 병렬 호출할 최대 서브 에이전트 수


@dataclass
class AgentDesign:
    main: MainAgentConfig
    sub_agents: list[SubAgentConfig]


# ── 기본 에이전트 설계 ───────────────────────────
DEFAULT_DESIGN = AgentDesign(
    main=MainAgentConfig(
        prompt="""당신은 AI 전화 안내사 '아리'입니다.
사용자 메시지를 분석해 필요한 서브 에이전트를 선택하고, 결과를 취합해 자연스러운 한국어로 답변하세요.

반드시 아래 JSON 형식으로만 응답하세요:
{
  "sub_agents": ["교통", "여행"],  // 필요한 서브 에이전트 ID 목록 (없으면 [])
  "direct_answer": "",             // 서브 에이전트 없이 직접 답할 내용 (있으면 sub_agents=[])
  "smalltalk": "잠깐만요, 찾아볼게요~"  // 처리 중 사용자에게 할 말
}""",
        smalltalk_prompt="""당신은 친근한 AI 안내사입니다.
사용자가 기다리는 동안 자연스럽고 짧은 스몰톡을 한 문장으로 해주세요.
예: "잠깐만요!", "찾아보고 있어요~", "조금만 기다려주세요!"
JSON 없이 문장만 출력하세요.""",
    ),
    sub_agents=[
        SubAgentConfig(
            id="교통",
            name="교통 안내",
            description="길찾기, 대중교통, 버스/지하철 노선, 소요시간, 위치 안내",
            prompt="""당신은 교통 전문 AI입니다.

[목적지 처리 규칙]
1. 사용자가 특정 장소로 가고 싶다고 하면 목적지를 파악하세요.
2. 목적지가 상호명(편의점, 카페, 마트 등)처럼 모호하면 지역명을 먼저 확인하세요.
   예: "다이소 어느 지점으로 가실건가요? 가까운 지역을 말씀해주세요."
   예: "스타벅스 근처 지역이 어디신가요?"
3. 목적지가 명확하면(역, 특정 건물, 지역+상호명) 반드시 아래 JSON을 응답 끝에 추가하세요:
   {"action": "request_location", "destination": "목적지 전체명"}

[위치 확인 안내]
- 대화 중 사용자의 위치가 확인된 경우 반드시 아래 형식으로 안내하세요:
  "확인된 현재 위치는 {주소}입니다."
- 위치 정보를 바탕으로 최적 경로를 안내하세요.

[SMS 발송 요청 처리]
사용자가 "문자로 보내줘", "문자 보내줘", "SMS로 보내줘" 등을 요청하면:
{"action": "send_sms"}
를 응답 끝에 추가하세요.

[응답 예시]
사용자: "홍대 가고 싶어"
응답: "홍대입구까지 안내해드릴게요. 위치 파악을 위해 SMS로 링크를 보내드릴게요.
{"action": "request_location", "destination": "홍대입구역"}"

사용자: "다이소 가고 싶어"
응답: "다이소 어느 지점으로 가실건가요? 근처 지역명을 말씀해주시면 정확히 안내해드릴게요."

사용자: "문자로 보내줘"
응답: "상세 길 안내를 문자로 보내드릴게요.
{"action": "send_sms"}"

절대 주변 건물을 물어보거나 위치를 직접 설명해달라고 하지 마세요.
JSON 액션을 포함할 때는 반드시 destination에 구체적인 장소명을 입력하세요.""",
            enabled=True,
            next_agents=[],
        ),
        SubAgentConfig(
            id="여행",
            name="여행 안내",
            description="여행지 추천, 맛집, 카페, 행사/이벤트, 포토스팟, 관광 명소",
            prompt="""당신은 여행 전문 AI입니다.
여행지 추천, 맛집, 카페, 행사/이벤트, 포토스팟, 관광 명소를 담당합니다.
감성적이고 흥미로운 정보를 2~3문장으로 소개하세요.""",
            enabled=True,
            next_agents=[],
        ),
        SubAgentConfig(
            id="예약",
            name="예약 안내",
            description="식당, 숙소, 공연, 병원, 시설 예약 방법 안내",
            prompt="""당신은 예약 안내 AI입니다.
식당, 숙소, 공연, 병원, 시설 예약 방법을 담당합니다.
예약 경로와 주의사항을 2~3문장으로 안내하세요.""",
            enabled=True,
            next_agents=[],
        ),
        SubAgentConfig(
            id="검색",
            name="정보 검색",
            description="일반 정보 검색, 사실 확인, 최신 정보 안내",
            prompt="""당신은 정보 검색 AI입니다.
일반 정보 검색, 사실 확인, 최신 정보 안내를 담당합니다.
정확하고 명확한 정보를 2~3문장으로 제공하세요.
확실하지 않은 정보는 그렇다고 밝히세요.""",
            enabled=True,
            next_agents=[],
        ),
        SubAgentConfig(
            id="문의",
            name="생활 문의",
            description="복지 안내, 보이스피싱 판단, 의약품 안내, 법률 상담, 행정 문의",
            prompt="""당신은 생활 문의 AI입니다.
복지 서비스, 보이스피싱 판단, 의약품 정보, 법률 기초 상담, 행정 문의를 담당합니다.
신중하고 정확하게 2~3문장으로 안내하고, 전문가 상담을 권고하세요.""",
            enabled=True,
            next_agents=[],
        ),
    ],
)

# 런타임 캐시 (DB 로드 후 메모리 캐싱)
_current_design: AgentDesign | None = None


def _design_to_dict(d: AgentDesign) -> dict:
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


def _dict_to_design(d: dict) -> AgentDesign:
    m = d["main"]
    return AgentDesign(
        main=MainAgentConfig(
            prompt=m["prompt"],
            smalltalk_prompt=m["smalltalk_prompt"],
            max_sub_agents=m.get("max_sub_agents", 3),
        ),
        sub_agents=[
            SubAgentConfig(
                id=a["id"], name=a["name"],
                description=a["description"], prompt=a["prompt"],
                enabled=a.get("enabled", True),
                next_agents=a.get("next_agents", []),
            )
            for a in d.get("sub_agents", [])
        ],
    )


def get_design() -> AgentDesign:
    """DB에서 로드 (캐시 우선). DB에 없으면 DEFAULT_DESIGN 반환."""
    global _current_design
    if _current_design is not None:
        return _current_design
    try:
        data = load_design("default")
        if data:
            _current_design = _dict_to_design(data)
            return _current_design
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("설계 DB 로드 실패, 기본값 사용: %s", e)
    _current_design = DEFAULT_DESIGN
    return _current_design


def set_design(design: AgentDesign) -> None:
    """메모리 캐시 + DB 동시 저장."""
    global _current_design
    _current_design = design
    try:
        save_design(_design_to_dict(design), "default")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("설계 DB 저장 실패: %s", e)


# ── 멀티에이전트 실행 ────────────────────────────
class MultiAgentRunner:
    """
    한 세션의 멀티에이전트 대화를 실행.
    history: 대화 히스토리 (메인 에이전트 관점)
    """

    def __init__(self):
        self._llm = get_llm()

    async def run(
        self,
        user_text: str,
        history: list[dict],
        design: AgentDesign,
    ) -> AsyncIterator[dict]:
        """
        스트리밍 방식으로 실행 단계를 yield.
        yield 형식: {"type": "...", "text": "...", "meta": {...}}

        type 목록:
          smalltalk    — 처리 중 스몰톡
          sub_result   — 서브 에이전트 결과
          final        — 최종 답변
          error        — 오류
        """
        # 1. 메인 에이전트: 의도 파악 + 서브 에이전트 선택
        dispatch = await self._dispatch(user_text, history, design)
        yield {"type": "smalltalk", "text": dispatch.get("smalltalk", "잠깐만요~"), "meta": {}}

        direct = dispatch.get("direct_answer", "").strip()
        if direct:
            yield {"type": "final", "text": direct, "meta": {"sub_agents_used": []}}
            return

        selected_ids = dispatch.get("sub_agents", [])
        enabled_map = {a.id: a for a in design.sub_agents if a.enabled}
        to_run = [enabled_map[i] for i in selected_ids if i in enabled_map]

        if not to_run:
            # 매칭 서브 에이전트 없으면 메인이 직접 답변
            answer = await self._direct_answer(user_text, history, design.main)
            yield {"type": "final", "text": answer, "meta": {"sub_agents_used": []}}
            return

        # 2. 서브 에이전트 병렬 실행
        sub_results = await asyncio.gather(
            *[self._run_sub(user_text, sub) for sub in to_run],
            return_exceptions=True,
        )

        results = []
        action_triggered = False

        for sub, result in zip(to_run, sub_results):
            if isinstance(result, Exception):
                log.error("서브 에이전트 오류 [%s]: %s", sub.id, result)
                continue

            # JSON 액션 감지 (예: request_location)
            action = self._parse_action(result)
            if action and not action_triggered:
                action_triggered = True
                act_type = action.get("action")

                import re as _re2
                def _strip_json(t):
                    return _re2.sub(r'[{][^}]+[}]', '', t).strip()

                if act_type == "request_location":
                    dest = action.get("destination", "")
                    yield {
                        "type": "action",
                        "action": "request_location",
                        "destination": dest,
                        "meta": {"agent_id": sub.id},
                    }
                    clean = _strip_json(result)
                    if clean:
                        yield {"type": "sub_result", "text": clean, "meta": {"agent_id": sub.id, "agent_name": sub.name}}
                    results.append({"id": sub.id, "name": sub.name, "answer": clean or result})
                    continue

                if act_type == "send_sms":
                    yield {
                        "type": "action",
                        "action": "send_sms",
                        "meta": {"agent_id": sub.id},
                    }
                    clean = _strip_json(result)
                    if clean:
                        yield {"type": "sub_result", "text": clean, "meta": {"agent_id": sub.id, "agent_name": sub.name}}
                    results.append({"id": sub.id, "name": sub.name, "answer": "SMS 발송 요청"})
                    continue

            yield {"type": "sub_result", "text": result, "meta": {"agent_id": sub.id, "agent_name": sub.name}}
            results.append({"id": sub.id, "name": sub.name, "answer": result})

        # 3. 후속 에이전트 처리 (next_agents)
        for sub in to_run:
            for nid in sub.next_agents:
                if nid in enabled_map and nid not in selected_ids:
                    next_result = await self._run_sub(user_text, enabled_map[nid])
                    yield {"type": "sub_result", "text": next_result, "meta": {"agent_id": nid, "agent_name": enabled_map[nid].name, "triggered_by": sub.id}}
                    results.append({"id": nid, "name": enabled_map[nid].name, "answer": next_result})

        # 4. 최종 취합
        final = await self._synthesize(user_text, results, design.main)
        yield {"type": "final", "text": final, "meta": {"sub_agents_used": [r["id"] for r in results]}}

    async def _dispatch(self, user_text: str, history: list[dict], design: AgentDesign) -> dict:
        """메인 에이전트: 서브 에이전트 선택 및 스몰톡 결정"""
        sub_list = "\n".join(
            f'  - "{a.id}": {a.description}'
            for a in design.sub_agents if a.enabled
        )
        dispatch_prompt = f"""{design.main.prompt}

사용 가능한 서브 에이전트:
{sub_list}"""

        msgs = list(history[-6:])  # 최근 6턴
        msgs.append({"role": "user", "content": user_text})

        try:
            raw = await self._llm.chat_with_system(dispatch_prompt, msgs)
            # JSON 추출
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
        except Exception as e:
            log.warning("dispatch 파싱 실패: %s", e)
        return {"sub_agents": [], "direct_answer": "", "smalltalk": "잠깐만요~"}

    async def _run_sub(self, user_text: str, sub: SubAgentConfig) -> str:
        """서브 에이전트 단독 실행"""
        return await self._llm.chat_with_system(
            sub.prompt,
            [{"role": "user", "content": user_text}],
        )

    def _parse_action(self, text: str) -> dict | None:
        """서브 에이전트 응답에서 JSON 액션 추출"""
        import json, re
        m = re.search(r'\{[^}]+\}', text)
        if m:
            try:
                data = json.loads(m.group())
                if "action" in data:
                    return data
            except Exception:
                pass
        return None

    async def _direct_answer(self, user_text: str, history: list[dict], main: MainAgentConfig) -> str:
        simple_prompt = main.prompt.split("\n")[0] + "\n2~3문장으로 자연스럽게 답변하세요."
        msgs = list(history[-6:]) + [{"role": "user", "content": user_text}]
        return await self._llm.chat_with_system(simple_prompt, msgs)

    async def _synthesize(self, user_text: str, results: list[dict], main: MainAgentConfig) -> str:
        """서브 에이전트 결과 취합 → 최종 자연스러운 답변"""
        context = "\n\n".join(f"[{r['name']}]\n{r['answer']}" for r in results)
        synth_prompt = f"""{main.prompt.split(chr(10))[0]}
아래 전문가들의 답변을 자연스럽게 통합해 사용자에게 3~4문장으로 안내하세요.
중복 내용은 제거하고, 가장 유용한 정보 위주로 정리하세요.

전문가 답변:
{context}"""
        return await self._llm.chat_with_system(
            synth_prompt,
            [{"role": "user", "content": user_text}],
        )
