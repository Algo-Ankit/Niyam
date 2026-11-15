"""Postgres store: one row per provision with full-text and pgvector columns, plus hybrid search."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import psycopg

from niyam.corpus.ecfr import Provision
from niyam.models.interfaces import Embedder
from niyam.models.types import EmbeddingInput

_EMBED_BATCH = 90  # under 100 requests/minute; the free tier counts each text
_RRF_K = 60  # standard reciprocal-rank-fusion constant


@dataclass(frozen=True)
class Hit:
    citation: str
    headings: tuple[str, ...]
    body: str
    score: float


def create_schema(conn: psycopg.Connection, dimensions: int) -> None:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS provisions (
            citation text PRIMARY KEY,
            corpus_version text NOT NULL,
            headings text[] NOT NULL,
            body text NOT NULL,
            search_text text NOT NULL,
            tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', search_text)) STORED,
            embedding vector({int(dimensions)}) NOT NULL,
            embedding_model text NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS provisions_tsv ON provisions USING gin (tsv)")


def load_corpus(conn: psycopg.Connection, corpus_file: Path, embedder: Embedder) -> int:
    """Replace the indexed provisions with those in `corpus_file`; return the row count.

    Heading-only provisions are skipped: their headings already lead every child's search text.
    """
    corpus = json.loads(corpus_file.read_text(encoding="utf-8"))
    version = f"{corpus['current_as_of']}:{corpus['source_sha256'][:12]}"
    rows = [
        Provision(p["citation"], tuple(p["labels"]), tuple(p["headings"]), p["text"])
        for p in corpus["provisions"]
        if p["text"]
    ]
    vectors = _embed_documents(embedder, rows)
    with conn.transaction():
        conn.execute("DELETE FROM provisions")
        with conn.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO provisions (citation, corpus_version, headings, body, search_text,"
                " embedding, embedding_model) VALUES (%s, %s, %s, %s, %s, %s::vector, %s)",
                [
                    (
                        r.citation,
                        version,
                        list(r.headings),
                        r.text,
                        r.search_text,
                        _literal(v),
                        embedder.model_id,
                    )
                    for r, v in zip(rows, vectors, strict=True)
                ],
            )
    return len(rows)


def search(conn: psycopg.Connection, embedder: Embedder, query: str, k: int = 8) -> list[Hit]:
    """Keyword and vector search over the same rows, fused by reciprocal rank."""
    vector = embed_query(embedder, query)
    candidates = max(k * 3, 20)
    rankings = [keyword_ranking(conn, query, candidates), vector_ranking(conn, vector, candidates)]
    fused = fuse(rankings)[:k]
    scores = dict(fused)
    return [
        Hit(h.citation, h.headings, h.body, scores[h.citation])
        for h in by_citation(conn, [c for c, _ in fused])
    ]


def embed_query(embedder: Embedder, query: str) -> list[float]:
    return embedder.embed([EmbeddingInput(query, "query")]).vectors[0]


def keyword_ranking(conn: psycopg.Connection, query: str, limit: int) -> list[str]:
    """Citations matching any query word, best ts_rank_cd first."""
    rows = conn.execute(
        # NOTE: plainto_tsquery ANDs every word, so full questions rarely match; OR them instead
        # and let ts_rank_cd reward provisions that cover more of the words.
        "SELECT citation FROM provisions,"
        " to_tsquery('english', replace(plainto_tsquery('english', %s)::text, '&', '|')) AS q"
        " WHERE tsv @@ q ORDER BY ts_rank_cd(tsv, q) DESC LIMIT %s",
        (query, limit),
    ).fetchall()
    return [c for (c,) in rows]


def vector_ranking(conn: psycopg.Connection, vector: Sequence[float], limit: int) -> list[str]:
    """Citations by cosine distance to `vector`, nearest first."""
    rows = conn.execute(
        "SELECT citation FROM provisions ORDER BY embedding <=> %s::vector LIMIT %s",
        (_literal(vector), limit),
    ).fetchall()
    return [c for (c,) in rows]


def by_citation(conn: psycopg.Connection, citations: Sequence[str]) -> list[Hit]:
    """The indexed provisions with these citations, in the order given (score 0)."""
    rows = {
        citation: (tuple(headings), body)
        for citation, headings, body in conn.execute(
            "SELECT citation, headings, body FROM provisions WHERE citation = ANY(%s)",
            (list(citations),),
        ).fetchall()
    }
    return [Hit(c, *rows[c], score=0.0) for c in citations if c in rows]


def fuse(rankings: Sequence[Sequence[str]]) -> list[tuple[str, float]]:
    """Reciprocal rank fusion: score = sum of 1 / (60 + rank); ties keep first-seen order."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (_RRF_K + rank)
    return sorted(scores.items(), key=lambda pair: -pair[1])


def _embed_documents(embedder: Embedder, rows: list[Provision]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(rows), _EMBED_BATCH):
        batch = rows[start : start + _EMBED_BATCH]
        inputs = [EmbeddingInput(r.text, "document", title=_title(r)) for r in batch]
        vectors.extend(embedder.embed(inputs).vectors)
    return vectors


def _title(row: Provision) -> str:
    return f"{row.citation} " + " > ".join(h for h in row.headings if h)


def _literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in vector) + "]"
