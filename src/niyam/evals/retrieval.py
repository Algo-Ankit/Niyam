"""Retrieval eval: keyword, vector and hybrid arms against gold paragraphs per question."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import psycopg

from niyam.models.interfaces import Embedder
from niyam.retrieval.store import embed_query, fuse, keyword_ranking, vector_ranking

ARMS = ("keyword", "vector", "hybrid")
CUTOFFS = (1, 3, 5)
_DEPTH = 10  # MRR counts a gold paragraph only within the top 10
_CANDIDATES = 24  # what search() uses for k = 8


@dataclass(frozen=True)
class Item:
    id: str
    question: str
    gold: tuple[str, ...]


def load_items(path: Path) -> list[Item]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            items.append(Item(row["id"], row["question"], tuple(row["gold"])))
    return items


def hit_at(ranked: Sequence[str], gold: Sequence[str], k: int) -> float:
    """1.0 if any gold paragraph is in the top `k`, else 0.0."""
    return 1.0 if set(ranked[:k]) & set(gold) else 0.0


def reciprocal_rank(ranked: Sequence[str], gold: Sequence[str]) -> float:
    """1 / rank of the first gold paragraph within the top 10, else 0."""
    for rank, citation in enumerate(ranked[:_DEPTH], start=1):
        if citation in gold:
            return 1.0 / rank
    return 0.0


@dataclass(frozen=True)
class Ranked:
    id: str
    gold: tuple[str, ...]
    rankings: dict[str, list[str]]  # arm -> citations, best first


def run(conn: psycopg.Connection, embedder: Embedder, items: list[Item]) -> list[Ranked]:
    """Rank every question with every arm."""
    ranked = []
    for item in items:
        keyword = keyword_ranking(conn, item.question, _CANDIDATES)
        vector = vector_ranking(conn, embed_query(embedder, item.question), _CANDIDATES)
        hybrid = [c for c, _ in fuse([keyword, vector])]
        ranked.append(
            Ranked(item.id, item.gold, {"keyword": keyword, "vector": vector, "hybrid": hybrid})
        )
    return ranked


def metrics(ranked: list[Ranked]) -> dict[str, dict[str, float]]:
    """Per arm: hit rate at 1, 3 and 5, and MRR within the top 10, rounded to 3 places."""
    result: dict[str, dict[str, float]] = {}
    for arm in ARMS:
        scores = {
            f"hit@{k}": sum(hit_at(r.rankings[arm], r.gold, k) for r in ranked) for k in CUTOFFS
        }
        scores["mrr@10"] = sum(reciprocal_rank(r.rankings[arm], r.gold) for r in ranked)
        result[arm] = {name: round(total / len(ranked), 3) for name, total in scores.items()}
    return result
