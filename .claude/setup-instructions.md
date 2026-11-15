One-time setup for THIS project only. Reading this instruction file is allowed; it is the instruction itself.

## STEP 0: Scope and safety (hard rules)
- Write ONLY inside the current project directory. Never read, create, edit, or delete anything under ~/.claude/ or anywhere outside this project.
- Confirm the current directory is the repo root (`git rev-parse --show-toplevel` must equal `pwd`). If not, or if this is not a git repo, STOP and tell me.
- Before writing any file below that already exists, copy it to <name>.bak-<YYYYMMDD-HHMM> in the same folder.
- Do not modify source code. Inspect only top-level names and dependency manifests (package.json, pyproject.toml, requirements.txt, etc.). Do not scan the codebase.

## STEP 1: Draft ./CLAUDE.md
Write ./CLAUDE.md with the "Workflow rules" section below exactly as written, followed by a "Project map" section you draft (max 20 lines): one-line project purpose (ask me if unclear), stack, quiet test command for iterating, full test command, run command, 1-line pointers to top-level module directories.
If ./CLAUDE.md already exists, keep its existing project-specific content inside the Project map section (trimmed to 20 lines, nothing important dropped) and show me what you merged.
Show me the full draft and wait for my approval before writing.

```markdown
# Workflow rules

## Role & Collaboration
- I am the Architect and Decision-Maker; you are the Builder.
- For any new phase or multi-file change: state a brief plan, flag risks and holes in my assumptions, and wait for my approval before editing. Single-line fixes I explicitly request need no plan.
- Be critical: if my design has a flaw, name it and propose a better alternative before writing code. Do not agree just to be agreeable.
- If a tool, test, dependency, or external provider behaves differently than expected, STOP and tell me. Never silently work around failures, mock out broken integrations, skip tests, or edit/weaken tests to make them pass.
- In each phase briefing, explain any non-obvious concept in 2-3 plain sentences and state what I should be able to explain back.
- Keep diffs small and scoped to the approved plan. No drive-by refactors.
- Ask before destructive or irreversible actions: git reset --hard, force push, branch deletion, dropping data, deleting files outside the current task.
- Never commit secrets, API keys, or .env files. Never print secret values to the terminal.

## Token & Context Hygiene
- Reading files to do the work is fine. The limit is terminal output: never dump full data files, PDFs, lockfiles, logs, or large JSON to stdout; use head/tail, key listings, jq slices, or wc -l.
- Tests: use the quiet command from the Project map while iterating. Run the full suite before any commit and report pass/fail counts.
- Put permanent API/library edge cases as a 1-2 line `# NOTE:` comment directly above the relevant function, not in prose docs.
- Keep the Project map under 20 lines. Only add a 1-line pointer when a NEW top-level module directory or a NEW permanent spec in docs/ is created. Never list individual files or append bug notes to this file.

## Project Records (repo root)
- DECISIONS.md: append-only log of design decisions. The moment I approve a decision, append it immediately (do not wait for /handover). Never edit or delete past entries; a reversal is a new entry saying "Supersedes #N".
- RESULTS.md: append-only log of measurements (latency, cost, token counts, eval scores, accuracy). Only record numbers produced by code run in this repo, with the command and commit that produced them. Never estimate, round up, or carry over numbers from memory or the web. Measurement scripts save raw output under results/.
- Never put a metric in docs, README, or commit messages unless it has a RESULTS.md entry; cite it as R#N.
- Read these logs with tail (e.g. `tail -n 30 DECISIONS.md`), never the whole file.
- HANDOVER.md: a snapshot, updated only via /handover. Never append to it.

## Session Continuity
- /projectstatus reports where the project stands from HANDOVER.md and the logs. It does not restore a previous conversation. When I run /projectstatus, ask to continue previous work, or send my first task request of a session (not a quick question), follow the steps in .claude/commands/projectstatus.md before doing anything else. If HANDOVER.md does not exist, skip this silently and handle my request normally. Quick questions get answered directly.
```

## STEP 2: Write ./.claude/commands/handover.md with exactly this content:
```markdown
Update HANDOVER.md in the repo root. Follow these steps in order.

