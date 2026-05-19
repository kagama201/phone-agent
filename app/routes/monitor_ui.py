"""
app/routes/monitor_ui.py
─────────────────────────
GET /monitor — 실시간 통화 모니터링 UI.
통화가 연결되면 STT/에이전트/TTS 내용이 자동으로 표시된다.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["monitor"])

_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>통화 모니터</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#f5f5f7;height:100dvh;display:flex;flex-direction:column}
header{padding:12px 20px;background:#fff;border-bottom:1px solid #e5e5ea;
       display:flex;align-items:center;gap:12px;flex-shrink:0}
header h1{font-size:15px;font-weight:600;color:#1c1c1e}
.ws-dot{width:8px;height:8px;border-radius:50%;background:#ccc;flex-shrink:0}
.ws-dot.on{background:#34c759}
.ws-dot.err{background:#ff3b30}
.spacer{flex:1}
.btn{padding:6px 14px;font-size:12px;border-radius:7px;border:1px solid #e5e5ea;
     cursor:pointer;background:#f5f5f7;color:#3a3a3c}
.btn:hover{background:#e5e5ea}
.btn.primary{background:#007aff;color:#fff;border-color:#007aff}

/* 레이아웃 */
.layout{display:flex;flex:1;overflow:hidden;gap:0}

/* 왼쪽: 통화 목록 */
.call-list{width:220px;min-width:180px;background:#fff;border-right:1px solid #e5e5ea;
           display:flex;flex-direction:column;overflow:hidden;flex-shrink:0}
.call-list-header{padding:10px 14px;font-size:12px;font-weight:500;
                  color:#8e8e93;border-bottom:1px solid #e5e5ea;flex-shrink:0}
.call-items{flex:1;overflow-y:auto}
.call-item{padding:10px 14px;cursor:pointer;border-bottom:1px solid #f2f2f7;
           display:flex;flex-direction:column;gap:3px}
.call-item:hover{background:#f5f5f7}
.call-item.active{background:#e3f2fd}
.call-id{font-size:12px;font-family:monospace;color:#1c1c1e;font-weight:500}
.call-phone{font-size:11px;color:#8e8e93}
.call-badge{font-size:10px;padding:1px 6px;border-radius:6px;
            background:#e8f5e9;color:#2e7d32;border:1px solid #c8e6c9;
            display:inline-block;width:fit-content}
.call-badge.ended{background:#f5f5f5;color:#8e8e93;border-color:#e5e5ea}
.no-calls{padding:20px 14px;font-size:12px;color:#8e8e93;text-align:center}

/* 오른쪽: 대화 내용 */
.chat-area{flex:1;display:flex;flex-direction:column;overflow:hidden}
.chat-header{padding:10px 16px;border-bottom:1px solid #e5e5ea;
             display:flex;align-items:center;gap:8px;flex-shrink:0;background:#fff}
.chat-header .cid{font-size:13px;font-weight:500;color:#1c1c1e}
.chat-header .cphone{font-size:12px;color:#8e8e93}
.messages{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:8px}

/* 메시지 버블 */
.msg{display:flex;flex-direction:column;gap:2px}
.msg.user{align-items:flex-end}
.msg.agent{align-items:flex-start}
.msg.system{align-items:center}
.msg.sub{align-items:flex-start}

.bubble{max-width:78%;padding:8px 12px;border-radius:14px;font-size:13px;line-height:1.5}
.msg.user .bubble{background:#007aff;color:#fff;border-bottom-right-radius:3px}
.msg.agent .bubble{background:#f2f2f7;color:#1c1c1e;border-bottom-left-radius:3px}
.msg.system .bubble{background:none;color:#8e8e93;font-size:11px;max-width:100%;text-align:center}
.msg.smalltalk .bubble{background:#fffde7;color:#795548;border:1px solid #fff176;
                        font-style:italic;border-radius:10px;font-size:12px}
.msg.sub .bubble{background:#e8f5e9;color:#1b5e20;border:1px solid #c8e6c9;font-size:12px;
                 border-bottom-left-radius:3px}
.sub-label{font-size:10px;color:#388e3c;font-weight:600;padding-left:3px;margin-bottom:1px}

.phase-tag{font-size:10px;padding:1px 6px;border-radius:5px;margin-left:5px;
           background:#e3f2fd;color:#1565c0;border:1px solid #90caf9}
.phase-tag.greeting{background:#e8f5e9;color:#2e7d32;border-color:#a5d6a7}
.phase-tag.tts{background:#fce4ec;color:#880e4f;border-color:#f48fb1}

.typing-row{display:flex;align-items:center;gap:4px;padding:4px 0}
.tdot{width:5px;height:5px;border-radius:50%;background:#8e8e93;animation:blink 1.2s infinite}
.tdot:nth-child(2){animation-delay:.2s}.tdot:nth-child(3){animation-delay:.4s}
@keyframes blink{0%,80%,100%{opacity:.2}40%{opacity:1}}

.empty-state{flex:1;display:flex;align-items:center;justify-content:center;
             color:#8e8e93;font-size:14px;flex-direction:column;gap:8px}
.empty-icon{font-size:36px;opacity:.3}
</style>
</head>
<body>

<header>
  <div class="ws-dot" id="wsDot"></div>
  <h1>통화 모니터</h1>
  <span id="wsStatus" style="font-size:12px;color:#8e8e93">연결 중...</span>
  <div class="spacer"></div>
  <a href="/prompt" style="font-size:12px;color:#007aff;text-decoration:none">에이전트 설계 →</a>
</header>

<div class="layout">
  <!-- 통화 목록 -->
  <div class="call-list">
    <div class="call-list-header">활성 통화</div>
    <div class="call-items" id="callItems">
      <div class="no-calls" id="noCalls">통화 없음</div>
    </div>
  </div>

  <!-- 대화 내용 -->
  <div class="chat-area">
    <div class="chat-header" id="chatHeader" style="display:none">
      <div>
        <span class="cid" id="headerCallId"></span>
        <span class="cphone" id="headerPhone"></span>
      </div>
    </div>
    <div class="messages" id="messages">
      <div class="empty-state">
        <div class="empty-icon">📞</div>
        <span>통화가 연결되면 대화 내용이 여기에 표시됩니다</span>
      </div>
    </div>
  </div>
</div>

<script>
// ── 상태 ──────────────────────────────────────
const calls = {};      // call_id → {phone, messages, element}
let activeCallId = null;
let ws = null;
let reconnectTimer = null;

// ── WebSocket ─────────────────────────────────
function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/calls`);

  ws.onopen = () => {
    document.getElementById('wsDot').className = 'ws-dot on';
    document.getElementById('wsStatus').textContent = '연결됨';
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  };

  ws.onclose = () => {
    document.getElementById('wsDot').className = 'ws-dot err';
    document.getElementById('wsStatus').textContent = '재연결 중...';
    reconnectTimer = setTimeout(connect, 3000);
  };

  ws.onerror = () => {
    document.getElementById('wsDot').className = 'ws-dot err';
  };

  ws.onmessage = e => {
    try { handleEvent(JSON.parse(e.data)); } catch(err) {}
  };
}

// ── 이벤트 처리 ───────────────────────────────
function handleEvent(ev) {
  const {call_id, type} = ev;

  if (type === 'call_start') {
    startCall(call_id, ev.phone || '');
    return;
  }
  if (type === 'call_end') {
    endCall(call_id);
    return;
  }

  // 통화가 없으면 자동 생성 (히스토리 복원)
  if (!calls[call_id]) startCall(call_id, '');

  if (type === 'stt') {
    addMsg(call_id, 'user', ev.text);
  } else if (type === 'agent') {
    removeTyping(call_id);
    const tag = ev.phase === 'greeting' ? 'greeting' : '';
    addMsg(call_id, 'agent', ev.text, tag);
  } else if (type === 'smalltalk') {
    addMsg(call_id, 'smalltalk', ev.text);
  } else if (type === 'sub_result') {
    addMsg(call_id, 'sub', ev.text, '', ev.agent_name || ev.agent_id || '');
  } else if (type === 'tts_start') {
    showTyping(call_id);
  } else if (type === 'tts_end') {
    removeTyping(call_id);
  }
}

// ── 통화 목록 관리 ────────────────────────────
function startCall(call_id, phone) {
  if (calls[call_id]) return;

  const item = document.createElement('div');
  item.className = 'call-item';
  item.id = 'call-item-' + call_id;
  item.innerHTML = `
    <div class="call-id">${call_id.slice(0, 12)}</div>
    <div class="call-phone">${phone || '번호 미표시'}</div>
    <span class="call-badge">통화중</span>`;
  item.onclick = () => selectCall(call_id);
  document.getElementById('noCalls').style.display = 'none';
  document.getElementById('callItems').appendChild(item);

  calls[call_id] = {phone, element: item, msgs: []};

  // 첫 통화면 자동 선택
  if (!activeCallId) selectCall(call_id);
}

function endCall(call_id) {
  const c = calls[call_id];
  if (!c) return;
  const badge = c.element.querySelector('.call-badge');
  if (badge) { badge.textContent = '종료'; badge.className = 'call-badge ended'; }
  addMsg(call_id, 'system', '통화가 종료되었습니다');
  // 5초 후 목록에서 제거
  setTimeout(() => {
    c.element.remove();
    delete calls[call_id];
    if (activeCallId === call_id) {
      activeCallId = null;
      const remaining = Object.keys(calls);
      if (remaining.length > 0) selectCall(remaining[remaining.length - 1]);
      else clearChat();
    }
    if (Object.keys(calls).length === 0)
      document.getElementById('noCalls').style.display = 'block';
  }, 5000);
}

function selectCall(call_id) {
  activeCallId = call_id;
  // 목록 하이라이트
  document.querySelectorAll('.call-item').forEach(el => el.classList.remove('active'));
  const item = document.getElementById('call-item-' + call_id);
  if (item) item.classList.add('active');
  // 헤더 업데이트
  const c = calls[call_id];
  document.getElementById('chatHeader').style.display = 'flex';
  document.getElementById('headerCallId').textContent = call_id.slice(0, 16);
  document.getElementById('headerPhone').textContent = c?.phone ? ' · ' + c.phone : '';
  // 메시지 재렌더
  renderMessages(call_id);
}

function clearChat() {
  document.getElementById('chatHeader').style.display = 'none';
  document.getElementById('messages').innerHTML = `
    <div class="empty-state">
      <div class="empty-icon">📞</div>
      <span>통화가 연결되면 대화 내용이 여기에 표시됩니다</span>
    </div>`;
}

// ── 메시지 렌더링 ─────────────────────────────
function renderMessages(call_id) {
  const msgs = document.getElementById('messages');
  msgs.innerHTML = '';
  const c = calls[call_id];
  if (!c) return;
  c.msgs.forEach(m => appendBubble(msgs, m));
  msgs.scrollTop = msgs.scrollHeight;
}

function addMsg(call_id, role, text, phase = '', subName = '') {
  const c = calls[call_id];
  if (!c) return;
  const m = {role, text, phase, subName};
  c.msgs.push(m);
  if (activeCallId === call_id) {
    const msgs = document.getElementById('messages');
    // empty state 제거
    const empty = msgs.querySelector('.empty-state');
    if (empty) empty.remove();
    appendBubble(msgs, m);
    msgs.scrollTop = msgs.scrollHeight;
  }
}

function appendBubble(container, m) {
  const {role, text, phase, subName} = m;
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  let inner = '';
  if (role === 'sub') {
    inner = `<div class="sub-label">${subName}</div><div class="bubble">${text}</div>`;
  } else if (role === 'system') {
    inner = `<div class="bubble">${text}</div>`;
  } else {
    const tag = phase ? `<span class="phase-tag ${phase}">${phase === 'greeting' ? '인사' : phase}</span>` : '';
    inner = `<div class="bubble">${text}${tag}</div>`;
  }
  div.innerHTML = inner;
  container.appendChild(div);
}

function showTyping(call_id) {
  if (activeCallId !== call_id) return;
  if (document.getElementById('typing-indicator')) return;
  const msgs = document.getElementById('messages');
  const div = document.createElement('div');
  div.id = 'typing-indicator';
  div.className = 'msg agent';
  div.innerHTML = '<div class="bubble"><div class="typing-row"><span class="tdot"></span><span class="tdot"></span><span class="tdot"></span></div></div>';
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function removeTyping(call_id) {
  if (activeCallId !== call_id) return;
  const el = document.getElementById('typing-indicator');
  if (el) el.remove();
}

// 시작
connect();
</script>
</body>
</html>"""


@router.get("/monitor", response_class=HTMLResponse)
async def monitor_ui():
    return HTMLResponse(content=_HTML)
