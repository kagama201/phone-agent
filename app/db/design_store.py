"""
app/db/design_store.py
───────────────────────
에이전트 설계를 SQLite에 저장/로드.

Render 무료 플랜은 재배포 시 /tmp가 초기화될 수 있으므로
DB_PATH 환경변수로 경로를 지정 가능하게 함.
Render Disk를 마운트하면 /data/design.db 로 영구 유지 가능.
기본값: /tmp/design.db (재배포 시 초기화 → DEFAULT_DESIGN으로 복원)
"""
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "/tmp/design.db")


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    """앱 시작 시 한 번 호출 — 테이블 생성"""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS designs (
                id      INTEGER PRIMARY KEY,
                name    TEXT NOT NULL DEFAULT 'default',
                data    TEXT NOT NULL,
                updated TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id   TEXT PRIMARY KEY,
                phone_number TEXT,
                location_lat REAL,
                location_lng REAL,
                pending_dest TEXT,
                created      TEXT NOT NULL DEFAULT (datetime('now')),
                updated      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
    log.info("DB 초기화 완료: %s", DB_PATH)


# ── 설계 저장/로드 ─────────────────────────────
def save_design(data: dict, name: str = "default") -> None:
    """설계 딕셔너리를 JSON으로 직렬화해 저장 (upsert)
    default 설계는 DESIGN_JSON 환경변수에도 백업 → 재배포 후 복원 가능
    """
    blob = json.dumps(data, ensure_ascii=False)
    with _conn() as con:
        existing = con.execute(
            "SELECT id FROM designs WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            con.execute(
                "UPDATE designs SET data=?, updated=datetime('now') WHERE name=?",
                (blob, name),
            )
        else:
            con.execute(
                "INSERT INTO designs (name, data) VALUES (?, ?)",
                (name, blob),
            )
    log.info("설계 저장 완료: %s", name)

    # default 설계는 Render 환경변수에도 백업
    # (재배포 시 /tmp 초기화 대응 — Render API로 업데이트)
    if name == "default":
        _backup_to_render(blob)


def _backup_to_render(blob: str) -> None:
    """Render API로 DESIGN_JSON 환경변수 업데이트 (비동기 시도, 실패 무시)"""
    render_api_key   = os.getenv("RENDER_API_KEY", "")
    render_service_id = os.getenv("RENDER_SERVICE_ID", "")
    if not render_api_key or not render_service_id:
        return  # 환경변수 미설정 시 무시
    try:
        import urllib.request, urllib.error
        import json as _json
        url = f"https://api.render.com/v1/services/{render_service_id}/env-vars"
        payload = _json.dumps([
            {"key": "DESIGN_JSON", "value": blob}
        ]).encode()
        req = urllib.request.Request(
            url, data=payload, method="PUT",
            headers={
                "Authorization": f"Bearer {render_api_key}",
                "Content-Type": "application/json",
            }
        )
        urllib.request.urlopen(req, timeout=5)
        log.info("Render 환경변수 DESIGN_JSON 백업 완료")
    except Exception as e:
        log.warning("Render 환경변수 백업 실패 (무시): %s", e)


def load_design(name: str = "default") -> dict | None:
    """저장된 설계 반환. 없으면 None"""
    with _conn() as con:
        row = con.execute(
            "SELECT data, updated FROM designs WHERE name = ?", (name,)
        ).fetchone()
    if row:
        log.info("설계 로드 완료: %s (updated: %s)", name, row["updated"])
        return json.loads(row["data"])
    return None


def list_designs() -> list[dict]:
    """저장된 설계 목록 반환"""
    with _conn() as con:
        rows = con.execute(
            "SELECT name, updated FROM designs ORDER BY updated DESC"
        ).fetchall()
    return [{"name": r["name"], "updated": r["updated"]} for r in rows]


def delete_design(name: str) -> bool:
    if name == "default":
        return False   # default는 삭제 불가
    with _conn() as con:
        con.execute("DELETE FROM designs WHERE name = ?", (name,))
    return True


# ── 세션 위치 저장/로드 ───────────────────────────
def upsert_session(session_id: str, **kwargs) -> None:
    """세션 위치/전화번호 등 업데이트"""
    with _conn() as con:
        existing = con.execute(
            "SELECT session_id FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if existing:
            sets = ", ".join(f"{k}=?" for k in kwargs)
            vals = list(kwargs.values()) + [session_id]
            con.execute(
                f"UPDATE sessions SET {sets}, updated=datetime('now') WHERE session_id=?",
                vals,
            )
        else:
            cols = "session_id, " + ", ".join(kwargs.keys())
            placeholders = ", ".join("?" * (len(kwargs) + 1))
            con.execute(
                f"INSERT INTO sessions ({cols}) VALUES ({placeholders})",
                [session_id] + list(kwargs.values()),
            )


def get_session_meta(session_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def cleanup_old_sessions(hours: int = 24) -> int:
    """오래된 세션 정리"""
    with _conn() as con:
        cur = con.execute(
            "DELETE FROM sessions WHERE updated < datetime('now', ?)",
            (f"-{hours} hours",),
        )
    return cur.rowcount
