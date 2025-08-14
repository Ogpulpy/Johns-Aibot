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
	return wrapper;
}

function updateThinking(el, text) {
	if (!el) return;
	const bubble = el.querySelector('.bubble');
	if (bubble) bubble.innerHTML = `<p>${escapeHtml(text)}</p>`;
}

async function sendMessage(message) {
	renderMessage('user', message);
	inputEl.value = '';
	inputEl.disabled = true;
	sendEl.disabled = true;

	let thinkingEl = renderMessage('assistant', 'Searching…');

	// Try SSE first
	try {
		await new Promise((resolve, reject) => {
			const url = `/api/chat/stream?message=${encodeURIComponent(message)}`;
			const evt = new EventSource(url);
			let finalPayload = null;
			evt.onmessage = (e) => {
				try {
					const data = JSON.parse(e.data);
					if (data.phase === 'searching') {
						updateThinking(thinkingEl, 'Searching the web…');
					} else if (data.phase === 'reading') {
						updateThinking(thinkingEl, `Reading ${data.count} source(s)…`);
					} else if (data.phase === 'answer') {
						finalPayload = data.payload;
						evt.close();
						resolve();
					}
				} catch (err) {
					// ignore parse errors
				}
			};
			evt.onerror = () => {
				try { evt.close(); } catch {}
				reject(new Error('SSE failed'));
			};
		}).then(() => {
			// Replace thinking bubble with final answer
			if (thinkingEl && thinkingEl.parentNode) thinkingEl.remove();
			// finalPayload is in Python repr; try to eval as JSON-ish
			try {
				const json = (typeof finalPayload === 'string') ? JSON.parse(finalPayload) : finalPayload;
				renderMessage('assistant', json.reply || '(no reply)', json.sources || []);
			} catch {
				// naive parse fallback
				renderMessage('assistant', '(received answer)');
			}
			return;
		});
	} catch (err) {
		// Fallback to POST
		try {
			const resp = await fetch('/api/chat', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ message }),
			});
			if (!resp.ok) throw new Error(`Server error: ${resp.status}`);
			const data = await resp.json();
			if (thinkingEl && thinkingEl.parentNode) thinkingEl.remove();
			renderMessage('assistant', data.reply || '(no reply)', data.sources || []);
		} catch (e2) {
			if (thinkingEl && thinkingEl.parentNode) thinkingEl.remove();
			renderMessage('assistant', `Something went wrong: ${e2.message}`);
		}
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

setTimeout(() => {
	renderMessage('assistant', 'Hi! I can look things up on the web for you. What would you like to know?');
}, 50);