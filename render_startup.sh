#!/usr/bin/env bash
# render_startup.sh
set -e

# ── Google 인증 파일 생성 ──────────────────────
if [ -n "$GOOGLE_CREDENTIALS_JSON" ]; then
    echo "$GOOGLE_CREDENTIALS_JSON" > /tmp/google_credentials.json
    export GOOGLE_APPLICATION_CREDENTIALS=/tmp/google_credentials.json
    echo "Google 인증 파일 생성 완료"
fi

# ── 프롬프트 설계 DB 복원 ──────────────────────
# DESIGN_JSON 환경변수에 저장된 설계를 DB 파일로 복원
# (재배포 시 /tmp 초기화 대응)
if [ -n "$DESIGN_JSON" ]; then
    python3 - << 'PYEOF'
import os, json, sqlite3
design_json = os.environ.get("DESIGN_JSON", "")
db_path = os.environ.get("DB_PATH", "/tmp/design.db")
if design_json:
    try:
        data = json.loads(design_json)
        con = sqlite3.connect(db_path)
        con.execute("""CREATE TABLE IF NOT EXISTS designs (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL DEFAULT 'default',
            data TEXT NOT NULL,
            updated TEXT NOT NULL DEFAULT (datetime('now'))
        )""")
        existing = con.execute("SELECT id FROM designs WHERE name='default'").fetchone()
        blob = json.dumps(data, ensure_ascii=False)
        if existing:
            con.execute("UPDATE designs SET data=?, updated=datetime('now') WHERE name='default'", (blob,))
        else:
            con.execute("INSERT INTO designs (name, data) VALUES ('default', ?)", (blob,))
        con.commit()
        con.close()
        print("프롬프트 설계 DB 복원 완료")
    except Exception as e:
        print(f"설계 복원 실패 (기본값 사용): {e}")
PYEOF
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
