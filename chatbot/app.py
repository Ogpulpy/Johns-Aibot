import os
import asyncio
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from search import search_and_fetch
from summarizer import summarize_answer

# Optional OpenAI support (only used if OPENAI_API_KEY is provided)
try:
	from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
	OpenAI = None  # type: ignore


class ChatRequest(BaseModel):
	message: str
	history: Optional[List[Dict[str, str]]] = None


def has_openai_key() -> bool:
	return bool(os.getenv("OPENAI_API_KEY")) and OpenAI is not None


async def generate_with_openai(question: str, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
	if not has_openai_key():
		raise RuntimeError("OpenAI not configured")

	client = OpenAI()

	# Prepare compact context from top documents
	max_chars = 8000
	context_chunks: List[str] = []
	used_docs: List[Dict[str, str]] = []
	for index, doc in enumerate(docs[:5], start=1):
		if not doc.get("text"):
			continue
		title = doc.get("title") or "Untitled"
		url = doc.get("url")
		snippet = (doc["text"] or "").strip()
		if len(snippet) > 1500:
			snippet = snippet[:1500] + "…"
		chunk = f"[{index}] {title}\nURL: {url}\nContent:\n{snippet}\n"
		context_chunks.append(chunk)
		used_docs.append({"title": title, "url": url})
		if sum(len(c) for c in context_chunks) > max_chars:
			break

	system_prompt = (
		"You are a concise research assistant. Answer the user's question using the provided web context. "
		"Cite sources inline using [n] notation matching the provided source list. If unsure, say you don't know."
	)

	context_block = "\n\n".join(context_chunks) if context_chunks else "No external context available."
	user_block = (
		f"Question: {question}\n\n"
		f"Sources:\n{context_block}\n\n"
		"Write a helpful, truthful answer in 4-8 sentences. Include citations like [1], [2] where relevant."
	)

	completion = await asyncio.to_thread(
		client.chat.completions.create,
		model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
		messages=[
			{"role": "system", "content": system_prompt},
			{"role": "user", "content": user_block},
		],
		temperature=0.2,
		max_tokens=500,
	)

	text = completion.choices[0].message.content or ""

	return {"reply": text.strip(), "sources": used_docs}


async def generate_answer(question: str, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
	if has_openai_key():
		try:
			return await generate_with_openai(question, docs)
		except Exception:
			pass  # fall back to extractive summary
	# Non-LLM, fast extractive summary
	summary, used_docs = summarize_answer(question, docs)
	return {"reply": summary, "sources": used_docs}


app = FastAPI(title="Web-Enabled Chatbot", version="0.2.0")

# Allow local dev origins
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> Dict[str, str]:
	return {"status": "ok"}


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest) -> Dict[str, Any]:
	message = (req.message or "").strip()
	if not message:
		raise HTTPException(status_code=400, detail="Empty message")

	# Search the web and fetch content quickly
	docs = await search_and_fetch(message, max_results=6, max_concurrent=6, budget_seconds=8.0)

	result = await generate_answer(message, docs)
	return result


@app.get("/api/chat/stream")
async def chat_stream(message: str):
	if not (message or "").strip():
		raise HTTPException(status_code=400, detail="Empty message")

	async def event_generator():
		# phase: searching
		yield f"data: {{\"phase\":\"searching\",\"message\":\"Searching the web...\"}}\n\n"
		docs = await search_and_fetch(message, max_results=6, max_concurrent=6, budget_seconds=8.0)
		yield f"data: {{\"phase\":\"reading\",\"count\":{len(docs)} }}\n\n"
		result = await generate_answer(message, docs)
		import json as _json
		payload = {"phase": "answer", "payload": result}
		yield f"data: {_json.dumps(payload)}\n\n"

	return StreamingResponse(event_generator(), media_type="text/event-stream")


# Serve static frontend
app.mount("/", StaticFiles(directory="public", html=True), name="public")