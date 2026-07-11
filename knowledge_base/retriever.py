"""
In-memory vector search using sentence-transformers (all-MiniLM-L6-v2).
Loads hotel_knowledge.txt once at import time, embeds all chunks, stores in RAM.
Query time: ~20ms total (embed + cosine sim). No network calls, no API key needed.
"""
import os
import logging
import numpy as np
from sentence_transformers import SentenceTransformer

log = logging.getLogger("agent")

_MODEL_NAME = "all-MiniLM-L6-v2"
_CHUNK_SIZE = 100   # words per chunk
_OVERLAP = 20
_MIN_SCORE = 0.25   # discard matches below this cosine similarity

_model = SentenceTransformer(_MODEL_NAME)


def _chunk_text(text: str) -> list:
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i:i + _CHUNK_SIZE]))
        i += _CHUNK_SIZE - _OVERLAP
    return [c for c in chunks if len(c.strip()) > 30]


def _load_kb():
    kb_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "data", "hotel_knowledge.txt")
    )
    with open(kb_path, "r", encoding="utf-8") as f:
        text = f.read()
    chunks = _chunk_text(text)
    embeddings = _model.encode(chunks, normalize_embeddings=True, show_progress_bar=False)
    log.info(f"[KB] Loaded {len(chunks)} chunks into memory (all-MiniLM-L6-v2)")
    return chunks, np.array(embeddings, dtype=np.float32)


# Load and embed entire KB at server start — stays in RAM, zero latency at query time
_chunks, _embeddings = _load_kb()


def retrieve_context(query: str, top_k: int = 1) -> str:
    """Cosine similarity search over in-memory KB. Returns top chunk(s) or empty string."""
    query_vec = _model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
    scores = _embeddings @ query_vec  # cosine similarity (vectors are already normalized)

    if top_k == 1:
        idx = int(np.argmax(scores))
        if scores[idx] < _MIN_SCORE:
            return "No relevant information found."
        return _chunks[idx]

    top_indices = np.argsort(scores)[::-1][:top_k]
    results = [_chunks[i] for i in top_indices if scores[i] >= _MIN_SCORE]
    return "\n\n".join(results) if results else "No relevant information found."
