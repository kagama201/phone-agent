"""
app/routes/test_ui.py
──────────────────────
/test — 에이전트 동작 테스트 UI.
/prompt에서 저장한 설계를 실시간으로 반영.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["test-ui"])

_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 에이전트 테스트</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f7;height:100dvh;display:flex;flex-direction:column;align-items:center;justify-content:center}
.container{width:100%;max-width:560px;height:90dvh;background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.1);display:flex;flex-direction:column;overflow:hidden}
.header{padding:14px 18px;border-bottom:1px solid #e5e5ea;display:flex;align-items:center;gap:10px}
.dot{width:9px;height:9px;border-radius:50%;background:#ccc;transition:background .3s;flex-shrink:0}
.dot.on{background:#34c759}
.header h2{font-size:15px;font-weight:600;color:#1c1c1e;flex:1}
.design-badge{font-size:11px;padding:2px 8px;border-radius:8px;background:#e3f2fd;color:#1565c0;border:1px solid #90caf9;cursor:pointer;text-decoration:none}
.sid{font-size:11px;color:#8e8e93;font-family:monospace}
.messages{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:8px}
.msg{display:flex;flex-direction:column;gap:2px}
.msg.user{align-items:flex-end}
.bubble{max-width:82%;padding:8px 13px;border-radius:16px;font-size:13px;line-height:1.5}
.msg.agent .bubble{background:#f2f2f7;color:#1c1c1e;border-bottom-left-radius:4px}
.msg.user .bubble{background:#007aff;color:#fff;border-bottom-right-radius:4px}
.msg.system .bubble{background:none;color:#8e8e93;font-size:12px;text-align:center;max-width:100%}
.msg.smalltalk .bubble{background:#fffde7;color:#795548;border:1px solid #fff176;font-style:italic;border-radius:12px;font-size:12px}
.msg.sub{align-items:flex-start}
.sub-label{font-size:10px;color:#388e3c;font-weight:600;padding-left:4px;margin-bottom:1px}
.msg.sub .bubble{background:#f1f8e9;color:#1b5e20;border:1px solid #dcedc8;font-size:12px;border-bottom-left-radius:4px}
.typing-bub{background:#f2f2f7;padding:9px 13px;border-radius:16px;border-bottom-left-radius:4px;display:inline-flex;gap:4px;align-items:center}
.d{width:6px;height:6px;border-radius:50%;background:#8e8e93;animation:blink 1.2s infinite}
.d:nth-child(2){animation-delay:.2s}.d:nth-child(3){animation-delay:.4s}
@keyframes blink{0%,80%,100%{opacity:.2}40%{opacity:1}}
.scenario-row{padding:0 14px 8px;display:flex;gap:5px;flex-wrap:wrap}
.sc{font-size:11px;padding:4px 9px;border:1px solid #e5e5ea;border-radius:10px;cursor:pointer;background:#f5f5f7;color:#3a3a3c}
.sc:hover{background:#e5e5ea}
.input-row{padding:10px 14px;border-top:1px solid #e5e5ea;display:flex;gap:7px}
.input-row input{flex:1;font-size:13px;padding:9px 13px;border:1px solid #e5e5ea;border-radius:18px;background:#f2f2f7;outline:none}
.input-row input:focus{border-color:#007aff;background:#fff}
.input-row button{padding:9px 15px;font-size:13px;background:#007aff;color:#fff;border:none;border-radius:18px;cursor:pointer}
.input-row button:disabled{background:#c7c7cc}
.btn-row{padding:0 14px 10px;display:flex;gap:7px}
.btn-row button{flex:1;padding:7px;border:1px solid #e5e5ea;border-radius:8px;font-size:12px;cursor:pointer;background:#f2f2f7;color:#3a3a3c}
.btn-row button:hover{background:#e5e5ea}
.design-info{padding:6px 14px;background:#e3f2fd;font-size:11px;color:#1565c0;display:none;align-items:center;gap:6px;flex-wrap:wrap}
.design-info.show{display:flex}
.agent-pill{padding:2px 7px;background:#fff;border:1px solid #90caf9;border-radius:8px;color:#1565c0;font-size:10px}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="dot" id="dot"></div>
    <h2>에이전트 테스트</h2>
    <a class="design-badge" href="/prompt" target="_blank">설계 편집 →</a>
    <span class="sid" id="sidEl"></span>
  </div>

  <div class="design-info" id="designInfo"></div>

  <div class="messages" id="messages">
    <div class="msg system"><div class="bubble">세션 시작을 눌러 대화를 시작하세요</div></div>
  </div>

  <div class="scenario-row" id="scRow" style="display:none">
    <span style="font-size:11px;color:#8e8e93;align-self:center">시나리오:</span>
    <button class="sc" onclick="send('강남역에서 홍대까지 가는 방법')">🚇 교통</button>
    <button class="sc" onclick="send('제주도 여행 맛집 추천해줘')">✈️ 여행</button>
    <button class="sc" onclick="send('근처 식당 예약하고 싶어')">📅 예약</button>
    <button class="sc" onclick="send('보이스피싱 의심 전화가 왔어')">🔍 문의</button>
    <button class="sc" onclick="send('오늘 날씨 어때?')">💬 일반</button>
  </div>

  <div class="input-row">
    <input type="text" id="inp" placeholder="세션을 먼저 시작하세요..." disabled
      onkeydown="if(event.key==='Enter')send()">
    <button id="sendBtn" onclick="send()" disabled>전송</button>
  </div>

  <div style="padding:0 14px 8px;display:flex;gap:8px;align-items:center">
    <input type="tel" id="phoneInput" placeholder="+821012345678 (SMS 테스트용)"
      style="flex:1;font-size:12px;padding:7px 10px;border:1px solid #e5e5ea;border-radius:8px;background:#f2f2f7;outline:none"
      onfocus="this.style.borderColor='#007aff';this.style.background='#fff'"
      onblur="this.style.borderColor='#e5e5ea';this.style.background='#f2f2f7'">
  </div>
  <div class="btn-row">
    <button onclick="startSession()">🟢 세션 시작</button>
    <button onclick="clearSession()">🔄 초기화</button>
  </div>
</div>

<script>
let sid = null, busy = false;

async function loadDesignInfo() {
  try {
    const r = await fetch('/chat/sessions');
    const d = await r.json();
    const info = document.getElementById('designInfo');
    if (d.active_design && d.active_design.sub_agents.length) {
      info.className = 'design-info show';
      info.innerHTML = '<span style="font-weight:500">활성 에이전트:</span> '
        + d.active_design.sub_agents.map(id =>
            `<span class="agent-pill">${id}</span>`).join('');
    }
  } catch(e) {}
}

async function startSession() {
  if (sid) await fetch(`/chat/session/${sid}`, {method:'DELETE'});
  document.getElementById('messages').innerHTML = '';
  addMsg('system', '연결 중...');

  const phone = document.getElementById('phoneInput')?.value.trim() || "";
  const r = await fetch('/chat/session', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({phone_number: phone})
  });
  const d = await r.json();
  sid = d.session_id;

  document.getElementById('messages').innerHTML = '';
  addMsg('agent', d.greeting);
  document.getElementById('dot').className = 'dot on';
  document.getElementById('sidEl').textContent = sid;
  document.getElementById('inp').disabled = false;
  document.getElementById('inp').placeholder = '메시지를 입력하세요...';
  document.getElementById('sendBtn').disabled = false;
  document.getElementById('scRow').style.display = 'flex';
  document.getElementById('inp').focus();
  loadDesignInfo();
}

function addMsg(role, text, meta={}) {
  const msgs = document.getElementById('messages');
  const sys = msgs.querySelector('.msg.system');
  if (sys && sys.textContent.includes('세션을')) sys.remove();
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  if (role === 'sub') {
    div.innerHTML = `<div class="sub-label">${meta.agent_name || ''}</div><div class="bubble">${text}</div>`;
  } else {
    div.innerHTML = `<div class="bubble">${text}</div>`;
  }
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function showTyping() {
  const msgs = document.getElementById('messages');
  const d = document.createElement('div');
  d.id = 'typing'; d.className = 'msg agent';
  d.innerHTML = '<div class="typing-bub"><span class="d"></span><span class="d"></span><span class="d"></span></div>';
  msgs.appendChild(d);
  msgs.scrollTop = msgs.scrollHeight;
}
function hideTyping() { const el = document.getElementById('typing'); if(el) el.remove(); }

async function send(preset) {
  if (!sid || busy) return;
  const inp = document.getElementById('inp');
  const text = preset || inp.value.trim();
  if (!text) return;
  inp.value = '';
  addMsg('user', text);
  busy = true;
  document.getElementById('sendBtn').disabled = true;
  showTyping();

  try {
    const r = await fetch(`/chat/session/${sid}/message`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({text}),
    });
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      for (const line of dec.decode(value).split('\n')) {
        if (!line.startsWith('data:')) continue;
        const raw = line.slice(5).trim();
        if (raw === '[DONE]') break;
        try {
          const chunk = JSON.parse(raw);
          if (chunk.type === 'smalltalk') {
            hideTyping(); addMsg('smalltalk', chunk.text); showTyping();
          } else if (chunk.type === 'sub_result') {
            addMsg('sub', chunk.text, chunk.meta);
          } else if (chunk.type === 'action') {
            hideTyping();
            const locMsg = chunk.text || `📍 ${chunk.destination} 위치 링크 SMS 발송 중...`;
            addMsg('system', locMsg);
            showTyping();
          } else if (chunk.type === 'final') {
            hideTyping(); addMsg('agent', chunk.text);
          } else if (chunk.type === 'error') {
            hideTyping(); addMsg('system', '오류: ' + chunk.text);
          }
        } catch(e) {}
      }
    }
  } catch(e) {
    hideTyping(); addMsg('system', '연결 오류: ' + e.message);
  } finally {
    busy = false;
    document.getElementById('sendBtn').disabled = false;
    document.getElementById('inp').focus();
  }
}

function clearSession() {
  if (sid) fetch(`/chat/session/${sid}`, {method:'DELETE'});
  sid = null;
  document.getElementById('messages').innerHTML = '<div class="msg system"><div class="bubble">세션이 초기화되었습니다</div></div>';
  document.getElementById('dot').className = 'dot';
  document.getElementById('sidEl').textContent = '';
  document.getElementById('inp').disabled = true;
  document.getElementById('inp').placeholder = '세션을 먼저 시작하세요...';
  document.getElementById('sendBtn').disabled = true;
  document.getElementById('scRow').style.display = 'none';
  document.getElementById('designInfo').className = 'design-info';
}

loadDesignInfo();
</script>
</body>
</html>"""


@router.get("/test", response_class=HTMLResponse)
async def test_ui():
    return HTMLResponse(content=_HTML)
