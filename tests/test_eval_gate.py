"""Offline CI regression gate and generated report checks (D75)."""

import json
import re
import shutil
from pathlib import Path

from niyam.evals import gate, report

_ROOT = Path(__file__).parents[1]


def _copy_repo_inputs(tmp_path: Path) -> None:
    shutil.copytree(_ROOT / "results", tmp_path / "results")
    shutil.copytree(_ROOT / "evals", tmp_path / "evals")
    (tmp_path / "data" / "processed").mkdir(parents=True)
    shutil.copy2(
        _ROOT / "data/processed/8-cfr-214.2-f.json",
        tmp_path / "data/processed/8-cfr-214.2-f.json",
    )


def test_eval_gate_passes_on_committed_baselines() -> None:
    checks = gate.run_gate(_ROOT)
    assert checks
    assert all(check.passed for check in checks), [c for c in checks if not c.passed]


def test_eval_gate_fails_when_safety_floor_drops(tmp_path: Path) -> None:
    _copy_repo_inputs(tmp_path)
    path = tmp_path / "results/edge-decline-1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["scores"][0]["no_leak"] = False
    data["summary"]["all"]["no_leak"] = 0.975
    path.write_text(json.dumps(data), encoding="utf-8")

    checks = {c.name: c for c in gate.run_gate(tmp_path)}
    assert checks["R10:decline_and_security.no_leak"].passed is False


def test_eval_gate_detects_tampered_summary(tmp_path: Path) -> None:
    _copy_repo_inputs(tmp_path)
    path = tmp_path / "results/answers-1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["summary"]["correct"] = 0.999
    path.write_text(json.dumps(data), encoding="utf-8")

    checks = {c.name: c for c in gate.run_gate(tmp_path)}
    assert checks["R15:answers.summary_matches_rows"].passed is False


def test_eval_gate_fails_when_rerank_regresses(tmp_path: Path) -> None:
    _copy_repo_inputs(tmp_path)
    path = tmp_path / "results/retrieval-test-rerank-1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data["rankings"]:
        item["rankings"]["vector+rerank"] = list(reversed(item["rankings"]["vector"]))
    path.write_text(json.dumps(data), encoding="utf-8")

    checks = {c.name: c for c in gate.run_gate(tmp_path)}
    assert checks["R12:retrieval_test.rerank.hit@1"].passed is False


def test_generated_results_report_matches_committed_file_and_cites_runs() -> None:
    rendered = report.render_report(_ROOT)
    committed = (_ROOT / "docs/results.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert rendered == committed

    results_md = (_ROOT / "RESULTS.md").read_text(encoding="utf-8")
    defined = set(re.findall(r"^## (R\d+)\b", results_md, flags=re.MULTILINE))
    cited = set(re.findall(r"\bR\d+\b", rendered))
    assert not (cited - defined), cited - defined
    for expected in ("R5", "R6", "R7", "R8", "R9", "R10", "R11", "R12", "R13", "R14", "R15", "R16"):
        assert expected in cited
    assert "n/a (0 cases)" in rendered
