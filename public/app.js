const chatEl = document.getElementById('chat');
const formEl = document.getElementById('composer');
const inputEl = document.getElementById('input');
const sendEl = document.getElementById('send');

function escapeHtml(text) {
  const div = document.createElement('div');
  div.innerText = text;
  return div.innerHTML;
}

function renderMessage(role, text, sources = []) {
  const wrapper = document.createElement('div');
  wrapper.className = `msg ${role}`;

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = text.split('\n').map(p => `<p>${escapeHtml(p)}</p>`).join('');
  wrapper.appendChild(bubble);

  if (role === 'assistant' && sources && sources.length > 0) {
    const src = document.createElement('div');
    src.className = 'sources';
    src.innerHTML = sources.map((s, i) => {
      const title = s.title || s.url || `Source ${i+1}`;
      return `<a href="${s.url}" target="_blank" rel="noopener noreferrer">[${i+1}] ${escapeHtml(title)}</a>`;
    }).join(' ');
    wrapper.appendChild(src);
  }

  chatEl.appendChild(wrapper);
  chatEl.scrollTop = chatEl.scrollHeight;
}

async function sendMessage(message) {
  renderMessage('user', message);
  inputEl.value = '';
  inputEl.disabled = true;
  sendEl.disabled = true;

  const thinkingId = `thinking-${Date.now()}`;
  renderMessage('assistant', 'Thinking…');

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    });
    if (!resp.ok) {
      throw new Error(`Server error: ${resp.status}`);
    }
    const data = await resp.json();

    // Remove the last assistant 'Thinking…' bubble
    chatEl.lastChild.remove();

    renderMessage('assistant', data.reply || '(no reply)', data.sources || []);
  } catch (err) {
    chatEl.lastChild.remove();
    renderMessage('assistant', `Something went wrong: ${err.message}`);
  } finally {
    inputEl.disabled = false;
    sendEl.disabled = false;
    inputEl.focus();
  }
}

formEl.addEventListener('submit', (e) => {
  e.preventDefault();
  const msg = inputEl.value.trim();
  if (msg.length === 0) return;
  sendMessage(msg);
});

inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    formEl.dispatchEvent(new Event('submit'));
  }
});

// Greet
setTimeout(() => {
  renderMessage('assistant', 'Hi! I can look things up on the web for you. What would you like to know?');
}, 50);