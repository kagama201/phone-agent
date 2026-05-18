"""
app/routes/test_ui.py
──────────────────────
브라우저에서 에이전트 동작을 직접 확인할 수 있는 테스트 UI.
GET /test → HTML 페이지 반환
통신망/STT/TTS 없이 LLM 대화 흐름만 테스트.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["test-ui"])

_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 에이전트 테스트</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #f5f5f7; height: 100dvh;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
  }
  .container {
    width: 100%; max-width: 560px; height: 90dvh;
    background: #fff; border-radius: 16px;
    box-shadow: 0 4px 24px rgba(0,0,0,.10);
    display: flex; flex-direction: column; overflow: hidden;
  }
  .header {
    padding: 16px 20px; border-bottom: 1px solid #e5e5ea;
    display: flex; align-items: center; gap: 10px;
  }
  .header .dot {
    width: 10px; height: 10px; border-radius: 50%; background: #ccc;
    transition: background .3s;
  }
  .header .dot.on { background: #34c759; }
  .header h2 { font-size: 15px; font-weight: 600; color: #1c1c1e; }
  .header .sid { font-size: 11px; color: #8e8e93; margin-left: auto; font-family: monospace; }
  .messages {
    flex: 1; overflow-y: auto; padding: 16px;
    display: flex; flex-direction: column; gap: 10px;
  }
  .bubble { max-width: 80%; padding: 10px 14px; border-radius: 18px; font-size: 14px; line-height: 1.5; }
  .bubble.agent {
    background: #f2f2f7; color: #1c1c1e; align-self: flex-start;
    border-bottom-left-radius: 4px;
  }
  .bubble.user {
    background: #007aff; color: #fff; align-self: flex-end;
    border-bottom-right-radius: 4px;
  }
  .bubble.system { background: none; color: #8e8e93; font-size: 12px; align-self: center; }
  .typing { display: flex; gap: 4px; align-items: center; padding: 10px 14px; }
  .typing span {
    width: 7px; height: 7px; background: #8e8e93; border-radius: 50%;
    animation: blink 1.2s infinite;
  }
  .typing span:nth-child(2) { animation-delay: .2s; }
  .typing span:nth-child(3) { animation-delay: .4s; }
  @keyframes blink { 0%,80%,100%{opacity:.2} 40%{opacity:1} }
  .input-row {
    padding: 12px 16px; border-top: 1px solid #e5e5ea;
    display: flex; gap: 8px;
  }
  .input-row input {
    flex: 1; padding: 10px 14px; border: 1px solid #e5e5ea; border-radius: 20px;
    font-size: 14px; outline: none; background: #f2f2f7;
  }
  .input-row input:focus { border-color: #007aff; background: #fff; }
  .input-row button {
    padding: 10px 16px; background: #007aff; color: #fff; border: none;
    border-radius: 20px; font-size: 14px; cursor: pointer; white-space: nowrap;
  }
  .input-row button:disabled { background: #c7c7cc; cursor: default; }
  .btn-row {
    padding: 0 16px 12px; display: flex; gap: 8px;
  }
  .btn-row button {
    flex: 1; padding: 8px; border: 1px solid #e5e5ea; border-radius: 8px;
    font-size: 12px; cursor: pointer; background: #f2f2f7; color: #3a3a3c;
  }
  .btn-row button:hover { background: #e5e5ea; }
  .scenario-row {
    padding: 0 16px 10px; display: flex; gap: 6px; flex-wrap: wrap;
  }
  .scenario-btn {
    font-size: 11px; padding: 5px 10px; border: 1px solid #e5e5ea;
    border-radius: 12px; cursor: pointer; background: #f2f2f7; color: #3a3a3c;
  }
  .scenario-btn:hover { background: #e5e5ea; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="dot" id="statusDot"></div>
    <h2>AI 에이전트 테스트</h2>
    <span class="sid" id="sidLabel">-</span>
  </div>

  <div class="messages" id="messages">
    <div class="bubble system">세션 시작 버튼을 눌러 대화를 시작하세요</div>
  </div>

  <div class="scenario-row" id="scenarioRow" style="display:none">
    <button class="scenario-btn" onclick="sendScenario('배송 조회하고 싶어요')">📦 배송 조회</button>
    <button class="scenario-btn" onclick="sendScenario('환불 신청하고 싶어요')">↩️ 환불 요청</button>
    <button class="scenario-btn" onclick="sendScenario('제품에 문제가 있어요')">⚠️ 불량 신고</button>
    <button class="scenario-btn" onclick="sendScenario('비밀번호를 잊어버렸어요')">🔑 계정 문제</button>
  </div>

  <div class="input-row">
    <input id="inputBox" type="text" placeholder="세션을 먼저 시작하세요..." disabled
      onkeydown="if(event.key==='Enter') send()">
    <button id="sendBtn" onclick="send()" disabled>전송</button>
  </div>

  <div class="btn-row">
    <button onclick="startSession()">🟢 세션 시작</button>
    <button onclick="resetSession()">🔄 대화 초기화</button>
    <button onclick="showHistory()">📋 히스토리</button>
  </div>
</div>

<script>
let sessionId = null;
let busy = false;

const $ = id => document.getElementById(id);

function addBubble(role, text) {
  const msgs = $('messages');
  // 빈 상태 메시지 제거
  const sys = msgs.querySelector('.bubble.system');
  if (sys) sys.remove();

  const div = document.createElement('div');
  div.className = 'bubble ' + role;
  div.textContent = text;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return div;
}

function showTyping() {
  const msgs = $('messages');
  const div = document.createElement('div');
  div.id = 'typing';
  div.className = 'bubble agent typing';
  div.innerHTML = '<span></span><span></span><span></span>';
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}
function hideTyping() {
  const el = $('typing');
  if (el) el.remove();
}

async function startSession() {
  if (sessionId) {
    // 기존 세션 종료
    await fetch(`/chat/session/${sessionId}`, { method: 'DELETE' });
  }
  $('messages').innerHTML = '';
  addBubble('system', '세션 연결 중...');

  const res = await fetch('/chat/session', { method: 'POST' });
  const data = await res.json();
  sessionId = data.session_id;

  $('messages').innerHTML = '';
  addBubble('agent', data.greeting);
  $('statusDot').className = 'dot on';
  $('sidLabel').textContent = 'session: ' + sessionId;
  $('inputBox').disabled = false;
  $('inputBox').placeholder = '메시지를 입력하세요...';
  $('sendBtn').disabled = false;
  $('scenarioRow').style.display = 'flex';
  $('inputBox').focus();
}

async function send() {
  if (!sessionId || busy) return;
  const text = $('inputBox').value.trim();
  if (!text) return;

  $('inputBox').value = '';
  addBubble('user', text);
  await _ask(text);
}

async function sendScenario(text) {
  if (!sessionId || busy) return;
  addBubble('user', text);
  await _ask(text);
}

async function _ask(text) {
  busy = true;
  $('sendBtn').disabled = true;
  showTyping();

  try {
    const res = await fetch(`/chat/session/${sessionId}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    hideTyping();
    addBubble('agent', data.agent);
  } catch (e) {
    hideTyping();
    addBubble('system', '오류가 발생했습니다: ' + e.message);
  } finally {
    busy = false;
    $('sendBtn').disabled = false;
    $('inputBox').focus();
  }
}

async function resetSession() {
  if (!sessionId) return;
  await fetch(`/chat/session/${sessionId}`, { method: 'DELETE' });
  sessionId = null;
  $('messages').innerHTML = '';
  $('statusDot').className = 'dot';
  $('sidLabel').textContent = '-';
  $('inputBox').disabled = true;
  $('inputBox').placeholder = '세션을 먼저 시작하세요...';
  $('sendBtn').disabled = true;
  $('scenarioRow').style.display = 'none';
  addBubble('system', '세션이 종료되었습니다. 새 세션을 시작하세요.');
}

async function showHistory() {
  if (!sessionId) { alert('세션을 먼저 시작하세요.'); return; }
  const res = await fetch(`/chat/session/${sessionId}/history`);
  const data = await res.json();
  const lines = data.history.map(m => `[${m.role}] ${m.content}`).join('\\n\\n');
  alert(lines || '(대화 없음)');
}
</script>
</body>
</html>"""


@router.get("/test", response_class=HTMLResponse)
async def test_ui():
    """브라우저 테스트 UI"""
    return HTMLResponse(content=_HTML)
