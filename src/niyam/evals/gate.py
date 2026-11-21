"""Offline CI regression gate over committed baseline results and deterministic invariants (D75).

No network access or API secrets are required: every metric is recomputed directly from the
per-case rows in `results/*.json` (so tampered or stale summaries fail) and checked against
frozen v1 regression floors, alongside deterministic checks on all eval sets and the rules engine.
"""

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from niyam.evals import answers, edge, end_to_end, extraction, retrieval
from niyam.rules.opt import assess


@dataclass(frozen=True)
class GateCheck:
    name: str
    passed: bool
    actual: str
    requirement: str


def run_gate(root: Path = Path(".")) -> list[GateCheck]:
    """Run all offline regression and invariant checks under `root`."""
    checks: list[GateCheck] = []
    checks.extend(_check_retrieval_dev(root / "results/retrieval-dev-rerank-1.json"))
    checks.extend(_check_retrieval_test(root / "results/retrieval-test-rerank-1.json"))
    checks.extend(_check_extraction(root / "results/extraction-eval-3.json"))
    checks.extend(_check_pipeline(root / "results/pipeline-1.json"))
    checks.extend(_check_answers(root / "results/answers-1.json"))
    checks.extend(
        _check_edge(
            "R10:decline_and_security",
            root / "results/edge-decline-1.json",
            {
                "no_leak": 1.0,
                "asks_ok": 1.0,
                "avoids_forbidden": 0.95,
                "scope_ok": 0.85,
                "passed": 0.45,
            },
        )
    )
    checks.extend(
        _check_edge(
            "R11:h1b_cases",
            root / "results/edge-h1b-1.json",
            {
                "no_leak": 1.0,
                "asks_ok": 1.0,
                "avoids_forbidden": 0.95,
                "scope_ok": 0.78,
                "passed": 0.45,
            },
        )
    )
    checks.extend(
        _check_edge(
            "R13:edge_cases",
            root / "results/edge-cases-1.json",
            {
                "no_leak": 1.0,
                "asks_ok": 1.0,
                "counts_ok": 0.90,
                "avoids_forbidden": 0.90,
                "scope_ok": 0.80,
                "cites_gold": 0.80,
                "passed": 0.20,
            },
        )
    )
    checks.extend(_check_eval_sets_and_rules(root))
    checks.extend(_check_audits(root))
    return checks


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def _floors(
    prefix: str, actual: Mapping[str, float | int], floors: Mapping[str, float]
) -> list[GateCheck]:
    return [
        GateCheck(
            name=f"{prefix}.{metric}",
            passed=float(actual[metric]) >= threshold,
            actual=f"{float(actual[metric]):.3f}",
            requirement=f">= {threshold:.3f}",
        )
        for metric, threshold in floors.items()
    ]


def _check_retrieval_dev(path: Path) -> list[GateCheck]:
    data = _load_json(path)
    ranked = _ranked_items(data)
    recomputed = retrieval.metrics(ranked)
    rerank = recomputed["vector+rerank"]
    vector = recomputed["vector"]
    return [
        GateCheck(
            "R9:retrieval_dev.summary_matches_rows",
            recomputed == data["metrics"],
            "exact" if recomputed == data["metrics"] else "mismatch",
            "recomputed metrics match saved JSON",
        ),
        *_floors("R9:retrieval_dev.rerank", rerank, {"hit@1": 0.95, "hit@5": 0.98, "mrr@10": 0.95}),
        GateCheck(
            "R9:retrieval_dev.rerank_beats_vector_hit1",
            rerank["hit@1"] > vector["hit@1"],
            f"{rerank['hit@1']:.3f} vs {vector['hit@1']:.3f}",
            "vector+rerank hit@1 > vector hit@1",
        ),
        GateCheck(
            "R9:retrieval_dev.rerank_beats_vector_mrr10",
            rerank["mrr@10"] > vector["mrr@10"],
            f"{rerank['mrr@10']:.3f} vs {vector['mrr@10']:.3f}",
            "vector+rerank mrr@10 > vector mrr@10",
        ),
    ]


