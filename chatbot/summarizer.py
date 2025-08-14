import re
from typing import Any, Dict, List, Tuple

_STOPWORDS = {
    "the", "is", "at", "which", "on", "and", "a", "an", "to", "of", "in", "for", "by", "with",
    "as", "from", "or", "that", "this", "it", "be", "are", "was", "were", "has", "had", "have",
}


def _sentences(text: str) -> List[str]:
    # Simple sentence splitter
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in parts if len(s.strip()) > 0]


def _keyword_score(sentence: str, keywords: List[str]) -> int:
    s = sentence.lower()
    return sum(1 for k in keywords if k in s)


def summarize_answer(question: str, docs: List[Dict[str, Any]], max_sentences: int = 8) -> Tuple[str, List[Dict[str, str]]]:
    # Extract keywords from the question
    tokens = re.findall(r"[A-Za-z0-9]+", question.lower())
    keywords = [t for t in tokens if t not in _STOPWORDS and len(t) > 2]

    candidate_sentences: List[Tuple[int, str, int]] = []  # (score, sentence, source_index)
    used_docs_meta: List[Dict[str, str]] = []

    for idx, doc in enumerate(docs[:5]):
        title = doc.get("title") or "Untitled"
        url = doc.get("url") or ""
        text = (doc.get("text") or "").strip()
        if not text:
            continue
        # Keep track of sources we might use
        used_docs_meta.append({"title": title, "url": url})
        for s in _sentences(text)[:20]:  # cap per document for speed
            score = _keyword_score(s, keywords)
            # Prefer slightly longer informative sentences
            length_bonus = min(max(len(s) // 80, 0), 3)
            candidate_sentences.append((score + length_bonus, s, idx))

    # Select top sentences
    candidate_sentences.sort(key=lambda x: x[0], reverse=True)
    chosen: List[Tuple[str, int]] = []
    seen = set()
    for score, sentence, source_idx in candidate_sentences:
        if len(chosen) >= max_sentences:
            break
        # Avoid near-duplicates
        key = sentence.lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        chosen.append((sentence, source_idx))

    if not chosen:
        return ("I couldn't gather enough reliable information from the web results to answer that confidently.", [] )

    # Compose concise answer with numbered citations like [1], [2]
    answer_lines: List[str] = []
    for s, src_idx in chosen:
        citation_num = src_idx + 1
        answer_lines.append(f"- {s} [{citation_num}]")

    answer = "Here is a quick summary based on current web sources:\n" + "\n".join(answer_lines)

    # Restrict used docs to those actually cited
    cited_indices = sorted({src_idx for _, src_idx in chosen})
    used_docs = []
    for i in cited_indices:
        if 0 <= i < len(docs):
            used_docs.append({
                "title": docs[i].get("title") or "Untitled",
                "url": docs[i].get("url") or "",
            })

    return answer, used_docs