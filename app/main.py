"""
app/main.py
────────────
FastAPI 애플리케이션 진입점.

라우터 구분:
  /test          브라우저 테스트 UI  (통신망 불필요)
  /chat/*        텍스트 채팅 API     (통신망 불필요)
  /incoming-call Twilio Webhook      (통신망 필요)
  /media-stream  WebSocket 오디오    (통신망 필요)
"""
import logging
import os

import uvicorn
from fastapi import FastAPI

from app.routes.test_ui      import router as ui_router
from app.routes.chat         import router as chat_router
from app.routes.twiml        import router as twiml_router
from app.routes.media_stream import router as ws_router, active_call_count

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(title="Phone AI Agent", version="0.1.0")

# ── 통신망 불필요 (에이전트 로직 테스트) ──
app.include_router(ui_router)
app.include_router(chat_router)

# ── 통신망 필요 (Twilio 연동) ──────────────
app.include_router(twiml_router)
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok", "active_calls": active_call_count()}


@app.get("/")
async def root():
    return {"message": "Phone AI Agent", "test_ui": "/test", "api_docs": "/docs"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
