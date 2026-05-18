#!/usr/bin/env bash
# render_startup.sh
# ──────────────────
# Render는 파일 시스템이 없으므로 Google 서비스 계정 JSON을
# 환경변수(GOOGLE_CREDENTIALS_JSON)에 넣고 시작 시 파일로 씀.

set -e

if [ -n "$GOOGLE_CREDENTIALS_JSON" ]; then
    echo "$GOOGLE_CREDENTIALS_JSON" > /tmp/google_credentials.json
    export GOOGLE_APPLICATION_CREDENTIALS=/tmp/google_credentials.json
    echo "Google 인증 파일 생성 완료"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
