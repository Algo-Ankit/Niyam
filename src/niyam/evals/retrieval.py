"""Retrieval eval: each arm ranked against gold paragraphs, compared with the vector arm."""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import psycopg

from niyam.evals.stats import Interval, paired_bootstrap
from niyam.models.interfaces import Embedder
from niyam.retrieval.hyde import hyde_ranking
from niyam.retrieval.store import embed_query, fuse, keyword_ranking, vector_ranking

CUTOFFS = (1, 3, 5)
BASELINE = "vector"
_DEPTH = 10  # MRR counts a gold paragraph only within the top 10
_CANDIDATES = 24  # candidates per arm before fusion


@dataclass(frozen=True)
class Item:
    id: str
    question: str
    gold: tuple[str, ...]


@dataclass(frozen=True)
class Ranked:
    id: str
    gold: tuple[str, ...]
    rankings: dict[str, list[str]]  # arm -> citations, best first
    passage: str | None = None  # the HyDE passage, when that arm ran


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


def run(
    conn: psycopg.Connection,
    embedder: Embedder,
    items: list[Item],
    passage_for: Callable[[str], str] | None = None,
    reorder: Callable[[str, list[str]], list[str]] | None = None,
) -> list[Ranked]:
    """Rank every question with every arm.

    HyDE arms run only when `passage_for` is given; the reranked arm only when `reorder` (the
    question and the vector ranking in, a reordered ranking out) is given.
    """
    ranked = []
    for item in items:
        keyword = keyword_ranking(conn, item.question, _CANDIDATES)
        vector = vector_ranking(conn, embed_query(embedder, item.question), _CANDIDATES)
        rankings = {"keyword": keyword, "vector": vector, "hybrid": _fused(keyword, vector)}
        if reorder is not None:
            rankings["vector+rerank"] = reorder(item.question, vector)
        passage = None
        if passage_for is not None:
            passage = passage_for(item.question)
            hyde = hyde_ranking(conn, embedder, passage, _CANDIDATES)
            rankings |= {"hyde": hyde, "vector+hyde": _fused(vector, hyde)}
        ranked.append(Ranked(item.id, item.gold, rankings, passage))
    return ranked


def metrics(ranked: list[Ranked]) -> dict[str, dict[str, float]]:
    """Per arm: hit rate at 1, 3 and 5, and MRR within the top 10, rounded to 3 places."""
    result: dict[str, dict[str, float]] = {}
    for arm in ranked[0].rankings:
        scores = {
            f"hit@{k}": sum(hit_at(r.rankings[arm], r.gold, k) for r in ranked) for k in CUTOFFS
        }
        scores["mrr@10"] = sum(reciprocal_rank(r.rankings[arm], r.gold) for r in ranked)
        result[arm] = {name: round(total / len(ranked), 3) for name, total in scores.items()}
    return result


def comparisons(ranked: list[Ranked]) -> dict[str, dict[str, Interval]]:
    """For each arm, the paired 95% interval of (arm - vector) on hit@1 and MRR@10."""
    result = {}
    for arm in ranked[0].rankings:
        if arm == BASELINE:
            continue
        result[arm] = {
            "hit@1": paired_bootstrap(
                [hit_at(r.rankings[BASELINE], r.gold, 1) for r in ranked],
                [hit_at(r.rankings[arm], r.gold, 1) for r in ranked],
            ),
            "mrr@10": paired_bootstrap(
                [reciprocal_rank(r.rankings[BASELINE], r.gold) for r in ranked],
                [reciprocal_rank(r.rankings[arm], r.gold) for r in ranked],
            ),
        }
    return result


def _fused(first: list[str], second: list[str]) -> list[str]:
    return [citation for citation, _ in fuse([first, second])]
