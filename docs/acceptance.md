# Acceptance brief

Staging Desk is an independent public work sample for teams maintaining a multilingual training app. A product owner wants to clarify a report-sync message in English and German. An engineer owns changes to sync behaviour and permissions. All data is synthetic.

The public UI replays three cases: a verified wording change, a constructed translation that loses a required count, and a request to change when reports count as sent. Show the original request, EN/DE before and after, the independent checks and the decision. Only the verified case may receive a browser-local product-owner decision. Replaying the demo needs no account or model credentials. The live CLI is a separate opt-in path.

The coding workflow uses separate Git worktrees for the interface and gate implementation, followed by independent review of the integrated commit. The live proposal workflow uses two isolated read-only model calls (author and reviewer) plus deterministic tests. A disagreement, malformed output or scope violation must stop the handoff. Retain a reproducible proposal fingerprint, the reviewer verdict and the gate result. The reviewer must be bound to the exact proposal and request reviewed. No production release path is present.

## UI data contract

Independent review added a regression requirement. Editing either original label must invalidate the old model verdict and any product-owner decision, even if the request and proposed wording are identical. The [delivery record](delivery.md) links the failing check and correction.

The Python exporter owns web/public/cases.json. It generates an array. Each entry has id (ready, blocked or escalated), title, request, source, status (ready, blocked or escalated), reason, before and after (objects with en/de string templates, or null for after), checks (array of {name, status, detail} with status pass/fail/skipped), reviewer (string or null), sha256 (string or null). The preview substitutes a sample count of 3 for the literal {count}. Decisions belong to an individual proposal fingerprint. The UI worker can use a temporary fixture outside Git until export is available.
