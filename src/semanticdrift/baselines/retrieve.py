"""Nearest worked example for the retrieval-augmented baseline (§8.8)."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, List, Optional, Sequence, Tuple

from semanticdrift.baselines.examples import CORPUS, WorkedExample, render_example

_WORD = re.compile(r"[a-z0-9]+", re.I)


def retrieve_reference(
    query: str,
    corpus: Optional[Sequence[WorkedExample]] = None,
    use_embeddings: bool = False,
) -> Tuple[WorkedExample, float]:
    items = list(corpus or CORPUS)
    if not items:
        raise ValueError("retrieval corpus is empty")
    if use_embeddings:
        try:
            hit = _embedding_hit(query, items)
            if hit is not None:
                return hit
        except Exception:
            pass
    return _bow_hit(query, items)


def retrieval_prefix(
    query: str,
    corpus: Optional[Sequence[WorkedExample]] = None,
    use_embeddings: bool = False,
) -> Tuple[str, str]:
    example, _score = retrieve_reference(query, corpus, use_embeddings=use_embeddings)
    text = (
        "RETRIEVED REFERENCE (nearest TLA+ Examples translation; "
        "not gold Promela for this task):\n\n" + render_example(example)
    )
    return text, example.example_id


def _tokens(text: str) -> List[str]:
    return [tok.lower() for tok in _WORD.findall(text)]


def _bow_hit(query: str, items: Sequence[WorkedExample]) -> Tuple[WorkedExample, float]:
    vocab = sorted({tok for item in items for tok in _tokens(_example_text(item))})
    vocab.extend(tok for tok in _tokens(query) if tok not in vocab)
    qvec = _vector(_tokens(query), vocab)
    best: Optional[WorkedExample] = None
    best_score = -1.0
    for item in items:
        score = _cosine(qvec, _vector(_tokens(_example_text(item)), vocab))
        if score > best_score:
            best = item
            best_score = score
    assert best is not None
    return best, best_score


def _example_text(item: WorkedExample) -> str:
    return f"{item.title}\n{item.requirement}\n{item.model}"


def _vector(tokens: Iterable[str], vocab: Sequence[str]) -> List[float]:
    counts = Counter(tokens)
    return [float(counts.get(word, 0)) for word in vocab]


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    n1 = math.sqrt(sum(a * a for a in left))
    n2 = math.sqrt(sum(b * b for b in right))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


def _embedding_hit(
    query: str,
    items: Sequence[WorkedExample],
) -> Optional[Tuple[WorkedExample, float]]:
    from sentence_transformers import SentenceTransformer, util

    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    corpus_text = [_example_text(item) for item in items]
    corpus_emb = embedder.encode(corpus_text, convert_to_tensor=True)
    query_emb = embedder.encode(query, convert_to_tensor=True)
    hits = util.semantic_search(query_emb, corpus_emb, top_k=1)[0]
    if not hits:
        return None
    row = hits[0]
    return items[int(row["corpus_id"])], float(row["score"])
