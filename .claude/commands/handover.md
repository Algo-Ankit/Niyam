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
