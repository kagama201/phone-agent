# Phone AI Agent

전화를 걸면 AI가 받아서 대화합니다.

```
전화 → Twilio → Render → Google STT → Gemini 2.5 Flash Lite → Google TTS → 음성 응답
```

---

## 사전 준비 — API 키 3종 발급

시작 전에 아래 3개 키를 준비하세요. 모두 무료입니다.

### 1. Google AI Studio 키 (Gemini LLM)

1. https://aistudio.google.com 접속
2. **Get API key** → **Create API key** → 복사

### 2. Google Cloud 서비스 계정 JSON (STT + TTS)

1. https://console.cloud.google.com → 새 프로젝트 생성
2. 검색창에서 **Cloud Speech-to-Text API** → 사용 설정
3. 검색창에서 **Cloud Text-to-Speech API** → 사용 설정
4. **IAM 및 관리자** → **서비스 계정** → **+ 서비스 계정 만들기**
   - 이름: `phone-agent-sa`
   - 역할: `Cloud Speech Client` + `Cloud Text-to-Speech Client`
5. 생성된 계정 클릭 → **키** 탭 → **키 추가** → **JSON** → 파일 다운로드
6. 다운로드된 JSON 파일을 텍스트 편집기로 열어 내용 전체를 복사해 둡니다

### 3. Twilio 계정 + 전화번호

1. https://twilio.com/try-twilio 가입 ($15 무료 크레딧 지급)
2. **Phone Numbers** → **Buy a Number** → Voice 체크 → 구입
3. **Console 홈**에서 **Account SID**, **Auth Token** 확인

---

## STEP 1 — GitHub에 올리기

```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/<username>/phone-agent.git
git branch -M main
git push -u origin main
```

---

## STEP 2 — Render 배포

### 2-1. 서비스 생성

1. https://render.com → GitHub 계정으로 로그인
2. **New** → **Web Service** → GitHub 저장소 `phone-agent` 연결
3. 빌드 설정 확인 (render.yaml이 자동 감지됩니다):
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `bash render_startup.sh`
   - Plan: **Free**

### 2-2. 환경변수 입력

**Environment** 탭에서 아래 4개 입력:

| Key | Value |
|-----|-------|
| `GOOGLE_API_KEY` | AI Studio에서 발급한 키 |
| `GOOGLE_CREDENTIALS_JSON` | 서비스 계정 JSON 파일 내용 전체 |
| `TWILIO_ACCOUNT_SID` | Twilio Console의 Account SID |
| `TWILIO_AUTH_TOKEN` | Twilio Console의 Auth Token |
| `TWILIO_PHONE_NUMBER` | 구입한 번호 (예: `+1xxxxxxxxxx`) |

**Save** → 자동 배포 시작. 완료되면 URL 확인:
```
https://phone-ai-agent.onrender.com
```

### 2-3. Deploy Hook 등록 (push 시 자동 배포)

```
Render → 서비스 → Settings → Deploy Hook → URL 복사

GitHub → Settings → Secrets and variables → Actions
  → New repository secret
  → Name: RENDER_DEPLOY_HOOK
  → Value: 복사한 URL
```

이후 `main` 브랜치에 push하면 Render에 자동 배포됩니다.

---

## STEP 3 — Twilio Webhook 등록

```
Twilio Console → Phone Numbers → Active Numbers → 구입한 번호
  → Voice Configuration
  → A CALL COMES IN: Webhook
  → URL: https://phone-ai-agent.onrender.com/incoming-call
  → HTTP Method: HTTP POST
  → Save configuration
```

---

## STEP 4 — 슬립 방지 (Render 무료 플랜)

Render 무료 플랜은 15분 비활동 시 슬립됩니다.

1. https://uptimerobot.com 무료 가입
2. **Add New Monitor** → HTTP(s)
   - URL: `https://phone-ai-agent.onrender.com/health`
   - Interval: **5 minutes**

---

## 완료 — 전화 테스트

구입한 Twilio 번호로 전화하면:

```
1. 연결 (~2초)
2. "잠시만 기다려 주세요."
3. "안녕하세요! AI 상담사 아리입니다. 무엇을 도와드릴까요?"
4. 이후 자유롭게 대화
```

로그 확인: Render Dashboard → 서비스 → **Logs**

---

## 공급자 교체

Render Dashboard → Environment 탭에서 값만 변경하면 됩니다.

| 목적 | Key | 변경값 |
|------|-----|--------|
| LLM을 Claude로 교체 | `LLM_PROVIDER` | `claude` |
| | `ANTHROPIC_API_KEY` | Anthropic 키 추가 |
| STT를 Deepgram으로 교체 | `STT_PROVIDER` | `deepgram` |
| | `DEEPGRAM_API_KEY` | Deepgram 키 추가 |
| TTS를 ElevenLabs로 교체 | `TTS_PROVIDER` | `elevenlabs` |
| | `ELEVENLABS_API_KEY` | ElevenLabs 키 추가 |

---

## 트러블슈팅

| 증상 | 해결 |
|------|------|
| 전화 후 무음 | Render Logs에서 Google 인증 오류 확인. `GOOGLE_CREDENTIALS_JSON` 값이 올바른 JSON인지 확인 |
| STT 인식 안 됨 | Google Cloud Console에서 Speech-to-Text API 활성화 확인 |
| Webhook 오류 11200 | 서버 슬립 상태. `/health` 직접 호출해 깨운 후 재시도 |
| Twilio 트라이얼 수신 불가 | Console → Verified Caller IDs에 본인 번호 추가 필요 |
