import re
from typing import Any, Dict, List, Tuple

from rank_bm25 import BM25Okapi

_STOPWORDS = {
    "the", "is", "at", "which", "on", "and", "a", "an", "to", "of", "in", "for", "by", "with",
    "as", "from", "or", "that", "this", "it", "be", "are", "was", "were", "has", "had", "have",
}


def _sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in parts if len(s.strip()) > 0]


def _keyword_tokens(text: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z0-9]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 2]


def _jaccard(a_tokens: List[str], b_tokens: List[str]) -> float:
    a, b = set(a_tokens), set(b_tokens)
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b) or 1
    return inter / union


def summarize_answer(question: str, docs: List[Dict[str, Any]], max_sentences: int = 7) -> Tuple[str, List[Dict[str, str]]]:
    # Gather candidate sentences with their source indices
    corpus_sentences: List[str] = []
    corpus_src: List[int] = []

    for idx, doc in enumerate(docs[:6]):
        text = (doc.get("text") or "").strip()
        if not text:
            continue
        # Up to 25 sentences per doc, filter too short
        for s in _sentences(text)[:25]:
            if len(s) < 50:
                continue
            corpus_sentences.append(s)
            corpus_src.append(idx)

    if not corpus_sentences:
        return ("I couldn't gather enough reliable information from the web results to answer that confidently.", [])

    # BM25 scoring by question tokens
    query_tokens = _keyword_tokens(question)
    tokenized = [_keyword_tokens(s) for s in corpus_sentences]
    bm25 = BM25Okapi(tokenized)
    base_scores = bm25.get_scores(query_tokens)

    # Greedy MMR-like selection to reduce redundancy
    selected: List[int] = []
    selected_tokens: List[List[str]] = []
    lambda_balance = 0.75

    candidates = list(range(len(corpus_sentences)))
    while len(selected) < max_sentences and candidates:
        best_idx = None
        best_score = -1e9
        for i in candidates:
            relevance = float(base_scores[i])
            if not selected_tokens:
                mmr = relevance
            else:
                # Diversity is 1 - max_jaccard to already selected
                max_sim = 0.0
                for toks in selected_tokens:
                    sim = _jaccard(tokenized[i], toks)
                    if sim > max_sim:
                        max_sim = sim
                diversity = 1.0 - max_sim
                mmr = lambda_balance * relevance + (1.0 - lambda_balance) * diversity
            if mmr > best_score:
                best_score = mmr
                best_idx = i
        if best_idx is None:
            break
        selected.append(best_idx)
        selected_tokens.append(tokenized[best_idx])
        candidates.remove(best_idx)

    # Compose final answer
    lines: List[str] = []
    for i in selected:
        src_idx = corpus_src[i]
        lines.append(f"- {corpus_sentences[i]} [{src_idx + 1}]")

    if not lines:
        return ("I couldn't gather enough reliable information from the web results to answer that confidently.", [])

    answer = "Here is a concise summary based on current sources:\n" + "\n".join(lines)

    cited_indices = sorted({corpus_src[i] for i in selected})
    used_docs: List[Dict[str, str]] = []
    for i in cited_indices:
        if 0 <= i < len(docs):
            used_docs.append({
                "title": docs[i].get("title") or "Untitled",
                "url": docs[i].get("url") or "",
            })

    return answer, used_docs