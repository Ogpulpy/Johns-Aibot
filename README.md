# Johns-Aibot
A simple, interactive chatbot with quick web lookup using DuckDuckGo and content extraction. Optional OpenAI support if you provide OPENAI_API_KEY.

Features
Web search via DuckDuckGo (no API key required)
Fast content fetching and extraction
Extractive summarization fallback (no LLM required)
Optional LLM answers with inline citations if OPENAI_API_KEY is set
Minimal web UI
Setup
cd /workspace/chatbot
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
(Optional) set your OpenAI key to enable LLM answers:

export OPENAI_API_KEY=your_key_here
# Optional: choose a model (defaults to gpt-4o-mini)
export OPENAI_MODEL=gpt-4o-mini
Run
uvicorn app:app --host 0.0.0.0 --port 8000
Then open http://localhost:8000 in your browser.

How it works
The backend searches the web and fetches a handful of result pages, extracting clean text.
If OpenAI is configured, it crafts a short, cited answer. Otherwise, a lightweight extractive summary is returned with citations.
Notes
Be mindful of source credibility; verify critical information.
Network access and website rate limits may affect speed and completeness.
