"""
app/services/location_store.py
────────────────────────────────
위치 수집 토큰 관리.
토큰은 UUID로 생성되며 TTL(기본 10분) 후 만료.
"""
import time
import uuid
from typing import Dict

# {token: {"session_id": str, "expires": float}}
_tokens: Dict[str, dict] = {}

TOKEN_TTL = 600   # 10분


def create_token(session_id: str) -> str:
    """세션에 대한 일회성 위치 수집 토큰 생성"""
    # 기존 토큰 정리
    _cleanup()
    token = str(uuid.uuid4())
    _tokens[token] = {
        "session_id": session_id,
        "expires": time.time() + TOKEN_TTL,
    }
    return token


def resolve_token(token: str) -> str | None:
    """토큰 → session_id 반환. 만료되거나 없으면 None"""
    _cleanup()
    entry = _tokens.get(token)
    if not entry:
        return None
    if time.time() > entry["expires"]:
        del _tokens[token]
        return None
    return entry["session_id"]


def consume_token(token: str) -> str | None:
    """토큰 사용 후 삭제 (일회성)"""
    session_id = resolve_token(token)
    if session_id:
        _tokens.pop(token, None)
    return session_id


def _cleanup():
    now = time.time()
    expired = [t for t, v in _tokens.items() if now > v["expires"]]
    for t in expired:
        del _tokens[t]
