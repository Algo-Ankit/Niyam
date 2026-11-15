"""LLM judge: is an answer correct against a reference, and grounded in the provisions given?

The judge is a different model family from the generator (D36). Its verdicts are
uncalibrated until the owner labels a sample and agreement is measured.
"""

from pydantic import BaseModel, Field

from niyam.models.interfaces import GenerativeModel
from niyam.models.types import GenerationRequest


class Verdict(BaseModel):
    correct: bool = Field(
        description="True if the answer states the reference's key facts (yes/no, numbers, "
        "dates, deadlines) and contradicts none of them; wording may differ"
    )
    grounded: bool = Field(
        description="True if every claim in the answer is supported by the provisions or findings"
    )
    reason: str = Field(description="One sentence explaining the verdict")


def judge(  # noqa: PLR0913 (each argument is one part of the judged case)
    model: GenerativeModel,
    *,
    question: str,
    reference: str,
    answer: str,
    provisions: str,
    findings: str,
) -> Verdict:
    prompt = (
        "You grade an assistant's answer about US F-1 student rules. Be strict about facts and "
        "lenient about wording. Extra correct detail is fine; any wrong number, date or yes/no "
        "makes the answer incorrect.\n\n"
        f"Question: {question}\n\nReference answer: {reference}\n\nAssistant answer: {answer}\n\n"
        f"Computed findings given to the assistant:\n{findings or '(none)'}\n\n"
        f"Provisions given to the assistant:\n{provisions}"
    )
    return model.generate(GenerationRequest(prompt, Verdict, thinking_level=None)).output
