# Web-Enabled Chatbot

A simple, fast chatbot with quick web lookup using multiple free sources, caching, and extractive summarization. Optional OpenAI support if you provide `OPENAI_API_KEY`.

## Features
- Web search via DuckDuckGo with HTML/Lite fallbacks (no API key required)
- Extra sources: Wikipedia REST, Stack Overflow, MDN, GitHub repos (unauthenticated)
- Disk cache for search results and fetched pages (speeds up repeats)
- Extractive summarization with BM25 re-ranking + LexRank (no LLM required)
- Optional LLM answers with inline citations if `OPENAI_API_KEY` is set
- Minimal web UI with SSE progress streaming

## Setup
```bash
cd /workspace/chatbot
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

(Optional) enable LLM answers:
```bash
export OPENAI_API_KEY=your_key_here
export OPENAI_MODEL=gpt-4o-mini
```

## Run
```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```
Open http://localhost:8000

## API
- POST `/api/chat` body: `{ "message": "..." }` -> `{ reply, sources }`
- GET `/api/chat/stream?message=...` SSE events: phases `searching`, `reading`, then `answer`

## Notes
- Caching directory: `.cache` (override with `CHATBOT_CACHE_DIR`)
- We use short timeouts and a global request budget for quick responses
- Sources are deduplicated and prioritized for quality/freshness