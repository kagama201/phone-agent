"""
app/core/call_event_bus.py
───────────────────────────
통화 중 발생하는 이벤트를 브라우저 WebSocket 구독자에게 실시간 전달.

이벤트 타입:
  call_start    통화 연결
  call_end      통화 종료
  stt           사용자 발화 (STT 결과)
  agent         에이전트 응답 텍스트 (TTS 전송 전)
  smalltalk     대기 중 스몰톡
  sub_result    서브 에이전트 결과

구독 흐름:
  브라우저 → WS /ws/calls 연결
  통화 발생 → CallAgent가 bus.publish() 호출
  bus → 연결된 모든 브라우저 WS에 JSON 전송
"""
import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import WebSocket

log = logging.getLogger(__name__)


class CallEventBus:
    def __init__(self):
        # call_id → 최근 이벤트 버퍼 (새 구독자에게 히스토리 전달용)
        self._history: Dict[str, list] = {}
        # 구독 중인 브라우저 WS 목록
        self._subscribers: Set[WebSocket] = set()
        # 활성 통화 메타 {call_id: {phone, started}}
        self._active_calls: Dict[str, dict] = {}

    # ── 구독 관리 ────────────────────────────────
    async def subscribe(self, ws: WebSocket) -> None:
        self._subscribers.add(ws)
        # 현재 진행 중인 모든 통화 히스토리 즉시 전송
        for call_id, events in self._history.items():
            for ev in events:
                try:
                    await ws.send_text(json.dumps(ev, ensure_ascii=False))
                except Exception:
                    pass
        log.info("WS 구독 추가 (총 %d명)", len(self._subscribers))

    def unsubscribe(self, ws: WebSocket) -> None:
        self._subscribers.discard(ws)
        log.info("WS 구독 해제 (총 %d명)", len(self._subscribers))

    # ── 이벤트 발행 ──────────────────────────────
    async def publish(self, call_id: str, event_type: str, **kwargs) -> None:
        event = {
            "call_id": call_id,
            "type": event_type,
            **kwargs,
        }
        # 히스토리 저장 (최근 100건)
        if call_id not in self._history:
            self._history[call_id] = []
        self._history[call_id].append(event)
        if len(self._history[call_id]) > 100:
            self._history[call_id] = self._history[call_id][-100:]

        # 모든 구독자에게 브로드캐스트
        dead = set()
        for ws in self._subscribers:
            try:
                await ws.send_text(json.dumps(event, ensure_ascii=False))
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._subscribers.discard(ws)

    # ── 통화 시작/종료 ────────────────────────────
    async def call_start(self, call_id: str, phone: str = "") -> None:
        self._active_calls[call_id] = {"phone": phone}
        await self.publish(call_id, "call_start", phone=phone)

    async def call_end(self, call_id: str) -> None:
        self._active_calls.pop(call_id, None)
        self._history.pop(call_id, None)
        await self.publish(call_id, "call_end")

    # ── 상태 조회 ────────────────────────────────
    def get_active_calls(self) -> dict:
        return dict(self._active_calls)


# 싱글톤 인스턴스
bus = CallEventBus()