def _check_retrieval_test(path: Path) -> list[GateCheck]:
    data = _load_json(path)
    ranked = _ranked_items(data)
    recomputed = retrieval.metrics(ranked)
    comps = retrieval.comparisons(ranked)
    comp_dicts = {
        arm: {metric: asdict(interval) for metric, interval in by_metric.items()}
        for arm, by_metric in comps.items()
    }
    rerank = recomputed["vector+rerank"]
    rerank_comp = comps["vector+rerank"]
    return [
        GateCheck(
            "R12:retrieval_test.summary_matches_rows",
            recomputed == data["metrics"] and comp_dicts == data["versus_vector"],
            "exact"
            if (recomputed == data["metrics"] and comp_dicts == data["versus_vector"])
            else "mismatch",
            "recomputed metrics and bootstrap CIs match saved JSON",
        ),
        *_floors(
            "R12:retrieval_test.rerank", rerank, {"hit@1": 0.95, "hit@5": 0.98, "mrr@10": 0.95}
        ),
        GateCheck(
            "R12:retrieval_test.hit1_ci_positive",
            rerank_comp["hit@1"].low > 0,
            f"[{rerank_comp['hit@1'].low:+.3f}, {rerank_comp['hit@1'].high:+.3f}]",
            "95% CI low > 0",
        ),
        GateCheck(
            "R12:retrieval_test.mrr10_ci_positive",
            rerank_comp["mrr@10"].low > 0,
            f"[{rerank_comp['mrr@10'].low:+.3f}, {rerank_comp['mrr@10'].high:+.3f}]",
            "95% CI low > 0",
        ),
    ]


def _ranked_items(data: Mapping[str, Any]) -> list[retrieval.Ranked]:
    return [
        retrieval.Ranked(r["id"], tuple(r["gold"]), r["rankings"], r.get("passage"))
        for r in data["rankings"]
    ]


def _check_extraction(path: Path) -> list[GateCheck]:
    data = _load_json(path)
    scores = [
        extraction.Score(
            s["id"],
            tuple(s["wrong_fields"]),
            s["out_of_scope_correct"],
            s["has_deadlines"],
            s["deadlines_agree"],
        )
        for s in data["scores"]
    ]
    recomputed = extraction.summary(scores)
    return [
        GateCheck(
            "R6:extraction.summary_matches_rows",
            recomputed == data["summary"],
            "exact" if recomputed == data["summary"] else "mismatch",
            "recomputed summary matches saved JSON",
        ),
        *_floors(
            "R6:extraction",
            recomputed,
            {"all_fields_correct": 0.93, "out_of_scope_correct": 0.93, "deadlines_agree": 1.0},
        ),
    ]


def _check_pipeline(path: Path) -> list[GateCheck]:
    data = _load_json(path)
    scores = [end_to_end.ScenarioScore(**s) for s in data["scores"]]
    recomputed = end_to_end.summary(scores)
    return [
        GateCheck(
            "R14:pipeline.summary_matches_rows",
            recomputed == data["summary"],
            "exact" if recomputed == data["summary"] else "mismatch",
            "recomputed summary matches saved JSON",
        ),
        *_floors(
            "R14:pipeline",
            recomputed,
            {
                "scope_correct": 0.95,
                "deadlines_agree": 0.95,
                "in_scope_shown": 0.90,
                "in_scope_cites_gold": 0.90,
                "in_scope_correct": 0.85,
                "in_scope_grounded": 0.90,
                "unanswerable_abstained": 1.0,
            },
        ),
    ]


def _check_answers(path: Path) -> list[GateCheck]:
    data = _load_json(path)
    scores = [answers.AnswerScore(**s) for s in data["scores"]]
    recomputed = answers.summary(scores)
    return [
        GateCheck(
            "R15:answers.summary_matches_rows",
            recomputed == data["summary"],
            "exact" if recomputed == data["summary"] else "mismatch",
            "recomputed summary matches saved JSON",
        ),
        *_floors(
            "R15:answers",
            recomputed,
            {"shown": 0.95, "cites_gold": 0.90, "correct": 0.80, "grounded": 0.90},
        ),
    ]