1. Guard: if this conversation contains no code changes, decisions, measurements, or findings since the last handover (for example, the session just started), do NOT write anything. Reply "Nothing new to hand over" and stop.
2. Read the existing HANDOVER.md if present. Carry forward Open questions and Gotchas that are still unresolved; drop ones resolved this session.
3. Append any decision I approved this session that is missing from DECISIONS.md, and any measurement produced this session that is missing from RESULTS.md, using the formats in those files.
4. Run `git status -s` and `git log --oneline -3`.
5. Overwrite HANDOVER.md from scratch, max 35 lines, with exactly these sections:

## Goal & Git state
Goal in one line. Branch, last commit hash + message, uncommitted files (list if <=5).
## Done & Verified
Concrete changes this session. Mark each as verified (with the command that proved it) or unverified.
## Open questions
Waiting on my decision. Write "None" if empty.
## Gotchas
Traps a fresh session would fall into. Write "None" if empty.
## Next step
The single exact next action, specific enough to start without re-reading the codebase.

Last line: "Records: DECISIONS.md latest #N, RESULTS.md latest R#N."

Rules: facts only, no padding, no metrics without a RESULTS.md entry. After writing, print only the line count and the Next step line. Do not commit unless I ask.
```

## STEP 3: Write ./.claude/commands/projectstatus.md with exactly this content:
```markdown
Read-only. Do not edit anything.
1. Read HANDOVER.md in the repo root. If it does not exist, say "No handover found" and stop.
2. Run `tail -n 30 DECISIONS.md` and `tail -n 20 RESULTS.md` if those files exist.
3. Run `git status -s` and `git log --oneline -5`.
4. List any commits or uncommitted changes the handover does not mention.
5. Reply in at most 6 lines: goal, where we are, discrepancies, open questions, proposed next step. Then wait for my go-ahead.
```

## STEP 4: Create the record files (only if they do not exist)
./DECISIONS.md with only this content:
```markdown
# Decisions (append-only)
Format:
## #N YYYY-MM-DD - <title>
- Decision: ...
- Why: ...
- Rejected alternatives: ...
```
./RESULTS.md with only this content:
```markdown
# Results (append-only, code-generated numbers only)
Format:
## R#N YYYY-MM-DD - <what was measured>
- Value: ...
- Produced by: <command or script> at commit <hash>
- Config: <model, provider, region, dataset, number of runs>
- Raw output: results/<file>
```
Create ./results/ if missing. Small result files (CSV/JSON under 1 MB) are committed; add larger outputs to .gitignore.
HANDOVER.md, DECISIONS.md, RESULTS.md, CLAUDE.md and .claude/commands/ must be committed, not gitignored. Tell me if .gitignore currently excludes any of them.

## STEP 5: Context blocking (needs my approval)
.claudeignore does NOT exist in Claude Code; never create one. Draft deny rules for ./.claude/settings.json (merge if it exists; never remove existing rules) covering only paths that actually exist in this repo, for example: "Read(./.env)", "Read(./.env.*)", "Read(./.venv/**)", "Read(./node_modules/**)", "Read(./dist/**)", "Read(./build/**)", large raw data folders. Do not deny lockfiles, results/, or data I may need you to read. Show me the rules and wait for approval before writing.

## STEP 6: Verify, then stop
- Check every file you wrote for non-ASCII characters with `grep -nP '[^\x00-\x7F]' <file>`. Remove any found and re-check.
- Run `git status -s` to show that every change is inside this repo.
- Print only: each file path written, its line count (wc -l), the non-ASCII check result, any backup paths created, and the git status output. Do not print file contents. Then stop and wait.
