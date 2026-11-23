# How the agents worked

## Timing and scope

This work sample was built in one afternoon on 23 November 2026. The UI, gate and review commits cluster between 14:47 and 15:00 Swiss time because agents worked concurrently in separate worktrees and their changes were integrated in that session. PR #2 added the approval service later that afternoon, with a commit at 16:13 and merge at 16:15.

## Building the desk

The [acceptance brief](../docs/acceptance.md) described the three outcomes and the data exchanged by the Vue interface and Python workflow. Two implementation agents worked in separate Git worktrees. Their commits show the [interface](https://github.com/willbrealey/staging-desk/commit/0e0f1a5) and [workflow gates](https://github.com/willbrealey/staging-desk/commit/5223506).

An independent reviewer examined the integrated change. Fourteen Python tests had passed, yet changing the original status text could leave an old approval valid. Three new assertions reproduced the problem on [GitHub Actions](https://github.com/willbrealey/staging-desk/actions/runs/45188585686). The [correction](https://github.com/willbrealey/staging-desk/commit/86df24036674d3bb3691fdb0e5864bc750290cdf) gives both agents the original labels and binds review and approval to those labels in both languages. The reviewer also found a keyboard shortcut that changed the selected case. A browser regression now checks both the case URL and keyboard focus.

The reviewer independently replayed all three cases at [the corrected revision](https://github.com/willbrealey/staging-desk/commit/50f19a4f9aa8e8a7d4b6d0fb5898b08d511ac34a) and changed only the English baseline. The old review became blocked and lost its approval fingerprint. CI covers the Python workflow, PostgreSQL approval service and Chromium user flows. Current results are available in [the CI runs](https://github.com/willbrealey/staging-desk/actions/workflows/verify.yml).

## Running a wording request

The [ready case](../evidence/ready/) was generated in a fresh run after the correction. A read-only Codex author proposed the two labels. A separate read-only Codex reviewer received the request, original labels and proposal. The Python gate checked the returned identities before offering the product owner a decision. The other two public cases are deliberately constructed controls. CI replays all three without calling a model.

## Harness-owned input identities

Fresh runs ask the reviewer for a decision and reason only. The harness snapshots the baseline and hashes the request and proposal before invoking the reviewer. It saves the model output in review-verdict.json and attaches the saved input hashes in review.json. The replay gate then checks those hashes against the current baseline and recorded files. The checked-in ready case predates this change, so its `review.json` contains hashes the model returned. No live run has been recorded since.
