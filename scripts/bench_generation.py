"""Times candidate generation models on one RAG-shaped prompt and saves the raw output.

Usage: uv run python scripts/bench_generation.py results/<file>.json <runs> <model> [<model>...]
Calls the adapter directly (no cache, no ledger) so every run is a live call.
"""

import json
import sys
import time
from pathlib import Path

from google import genai
from pydantic import BaseModel

from niyam.config import get_settings
from niyam.models.gemini import GeminiGenerativeModel
from niyam.models.types import GenerationRequest

PASSAGES = [
    "[P1] Master Direction on PPIs, 9.1: Full-KYC PPIs may be issued up to a limit of "
    "Rs 2,00,000 outstanding at any point of time.",
    "[P2] Master Direction on PPIs, 9.2: Minimum-detail PPIs: amount loaded during any month "
    "shall not exceed Rs 10,000 and total amount loaded during the financial year shall not "
    "exceed Rs 1,20,000.",
    "[P3] Master Direction on PPIs, 10.1: Cash withdrawal using small PPIs is not permitted.",
    "[P4] Master Direction on PPIs, 12.3: Issuers shall make PPIs interoperable via UPI.",
]
QUESTIONS = [
    "What is the maximum balance a full-KYC PPI can hold?",
    "Can I withdraw cash from a minimum-detail PPI and what is the yearly load limit?",
    "What is the penalty for a bank missing the NEFT cut-off time?",
]


class Answer(BaseModel):
    answer: str
    citations: list[str]
    abstain: bool


def prompt_for(question: str) -> str:
    return (
        "Answer only from the passages and cite passage ids like P1. If the passages do not "
        "answer the question, set abstain to true.\n\n"
        + "\n".join(PASSAGES)
        + f"\n\n<question>{question}</question>"
    )


def main() -> None:
    out, runs, models = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3:]
    client = genai.Client(api_key=get_settings().gemini_api_key.get_secret_value())
    records = []
    for model in models:
        adapter = GeminiGenerativeModel(client, model)
        level = None if model.startswith("gemma") else "low"  # Gemma has no thinking levels
        for question in QUESTIONS[:runs]:
            start = time.perf_counter()
            try:
                result = adapter.generate(GenerationRequest(prompt_for(question), Answer, level))
                record = {"answer": result.output.model_dump(), "tokens": result.usage.total_tokens}
            except Exception as error:  # record every failure, then keep benchmarking
                record = {"error": f"{type(error).__name__}: {error}"[:300]}
            record |= {"model": model, "question": question}
            record["seconds"] = round(time.perf_counter() - start, 2)
            records.append(record)
            print(model, record["seconds"], record.get("error", record.get("tokens")))
            out.write_text(json.dumps(records, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
