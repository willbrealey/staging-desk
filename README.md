# A product-owner copy change, from request to staging preview

One coding agent proposes a bilingual interface change. An independent Python checker decides whether the change can be previewed. The product owner reviews the meaning of both translations. This local portfolio prototype uses a fictional training-report screen and synthetic data.

[Open the checked preview](preview/index.html) · [Read the request](examples/request.txt) · [Inspect the actual agent output](examples/proposal.json) · [Review receipt](preview/receipt.json)

## What to show on screen

1. Read the product owner’s request. The vague word “Pending” leaves people wondering whether they have to enter their report again.
2. Open the English and German preview. The proposed labels explain that the reports are saved on the device and waiting to sync. Compare the three-report counter and the separate “Sent” state in both languages.
3. Try the deliberately broken proposal below. The German looks plausible, but it lost the dynamic count. The checker rejects it before creating a preview directory. This is a constructed regression case. The recorded live model run passed on its first proposal.
4. Read the receipt. It identifies the exact proposal presented for human review. A native speaker still needs to judge whether the wording is accurate and natural. The receipt records a pending decision.

## Reproduce the local run

From this directory, with Python 3.9 or newer, choose new output directory names each time.

```sh
python3 -m unittest -v
python3 workflow.py preview examples/proposal.json .preview-valid
python3 workflow.py preview examples/missing-count.json .preview-invalid
```

The last command should exit with status 1 and mention the missing German placeholder. Open `.preview-valid/index.html` to inspect the result. A previous preview is never overwritten.

## Run a fresh agent

A signed-in Codex CLI is required for a new model call. The runner prepares the owner’s brief, invokes Codex once in a temporary read-only working directory and checks its structured proposal. Each run has a two-minute timeout. Request and response files remain available even if the checker refuses the proposal.

```sh
python3 run_agent.py examples/request.txt .preview-live
```

An alternative with an existing agent session is to run `python3 workflow.py brief examples/request.txt`, give the resulting brief to the agent and pass its JSON response to `workflow.py preview`.

## What is enforced

The proposal format allows edits to one display key in two locales. The checker requires both labels, the exact placeholder in each and plain text. The preview renders fixed synthetic states, escapes the labels and hashes the original proposal. An agent can request engineer review. Interpreting the request and assessing translation quality still require judgement.

The GitHub Actions workflow accepts proposal JSON as data when dispatched on the default branch, requests read-only repository permissions, runs the tests, and attaches the HTML preview and receipt. It can be tried after publishing to a GitHub repository with Actions enabled. The hosted workflow has not been run for this local prototype. The demo ends at review and has no production deployment integration.

## Recorded experiment

On 23 November 2026 the recorded read-only Codex call produced the checked-in proposal in one invocation. The CLI reported 18,000 tokens for the run. That figure includes harness overhead and does not establish the price paid. A practical next experiment would compare a smaller model or a shorter context on the same acceptance cases.

The idea comes from [IMPedia’s employer listing](https://swissdevjobs.ch/jobs/Institute-of-Medical-Procedures-Software-Engineer-Agentic-AI), which describes product-owner changes reaching staging, and [the developer’s release notes](https://apps.apple.com/ch/app/impedia/id1455999196), which mention clearer report-sync failures. This is an independent demonstration.
