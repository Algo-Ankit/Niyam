"""HyDE: search with a hypothetical regulation passage instead of the student's question.

Students write "can I go without a job for a while?"; the regulation writes "may not accrue an
aggregate of more than 90 days of unemployment". A passage written in regulatory style sits
closer to the right paragraph in embedding space than the question does.
"""

import psycopg
from pydantic import BaseModel, Field

from niyam.config import ThinkingLevel
from niyam.models.interfaces import Embedder, GenerativeModel
from niyam.models.types import EmbeddingInput, GenerationRequest
from niyam.retrieval.store import vector_ranking


class _Passage(BaseModel):
    text: str = Field(description="One paragraph in the style of 8 CFR 214.2(f)")


def hypothetical_passage(
    generator: GenerativeModel, question: str, thinking_level: ThinkingLevel | None
) -> str:
    prompt = (
        "Write one short paragraph, in the wording style of the US regulation 8 CFR 214.2(f), "
        "that would answer this F-1 student question. Write it as regulation text, with no "
        f"commentary and no citations.\n\nQuestion: {question}"
    )
    return generator.generate(GenerationRequest(prompt, _Passage, thinking_level)).output.text


def hyde_ranking(
    conn: psycopg.Connection, embedder: Embedder, passage: str, limit: int
) -> list[str]:
    """Citations nearest to the hypothetical passage, embedded as a document."""
    vector = embedder.embed([EmbeddingInput(passage, "document")]).vectors[0]
    return vector_ranking(conn, vector, limit)