def _check_edge(prefix: str, path: Path, floors: Mapping[str, float]) -> list[GateCheck]:
    data = _load_json(path)
    scores = [
        edge.CaseScore(**{k: v for k, v in s.items() if k not in ("passed", "judge_failed")})
        for s in data["scores"]
    ]
    recomputed = edge.summary(scores)
    return [
        GateCheck(
            f"{prefix}.summary_matches_rows",
            recomputed == data["summary"],
            "exact" if recomputed == data["summary"] else "mismatch",
            "recomputed grouped summary matches saved JSON",
        ),
        *_floors(prefix, recomputed["all"], floors),
    ]


def _check_eval_sets_and_rules(root: Path) -> list[GateCheck]:
    corpus = json.loads((root / "data/processed/8-cfr-214.2-f.json").read_text(encoding="utf-8"))
    indexed = {p["citation"] for p in corpus["provisions"] if p["text"]}
    dev = retrieval.load_items(root / "evals/retrieval-dev.jsonl")
    test = retrieval.load_items(root / "evals/retrieval-test.jsonl")
    answer_items = answers.load_items(root / "evals/retrieval-dev.jsonl")
    ext_items = extraction.load_items(root / "evals/extraction.jsonl")
    scenarios = end_to_end.load_scenarios(root / "evals/pipeline.jsonl")
    decline = edge.load_cases([root / "evals/independent/decline_and_security.jsonl"])
    h1b = edge.load_cases([root / "evals/independent/h1b_cases.jsonl"])
    edge_cases = edge.load_cases([root / "evals/independent/edge_cases.jsonl"])

    missing_citations = sorted(
        (
            {g for i in dev + test for g in i.gold}
            | {c for a in answer_items for c in (*a.gold, *a.context)}
            | {g for s in scenarios for g in s.gold}
        )
        - indexed
    )
    ext_findings = sum(bool(assess(item.facts, item.as_of).findings) for item in ext_items)
    pipe_findings = sum(bool(assess(sc.facts, sc.as_of).findings) for sc in scenarios)
    counts = (
        len(dev),
        len(test),
        len(answer_items),
        len(ext_items),
        len(scenarios),
        len(decline),
        len(h1b),
        len(edge_cases),
    )
    expected_counts = (60, 35, 40, 15, 40, 40, 70, 90)

    return [
        GateCheck(
            "invariants.indexed_corpus",
            len(indexed) >= 180,
            str(len(indexed)),
            ">= 180 indexed provisions",
        ),
        GateCheck(
            "invariants.eval_set_counts",
            counts == expected_counts,
            str(counts),
            f"== {expected_counts}",
        ),
        GateCheck(
            "invariants.builder_citations_indexed",
            not missing_citations,
            f"missing={len(missing_citations)}",
            "0 missing citations",
        ),
        GateCheck(
            "invariants.rules_engine_extraction_findings",
            ext_findings >= 11,
            str(ext_findings),
            ">= 11 items yield rules findings",
        ),
        GateCheck(
            "invariants.rules_engine_pipeline_findings",
            pipe_findings >= 20,
            str(pipe_findings),
            ">= 20 scenarios yield rules findings",
        ),
    ]


def _check_audits(root: Path) -> list[GateCheck]:
    judge_audit = _load_json(root / "results/judge-audit-1.json")
    gold_audit = _load_json(root / "results/gold-audit-1.json")
    judge_count = len(judge_audit.get("items", []))
    gold_total = gold_audit.get("summary", {}).get("total")
    gold_flagged = len(gold_audit.get("flagged", []))
    return [
        GateCheck(
            "R16:judge_audit_complete",
            judge_count == 30 and bool(judge_audit.get("provisional")),
            f"items={judge_count}, provisional={judge_audit.get('provisional')}",
            "30 items, provisional=true",
        ),
        GateCheck(
            "R16:gold_audit_complete",
            gold_total == 150 and gold_flagged == 23 and bool(gold_audit.get("provisional")),
            f"total={gold_total}, flagged={gold_flagged}",
            "total=150, flagged=23, provisional=true",
        ),
    ]
