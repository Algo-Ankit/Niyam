# Providers

Verified 2026-11-14. **docs** = stated on the provider's official documentation;
**measured** = observed in a live call from this repo. Anything else is marked unverified.
Re-check with `uv run niyam verify-providers`.

## Decision model: `gemini-decision-1` (in use)

| Item | Value | Source |
|---|---|---|
| SDK call | `genai.Client(http_options={"api_version": "v1beta"}).decisions.create(model, input, questions)` | docs, measured |
| REST | `POST https://generativelanguage.googleapis.com/v1beta/decisions` | docs |
| Question types | `noul` (yes/no), `choice`, `score`; 1 to 1,000 questions per request | docs |
| Context | 262,144 tokens across shared input and all questions | docs |
| Answer shape | `answers` is a map keyed by question name, **in arbitrary order**; `noul` = P(yes) in 0.01 to 0.99, plus `confidence` | docs, measured |
| Usage fields | `usage.total_input_tokens`; output tokens always 0 | docs, measured |
| Billing | "Shared input counts once per request regardless of how many questions you ask" | docs |
| Free tier price | free of charge | docs (pricing page, model-extracted summary: confirm in AI Studio) |
| Free tier limits | 200 RPM, 50,000 TPM, 10,000 RPD | docs; owner to confirm from AI Studio |
| Quota separation from Hydrogen | limits listed per model, "applied per project"; not stated explicitly as separate | docs; owner to confirm |
| Caching | Decisions API supports no context caching; "repeated input across requests counts in full" | docs |
| Refusals | unsafe input returns HTTP 400 with no answers | docs |

**Measured (3 requests, 1,846 input tokens):**
- Single yes/no relevance question: 1,542 ms, 141 tokens, P(yes)=0.99.
- **Re-rank of 20 passages in one request:** 827 ms, 1,526 tokens. Both relevant passages
  0.97 and 0.98; a near-miss (a different PPI limit) 0.13; the other 17 between 0.02 and 0.09.
- Scope question ("Is this about RBI payments regulation…?") on an in-scope question: 0.95.

Weaknesses stated by the provider: choice questions always spread probability across options
even when none fits; scores are weighted averages. Numbers and dates stay verified by code
(DECISIONS D6).

## Decision model: Jev (TypeSafe AI), not in use

- Vercel AI Gateway lists `typesafe-ai/jev` (alias), `typesafe-ai/jev-1.13.0` and
  `typesafe-ai/jev-1.14.0`, type `evaluation`, 32,000-token context, 0.042 USD per million
  input tokens, output free (docs, gateway model catalogue).
- Endpoint `POST https://ai-gateway.vercel.sh/v1/decisions`: `model`, `input`, `questions`
  (`predicate`, `choice`, `score`); answers in question order; cost in
  `provider_metadata.gateway.cost`; balance via `GET /v1/credits` (docs).
- **Measured:** `GET /v1/credits` returned balance 0. The first decision call returned
  HTTP 403 `customer_verification_required`: "AI Gateway requires a valid credit card on file
  to service requests … to add a card and unlock your free credits." No model ran; spend 0.
- Docs: "Once you purchase credits, your account transitions to the paid tier and the monthly
  free credit no longer applies." Free credit amount and per-minute limits: not stated.
- To add Jev later: one adapter implementing `DecisionModel` plus one branch in
  `niyam.models.factory`.

## Generative model: `gemini-3.5-flash` (in use, D33)

Same Interactions API call as before (`client.interactions.create` with `thinking_level` and a
JSON `response_format`); only the model id changed. Latency on one RAG-shaped prompt, free tier,
thinking `low`: 3.5-flash 4.2 to 6.7 s (R1, R2). Candidates `gemini-3.6-flash` (3.7 to 6.0 s)
and `gemini-3.5-flash-lite` (3.4 to 3.9 s) were also fast and correct (R2). Free tier limits
(AI Studio, owner-confirmed 2026-11-15; the page shows used / limit): 3.6-flash, 3.8-flash and
hydrogen 5 RPM, 250K TPM, **20 RPD**; 3.5-flash-lite 15 RPM, 250K TPM, **500 RPD**;
decisions 200 RPM, 50K TPM, 10K RPD. **`gemini-3.5-flash` was not in the pasted list**, so its
limits are unconfirmed and unset in config.

