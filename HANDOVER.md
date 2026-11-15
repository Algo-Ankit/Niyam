## Goal & Git state
Goal: a US consumer-payments Compliance Checker (RAG with evals and monitoring) on public-domain text; Phase 0 closed, Phase 1 re-planned, not started.
Branch main, last commit eb2b898 "Record the US re-scope and Compliance Checker decisions". Uncommitted: none. This handover commit is pushed with it.

## Done & Verified
- Re-scoped from RBI/NPCI to US consumer payments: RBI Disclaimer and NPCI terms prohibit "caching" and give no licence; NPCI robots.txt blocks unnamed bots (D37). Unverified by code; from subagent web research.
- Product chosen: Compliance Checker (policy/ToS in, findings table out) plus idea-triage mode that never says "legal" (D39). Official government sources only (D38).
- Findings (agent-read, unverified by code): CFPB says its content is public domain; eCFR is keyless; Reg E 12 CFR 1005 fetched as XML (section = DIV8, appendix = DIV9, paragraphs are flat <P> with "(a)" text labels); Supplement I (commentary) is in the same XML. Part 1026 untested.
- Currency (agent-read): Part 1005 last amended 2025-10-01, Part 1026 2026-03-01; no stay or rescission found. CFPB funding litigation is unverified.
- Suite still passes after the DECISIONS commit: pre-commit hook ran ruff, format, mypy, pytest (36 passed).
- Decisions D37 to D39 logged; no code or RESULTS changes this session.

## Open questions
- Reg Z scope: proposed card-relevant subparts only (open-end credit, 1026.12 and .13 with commentary), not all of Part 1026. Not yet approved.
- CFPB Reg E FAQs: proposed as test source only, never indexed. Not yet approved.
- Whether to send RBI/NPCI/none a permission request: moot unless the India scope returns.
- Ask CFPB usable count is unknown (agent guess 60 to 150 is unsourced); sitemap gave 403 to scripts.
- AI Studio "used" counts vs local ledger; ledger/cache in .state/ reset on free hosting (Phase 4).

## Gotchas
- eCFR robots.txt disallows /api/versioner/v1/full/: do not bulk crawl it. Use govinfo bulk CFR XML (govinfo.gov/bulkdata/CFR, untested) or a handful of polite requests; send Accept-Encoding (curl --compressed) or the API errors.
- Do not spoof a browser User-Agent; use a clear one and stop on 403/418. Do not use CFPB logo or name as endorsement.
- docs/PROJECT_CONTEXT.md still describes RBI, Jev and hydrogen; D21, D33, D35, D37 supersede it. Update sections 1, 4, 6, 7, 13, 14 only after plan approval. Read it by section (D29).
- "#N" in CLAUDE.md rules means "DN"; next decision is D40, next result R4.
- `uv` is `.tools/bootstrap/Scripts/uv.exe` on Windows. Python writes CRLF: edit with the Edit tool or open files with newline=''.
- Generator `gemini-3.5-flash-lite` 500 RPD; judge `gemma-4-31b-it` 16K tokens/min (about 4 judge calls/min, rejects thinking_level); decision model 10K RPD. Per-obligation checks go to the decision model, the summary to the generator.
- `verify-providers` makes live calls that count against quota. Deny rules block reading .env, .venv, .tools and caches.
- Subagent reports are unverified model output and some counts came from scraper summaries; re-verify from raw pages at download time. Keep subagents on Sonnet or Opus at medium effort, capped reports; owner objected to Fable at high effort.

## Next step
On Opus, present the revised Phase 1 plan for approval (no edits before): update docs/PROJECT_CONTEXT.md to the new scope; spike of about 5 polite requests fetching 12 CFR 1005 and 1026 (with Supplement I) from govinfo bulk data and enumerating Ask CFPB category pages; then obligation register, chunker (parse flat "(a)(1)" labels into a hierarchy), Postgres load, seeded-defect and idea test sets.

Records: DECISIONS.md latest D39, RESULTS.md latest R3.
