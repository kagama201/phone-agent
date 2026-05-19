"""
app/routes/prompt_ui.py
────────────────────────
에이전트 설계 도구 UI. GET /prompt → HTML 반환.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["prompt-ui"])

_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>에이전트 설계 도구</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f7;color:#1c1c1e;height:100dvh;display:flex;flex-direction:column}
header{padding:12px 20px;background:#fff;border-bottom:1px solid #e5e5ea;display:flex;align-items:center;gap:12px;flex-shrink:0}
header h1{font-size:16px;font-weight:600}
.badge{font-size:11px;padding:2px 8px;border-radius:10px;background:#e8f5e9;color:#2e7d32;border:1px solid #c8e6c9}
.btn{padding:7px 14px;font-size:13px;border-radius:8px;border:1px solid #e5e5ea;cursor:pointer;background:#f5f5f7;color:#1c1c1e;white-space:nowrap}
.btn:hover{background:#e5e5ea}
.btn.primary{background:#007aff;color:#fff;border-color:#007aff}
.btn.primary:hover{background:#0066cc}
.btn.danger{background:#fff;color:#d32f2f;border-color:#ffcdd2}
.btn.danger:hover{background:#ffebee}
.btn.small{padding:4px 10px;font-size:12px}
.spacer{flex:1}

.layout{display:flex;flex:1;overflow:hidden}

/* ── 왼쪽: 설계 패널 ── */
.design-panel{width:420px;min-width:320px;background:#fff;border-right:1px solid #e5e5ea;display:flex;flex-direction:column;overflow:hidden}
.tabs{display:flex;border-bottom:1px solid #e5e5ea;flex-shrink:0}
.tab{padding:10px 16px;font-size:13px;cursor:pointer;border-bottom:2px solid transparent;color:#8e8e93;white-space:nowrap}
.tab.active{color:#007aff;border-bottom-color:#007aff;font-weight:500}
.tab-content{display:none;flex:1;overflow-y:auto;padding:16px}
.tab-content.active{display:flex;flex-direction:column;gap:12px}

label{font-size:12px;font-weight:500;color:#3a3a3c;display:block;margin-bottom:4px}
textarea{width:100%;padding:10px;border:1px solid #e5e5ea;border-radius:8px;font-size:13px;resize:vertical;font-family:inherit;line-height:1.5;min-height:80px}
textarea:focus{outline:none;border-color:#007aff}
input[type=text]{width:100%;padding:8px 10px;border:1px solid #e5e5ea;border-radius:8px;font-size:13px;font-family:inherit}
input[type=text]:focus{outline:none;border-color:#007aff}
input[type=number]{width:70px;padding:6px 8px;border:1px solid #e5e5ea;border-radius:8px;font-size:13px}

.section-title{font-size:13px;font-weight:600;color:#1c1c1e;margin-bottom:8px}
.field{margin-bottom:12px}

/* 서브 에이전트 카드 */
.agent-list{display:flex;flex-direction:column;gap:8px}
.agent-card{border:1px solid #e5e5ea;border-radius:10px;overflow:hidden}
.agent-card-header{display:flex;align-items:center;gap:8px;padding:10px 12px;cursor:pointer;background:#fafafa}
.agent-card-header:hover{background:#f0f0f5}
.agent-card-body{display:none;padding:12px;border-top:1px solid #e5e5ea;display:flex;flex-direction:column;gap:10px}
.agent-card-body.open{display:flex}
.agent-tag{font-size:11px;padding:2px 8px;border-radius:10px;border:1px solid #e5e5ea;background:#f5f5f7;color:#3a3a3c}
.toggle{width:36px;height:20px;border-radius:10px;background:#ccc;position:relative;cursor:pointer;flex-shrink:0;transition:background .2s}
.toggle.on{background:#34c759}
.toggle::after{content:'';position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:#fff;transition:transform .2s}
.toggle.on::after{transform:translateX(16px)}
.next-agents{display:flex;flex-wrap:wrap;gap:6px;margin-top:4px}
.next-tag{font-size:11px;padding:3px 8px;border-radius:8px;border:1px solid #e5e5ea;background:#f5f5f7;cursor:pointer;user-select:none}
.next-tag.selected{background:#e3f2fd;border-color:#90caf9;color:#1565c0}

/* ── 오른쪽: 테스트 채팅 ── */
.chat-panel{flex:1;display:flex;flex-direction:column;overflow:hidden}
.chat-header{padding:12px 16px;border-bottom:1px solid #e5e5ea;display:flex;align-items:center;gap:8px;flex-shrink:0;background:#fff}
.chat-header span{font-size:14px;font-weight:500}
.status-dot{width:8px;height:8px;border-radius:50%;background:#ccc;flex-shrink:0}
.status-dot.on{background:#34c759}
.messages{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px}
.msg{display:flex;flex-direction:column;gap:3px}
.msg.user{align-items:flex-end}
.bubble{max-width:75%;padding:9px 13px;border-radius:16px;font-size:13px;line-height:1.5}
.msg.user .bubble{background:#007aff;color:#fff;border-bottom-right-radius:4px}
.msg.agent .bubble{background:#f2f2f7;color:#1c1c1e;border-bottom-left-radius:4px}
.msg.system .bubble{background:none;color:#8e8e93;font-size:12px;text-align:center;max-width:100%}
.msg.smalltalk .bubble{background:#fff9e6;color:#795548;border:1px solid #ffe082;font-style:italic;border-radius:12px}
.msg.sub .bubble{background:#e8f5e9;color:#1b5e20;border:1px solid #c8e6c9;font-size:12px}
.sub-label{font-size:11px;color:#388e3c;font-weight:500;margin-bottom:2px;padding-left:4px}
.typing-bubble{background:#f2f2f7;padding:9px 13px;border-radius:16px;border-bottom-left-radius:4px;display:inline-flex;gap:4px;align-items:center}
.dot{width:6px;height:6px;border-radius:50%;background:#8e8e93;animation:blink 1.2s infinite}
.dot:nth-child(2){animation-delay:.2s}
.dot:nth-child(3){animation-delay:.4s}
@keyframes blink{0%,80%,100%{opacity:.2}40%{opacity:1}}
.input-row{padding:12px 16px;border-top:1px solid #e5e5ea;display:flex;gap:8px;background:#fff;flex-shrink:0}
.input-row input{flex:1;padding:10px 14px;border:1px solid #e5e5ea;border-radius:20px;font-size:13px;outline:none;background:#f2f2f7}
.input-row input:focus{border-color:#007aff;background:#fff}
.scenario-row{padding:0 16px 10px;display:flex;gap:6px;flex-wrap:wrap;background:#fff;flex-shrink:0}
.sc-btn{font-size:11px;padding:4px 10px;border-radius:12px;border:1px solid #e5e5ea;cursor:pointer;background:#f5f5f7;color:#3a3a3c}
.sc-btn:hover{background:#e5e5ea}
</style>
</head>
<body>
<header>
  <h1>에이전트 설계 도구</h1>
  <span class="badge" id="saveBadge">미저장</span>
  <div class="spacer"></div>
  <button class="btn" onclick="resetDesign()">초기화</button>
  <button class="btn primary" onclick="saveDesign()">저장 적용</button>
</header>

<div class="layout">
  <!-- ── 설계 패널 ── -->
  <div class="design-panel">
    <div class="tabs">
      <div class="tab active" onclick="switchTab('main')">메인 에이전트</div>
      <div class="tab" onclick="switchTab('sub')">서브 에이전트</div>
    </div>

    <!-- 메인 에이전트 탭 -->
    <div class="tab-content active" id="tab-main">
      <div class="field">
        <label>역할 및 디스패치 프롬프트</label>
        <textarea id="mainPrompt" rows="10" oninput="markUnsaved()"></textarea>
      </div>
      <div class="field">
        <label>스몰톡 프롬프트 (대기 중 멘트)</label>
        <textarea id="smalltalkPrompt" rows="4" oninput="markUnsaved()"></textarea>
      </div>
      <div class="field" style="display:flex;align-items:center;gap:10px">
        <label style="margin:0">최대 병렬 서브 에이전트</label>
        <input type="number" id="maxSub" min="1" max="5" value="3" oninput="markUnsaved()">
      </div>
    </div>

    <!-- 서브 에이전트 탭 -->
    <div class="tab-content" id="tab-sub">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
        <span class="section-title">서브 에이전트 목록</span>
        <button class="btn small primary" onclick="addSubAgent()">+ 추가</button>
      </div>
      <div class="agent-list" id="agentList"></div>
    </div>
  </div>

  <!-- ── 테스트 채팅 ── -->
  <div class="chat-panel">
    <div class="chat-header">
      <div class="status-dot" id="statusDot"></div>
      <span>테스트 대화</span>
      <div class="spacer"></div>
      <button class="btn small" onclick="clearChat()">대화 초기화</button>
    </div>

    <div class="messages" id="messages">
      <div class="msg system"><div class="bubble">저장 후 대화를 시작하세요</div></div>
    </div>

    <div class="scenario-row">
      <span style="font-size:11px;color:#8e8e93;align-self:center">시나리오:</span>
      <button class="sc-btn" onclick="send('강남역에서 홍대입구까지 가는 방법 알려줘')">🚇 교통 안내</button>
      <button class="sc-btn" onclick="send('제주도 여행 맛집 추천해줘')">✈️ 여행 추천</button>
      <button class="sc-btn" onclick="send('근처 식당 예약하고 싶어')">📅 예약 안내</button>
      <button class="sc-btn" onclick="send('보이스피싱 의심 전화가 왔어')">🔍 생활 문의</button>
      <button class="sc-btn" onclick="send('오늘 날씨 어때?')">💬 일반 대화</button>
    </div>

    <div class="input-row">
      <input type="text" id="chatInput" placeholder="메시지를 입력하세요..." onkeydown="if(event.key==='Enter')send()">
      <button class="btn primary" onclick="send()">전송</button>
    </div>
  </div>
</div>

<script>
let design = null;
let chatHistory = [];
let busy = false;

// ── 초기 로드 ─────────────────────────────────
async function loadDesign() {
  const res = await fetch('/prompt/design');
  design = await res.json();
  renderDesign();
  markSaved();
}

function renderDesign() {
  document.getElementById('mainPrompt').value = design.main.prompt;
  document.getElementById('smalltalkPrompt').value = design.main.smalltalk_prompt;
  document.getElementById('maxSub').value = design.main.max_sub_agents;
  renderAgentList();
}

function renderAgentList() {
  const list = document.getElementById('agentList');
  list.innerHTML = '';
  design.sub_agents.forEach((agent, idx) => {
    const card = document.createElement('div');
    card.className = 'agent-card';
    card.id = `card-${idx}`;

    const allIds = design.sub_agents.map(a => a.id).filter(id => id !== agent.id);
    const nextTags = allIds.map(id => {
      const sel = (agent.next_agents || []).includes(id);
      return `<span class="next-tag ${sel?'selected':''}" onclick="toggleNext(${idx},'${id}',this)">${id}</span>`;
    }).join('');

    card.innerHTML = `
      <div class="agent-card-header" onclick="toggleCard(${idx})">
        <div class="toggle ${agent.enabled?'on':''}" onclick="event.stopPropagation();toggleEnabled(${idx},this)"></div>
        <span style="font-size:13px;font-weight:500;flex:1">${agent.name}</span>
        <span class="agent-tag">${agent.id}</span>
        <span style="color:#8e8e93;font-size:16px" id="arrow-${idx}">›</span>
      </div>
      <div class="agent-card-body" id="body-${idx}">
        <div class="field">
          <label>에이전트 ID</label>
          <input type="text" value="${agent.id}" oninput="updateField(${idx},'id',this.value)">
        </div>
        <div class="field">
          <label>이름</label>
          <input type="text" value="${agent.name}" oninput="updateField(${idx},'name',this.value)">
        </div>
        <div class="field">
          <label>설명 (메인 에이전트가 호출 여부 판단에 사용)</label>
          <textarea rows="2" oninput="updateField(${idx},'description',this.value)">${agent.description}</textarea>
        </div>
        <div class="field">
          <label>시스템 프롬프트</label>
          <textarea rows="5" oninput="updateField(${idx},'prompt',this.value)">${agent.prompt}</textarea>
        </div>
        <div class="field">
          <label>후속 에이전트 (이 에이전트 완료 후 자동 호출)</label>
          <div class="next-agents">${nextTags || '<span style="font-size:12px;color:#8e8e93">없음</span>'}</div>
        </div>
        <div style="display:flex;justify-content:flex-end">
          <button class="btn small danger" onclick="removeAgent(${idx})">삭제</button>
        </div>
      </div>`;
    list.appendChild(card);
  });
}

function toggleCard(idx) {
  const body = document.getElementById(`body-${idx}`);
  const arrow = document.getElementById(`arrow-${idx}`);
  const open = body.classList.toggle('open');
  arrow.style.transform = open ? 'rotate(90deg)' : '';
}

function toggleEnabled(idx, el) {
  design.sub_agents[idx].enabled = !design.sub_agents[idx].enabled;
  el.classList.toggle('on', design.sub_agents[idx].enabled);
  markUnsaved();
}

function updateField(idx, key, val) {
  design.sub_agents[idx][key] = val;
  markUnsaved();
}

function toggleNext(idx, targetId, el) {
  const arr = design.sub_agents[idx].next_agents || [];
  const i = arr.indexOf(targetId);
  if (i >= 0) arr.splice(i, 1);
  else arr.push(targetId);
  design.sub_agents[idx].next_agents = arr;
  el.classList.toggle('selected', i < 0);
  markUnsaved();
}

function addSubAgent() {
  const id = `에이전트${design.sub_agents.length + 1}`;
  design.sub_agents.push({
    id, name: '새 에이전트', description: '담당 도메인 설명',
    prompt: '당신은 전문 AI입니다.\n2~3문장으로 답변하세요.',
    enabled: true, next_agents: [],
  });
  renderAgentList();
  markUnsaved();
  // 새 카드 자동 열기
  setTimeout(() => toggleCard(design.sub_agents.length - 1), 50);
}

function removeAgent(idx) {
  if (!confirm(`"${design.sub_agents[idx].name}" 서브 에이전트를 삭제할까요?`)) return;
  design.sub_agents.splice(idx, 1);
  renderAgentList();
  markUnsaved();
}

// ── 저장 ──────────────────────────────────────
function collectDesign() {
  design.main.prompt = document.getElementById('mainPrompt').value;
  design.main.smalltalk_prompt = document.getElementById('smalltalkPrompt').value;
  design.main.max_sub_agents = parseInt(document.getElementById('maxSub').value) || 3;
  return design;
}

async function saveDesign() {
  const d = collectDesign();
  const res = await fetch('/prompt/design', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(d),
  });
  if (res.ok) markSaved();
}

async function resetDesign() {
  if (!confirm('기본값으로 초기화할까요?')) return;
  const res = await fetch('/prompt/reset', {method:'POST'});
  const data = await res.json();
  design = data.design;
  renderDesign();
  markSaved();
}

function markUnsaved() {
  const b = document.getElementById('saveBadge');
  b.textContent = '미저장';
  b.style.background = '#fff3e0';
  b.style.color = '#e65100';
  b.style.borderColor = '#ffcc80';
}
function markSaved() {
  const b = document.getElementById('saveBadge');
  b.textContent = '저장됨';
  b.style.background = '#e8f5e9';
  b.style.color = '#2e7d32';
  b.style.borderColor = '#c8e6c9';
}

// ── 탭 전환 ───────────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', ['main','sub'][i]===name));
  document.getElementById('tab-main').classList.toggle('active', name==='main');
  document.getElementById('tab-sub').classList.toggle('active', name==='sub');
}

// ── 채팅 ──────────────────────────────────────
function addMsg(role, text, meta={}) {
  const msgs = document.getElementById('messages');
  const sys = msgs.querySelector('.msg.system');
  if (sys) sys.remove();
  const div = document.createElement('div');
  div.className = `msg ${role}`;
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
  const div = document.createElement('div');
  div.id = 'typing';
  div.className = 'msg agent';
  div.innerHTML = '<div class="typing-bubble"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>';
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}
function hideTyping() {
  const el = document.getElementById('typing');
  if (el) el.remove();
}

async function send(preset) {
  if (busy) return;
  const input = document.getElementById('chatInput');
  const text = preset || input.value.trim();
  if (!text) return;
  input.value = '';
  addMsg('user', text);
  chatHistory.push({role:'user', content:text});

  busy = true;
  document.getElementById('statusDot').className = 'status-dot on';
  showTyping();

  try {
    const res = await fetch('/prompt/run', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({message: text, history: chatHistory.slice(-10)}),
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let finalText = '';

    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      const lines = decoder.decode(value).split('\n');
      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        const raw = line.slice(5).trim();
        if (raw === '[DONE]') break;
        try {
          const chunk = JSON.parse(raw);
          if (chunk.type === 'smalltalk') {
            hideTyping();
            addMsg('smalltalk', chunk.text);
            showTyping();
          } else if (chunk.type === 'sub_result') {
            addMsg('sub', chunk.text, chunk.meta);
          } else if (chunk.type === 'final') {
            hideTyping();
            finalText = chunk.text;
            addMsg('agent', chunk.text);
          } else if (chunk.type === 'error') {
            hideTyping();
            addMsg('system', '오류: ' + chunk.text);
          }
        } catch(e) {}
      }
    }

    if (finalText) chatHistory.push({role:'assistant', content:finalText});
  } catch(e) {
    hideTyping();
    addMsg('system', '연결 오류: ' + e.message);
  } finally {
    busy = false;
    document.getElementById('statusDot').className = 'status-dot';
  }
}

function clearChat() {
  chatHistory = [];
  document.getElementById('messages').innerHTML = '<div class="msg system"><div class="bubble">대화가 초기화되었습니다</div></div>';
}

loadDesign();
</script>
</body>
</html>"""


@router.get("/prompt", response_class=HTMLResponse)
async def prompt_ui():
    return HTMLResponse(content=_HTML)