Not chosen: `gemini-4-hydrogen` took 8.2 to 36.4 s (R1; earlier manual probes saw 30 to 76 s).
`gemini-3.7-flash` and `gemini-3.8-flash` took 63 to 226 s and wrongly abstained on one
answerable question (R1). Three questions per model is a smoke test, not a quality comparison.

## Embeddings: `gemini-embedding-2`

| Item | Value | Source |
|---|---|---|
| Dimensions | default 3,072; we use 768 (auto-normalised at reduced sizes) | docs, measured (norm 1.0) |
| Task hints | no `task_type`; prefixes `task: search result \| query: …` and `title: … \| text: …` | docs |
| Max input | 8,192 tokens, longer input "silently truncated" | docs |
| **Batching** | a plain list of strings returns **one aggregated vector**; wrap each text in its own `types.Content` to get one vector per text | docs, measured |
| Max items per request | not stated; whether 8,192 tokens is per item or per request is unverified (test in Phase 1) | — |
| Free tier limits | 100 RPM, 30K TPM, 1K RPD | AI Studio, owner-confirmed 2026-11-15 |

Measured: 4 texts sent as separate `Content`s returned 4 unit vectors in 947 ms using 109
tokens; the query's nearest document was the correct clause (cosine 0.833 vs 0.653 and 0.669).
pgvector's HNSW index supports up to 2,000 dimensions for `vector`, so 768 fits (docs, Neon).

## Langfuse Cloud (Hobby)

- SDK `langfuse` 5.2.0: `start_as_current_observation(as_type="span", ...)`,
  `score_current_trace(...)`, `create_score(...)`, `flush()`, `auth_check()` (measured: methods
  present, one trace with a nested span and a numeric score created).
- The SDK reads `LANGFUSE_BASE_URL`; we pass our `LANGFUSE_HOST` value explicitly as `host=`.
- Hobby: 50,000 units per month, units = traces + observations + scores, 30 days data access,
  ingestion 1,000 requests per minute (docs). Behaviour past 50,000: not stated.
- Docs note: on Langfuse Cloud, `POST /api/public/ingestion` stops accepting everything except
  scores on 16 November 2026. SDK v5 sends traces over OpenTelemetry, so it is unaffected.
- Measured: a 401 "Invalid credentials" was caused by the public and secret keys being swapped
  in `.env`; with the correct order, `auth_check()` returned true.

## Postgres: Neon (Free plan)

| Item | Value | Source |
|---|---|---|
| Server | PostgreSQL 18.7 | measured |
| pgvector | 0.8.7, `CREATE EXTENSION vector` works on Free | docs, measured |
| Vector search | HNSW index with `vector_cosine_ops` on `vector(768)` returned the expected nearest row | measured |
| Full-text search | GIN index on a generated `tsvector`; works with `'english'` passed explicitly | measured |
| Default text search config | `pg_catalog.simple`, so `'english'` must always be explicit | measured |
| Free plan | 1 GB storage per project, 100 CU-hours per month, scale to zero after 5 min (cannot disable) | docs |
| Pooled endpoint | PgBouncer transaction mode; SQL-level `PREPARE` and `SET` unsupported; migrations need the direct endpoint | docs |
| Connect time | 1,231 ms (one cold connection) | measured |

**Keyword search finding for Phase 2 (measured):** `to_tsvector('english', 'PPIs')` gives
`ppis`, but the query term `PPI` gives `ppi`, and `websearch_to_tsquery` requires every term to
match, so "cash withdrawal small PPI" missed "Cash withdrawal using small PPIs is not
permitted." `KYCs` folds to `kyc` correctly. The keyword retriever must normalise acronym
plurals and use OR-style queries ranked by `ts_rank_cd`.
