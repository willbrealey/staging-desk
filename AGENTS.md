# Staging Desk
Read README.md and docs/acceptance.md before editing. All cases are synthetic.

- A writer owns one Git worktree. Keep a shared acceptance contract when changes cross Vue, Python and database boundaries.
- Freeze the integrated commit before asking a fresh reviewer to check its diff, caller behaviour and test results. Re-review after code changes.
- The copy author may propose one label. Runtime reviewers see the original request and baseline without the author’s rationale.
- Keep credentials out of tracked files, prompts and logs. Runtime SQL uses desk_runtime. Never use a superuser or migration credential in the API.
- Authenticate before deriving transaction-local tenant and actor identity. Test isolation in PostgreSQL with no application tenant filter.
- An approval and its audit event must commit together. Test stale evidence, concurrent retries and audit failure.
- Run sh scripts/check.sh. Service changes also require python3 -m pytest tests/test_service.py with a disposable PostgreSQL database. Frontend changes require npm run build and npm test in web.
- Enable the local push hook with git config core.hooksPath .githooks. CI repeats the checks regardless of local hook configuration.
- Use the Responses runner for enforced token and per-request spend budgets. The older Codex CLI runner has call and time bounds only. Never describe a timeout as a monetary cap.
