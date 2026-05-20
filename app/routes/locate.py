"""
app/routes/locate.py
─────────────────────
위치 동의 웹 페이지.

GET  /locate/{token}       GPS 동의 페이지
POST /locate/{token}       위치 좌표 수신 → 세션 저장 + 에이전트 콜백
GET  /locate/status/{sid}  위치 수집 완료 여부 폴링
"""
import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.db.design_store import upsert_session, get_session_meta
from app.services.location_store import consume_token, resolve_token

log = logging.getLogger(__name__)
router = APIRouter(prefix="/locate", tags=["location"])


class LocationPayload(BaseModel):
    lat: float
    lng: float
    accuracy: float | None = None


@router.get("/{token}", response_class=HTMLResponse)
async def location_page(token: str):
    session_id = resolve_token(token)
    if not session_id:
        return HTMLResponse("<h2>링크가 만료되었거나 유효하지 않습니다.</h2>", status_code=410)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>위치 확인</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,sans-serif;display:flex;flex-direction:column;
       align-items:center;justify-content:center;min-height:100vh;
       background:#f5f5f7;padding:20px}}
  .card{{background:#fff;border-radius:20px;padding:32px 24px;max-width:360px;
         width:100%;text-align:center;box-shadow:0 4px 24px rgba(0,0,0,.08)}}
  .icon{{font-size:48px;margin-bottom:16px}}
  h2{{font-size:20px;font-weight:600;color:#1c1c1e;margin-bottom:10px}}
  p{{font-size:14px;color:#6e6e73;margin-bottom:28px;line-height:1.6}}
  button{{width:100%;padding:16px;font-size:16px;font-weight:600;border:none;
          border-radius:14px;cursor:pointer;transition:all .2s}}
  .allow{{background:#007aff;color:#fff}}
  .allow:hover{{background:#0066dd}}
  .allow:disabled{{opacity:.5;cursor:default}}
  .status{{font-size:14px;margin-top:20px;min-height:24px;line-height:1.5}}
  .ok{{color:#34c759;font-weight:500}}
  .err{{color:#ff3b30}}
  .loading{{color:#8e8e93}}
</style>
</head>
<body>
<div class="card">
  <div class="icon">📍</div>
  <h2>위치 공유 요청</h2>
  <p>AI 안내사가 현재 위치를 기반으로<br>정확한 길 안내를 제공합니다.</p>
  <button class="allow" id="btn" onclick="getLocation()">현재 위치 공유하기</button>
  <div class="status" id="status"></div>
</div>
<script>
const token = "{token}";
function getLocation(){{
  const btn = document.getElementById('btn');
  const st  = document.getElementById('status');
  btn.disabled = true;
  st.className = 'status loading';
  st.textContent = '위치를 확인하는 중...';

  if (!navigator.geolocation) {{
    st.className = 'status err';
    st.textContent = '이 브라우저는 위치 서비스를 지원하지 않습니다.';
    btn.disabled = false;
    return;
  }}

  navigator.geolocation.getCurrentPosition(
    async pos => {{
      const {{latitude: lat, longitude: lng, accuracy}} = pos.coords;
      st.textContent = '위치 확인 완료! 서버에 전송 중...';
      try {{
        const r = await fetch('/locate/' + token, {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{lat, lng, accuracy}})
        }});
        if (r.ok) {{
          st.className = 'status ok';
          st.textContent = '✓ 위치 전송 완료! 전화에서 길 안내를 들으세요.';
          btn.textContent = '전송 완료';
          btn.style.background = '#34c759';
        }} else {{
          throw new Error(await r.text());
        }}
      }} catch(e) {{
        st.className = 'status err';
        st.textContent = '오류: ' + e.message;
        btn.disabled = false;
      }}
    }},
    err => {{
      st.className = 'status err';
      const msgs = {{1:'위치 권한이 거부되었습니다.', 2:'위치를 확인할 수 없습니다.', 3:'시간이 초과되었습니다.'}};
      st.textContent = msgs[err.code] || '위치 오류: ' + err.message;
      btn.disabled = false;
    }},
    {{enableHighAccuracy: true, timeout: 10000, maximumAge: 0}}
  );
}}
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.post("/{token}")
async def receive_location(token: str, payload: LocationPayload):
    session_id = consume_token(token)
    if not session_id:
        return JSONResponse({"error": "토큰이 만료되었거나 유효하지 않습니다."}, status_code=410)

    # DB에 위치 저장
    upsert_session(
        session_id,
        location_lat=payload.lat,
        location_lng=payload.lng,
    )
    log.info("위치 수신: session=%s lat=%.5f lng=%.5f", session_id, payload.lat, payload.lng)

    # 에이전트 콜백 호출 (비동기 — 응답 지연 방지)
    async def _notify():
        try:
            from app.core.location_agent import on_location_received
            await on_location_received(session_id, payload.lat, payload.lng)
        except Exception as e:
            log.error("location 콜백 오류: %s", e)

    asyncio.create_task(_notify())
    return {"status": "ok", "session_id": session_id}


@router.get("/status/{session_id}")
async def location_status(session_id: str):
    meta = get_session_meta(session_id)
    if meta and meta.get("location_lat") is not None:
        return {"ready": True, "lat": meta["location_lat"], "lng": meta["location_lng"]}
    return {"ready": False}
