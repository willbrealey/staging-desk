"""One author call, then an independent reviewer call if deterministic checks pass."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from workflow import AUTHOR_FIELDS, REVIEW_FIELDS, ROOT, assess, baseline, baseline_digest, bytes_from, digest, request_text


def call_agent(prompt, fields, decisions):
    schema = {"type": "object", "additionalProperties": False, "required": sorted(fields),
              "properties": {k: {"type": "string"} for k in sorted(fields)}}
    schema["properties"]["decision"]["enum"] = decisions
    with TemporaryDirectory() as isolated:
        work = Path(isolated)
        description = work / "schema.json"
        description.write_text(json.dumps(schema), encoding="utf-8")
        output = work / "reply.json"
        cmd = ["codex", "exec", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check",
               "--sandbox", "read-only", "--output-schema", str(description),
               "--output-last-message", str(output), "-"]
        subprocess.run(cmd, cwd=work, input=prompt, text=True, timeout=120, check=True)
        return bytes_from(output)


def run(request_path, out, invoke=call_agent):
    request = bytes_from(request_path)
    request_string = request_text(request)
    out.mkdir(parents=True, exist_ok=False)
    (out / "request.txt").write_bytes(request)
    prompt = (ROOT / "agent-brief.txt").read_text(encoding="utf-8")
    stage = "author"
    original = baseline()
    context_hash = baseline_digest()
    try:
        message = {"baseline": original, "request": request_string}
        proposal = invoke(prompt + "\nInputs:\n" + json.dumps(message, ensure_ascii=False),
                          AUTHOR_FIELDS, ["propose", "escalate"])
        (out / "proposal.json").write_bytes(proposal)
        result = assess(request, proposal)
        if all(check["status"] == "pass" for check in result["checks"][:2]):
            # The reviewer sees the proposed text, but not the author's rationale.
            stage = "reviewer"
            payload = json.loads(proposal)
            candidate = {k: payload[k] for k in ("key", "en", "de")}
            inputs = {**message, "candidate": candidate, "baseline_sha256": context_hash,
                      "request_sha256": digest(request), "proposal_sha256": digest(proposal)}
            directions = (ROOT / "reviewer-brief.txt").read_text(encoding="utf-8")
            review = invoke(directions + "\nInputs:\n" + json.dumps(inputs, ensure_ascii=False),
                            REVIEW_FIELDS, ["accept", "reject", "escalate"])
            (out / "review.json").write_bytes(review)
            result = assess(request, proposal, review)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        failure = {"status": "blocked", "stage": stage, "error_type": type(exc).__name__,
                   "baseline_sha256": context_hash, "request_sha256": digest(request)}
        (out / "receipt.json").write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        raise
    (out / "receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("run_directory", type=Path, help="a new directory for the recorded exchange")
    args = parser.parse_args()
    try:
        outcome = run(args.request, args.run_directory)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Run stopped: {exc}", file=sys.stderr)
        return 1
    print(outcome["status"] + ": " + outcome["reason"])
    return 0 if outcome["status"] == "ready" else 1


if __name__ == "__main__":
    sys.exit(main())
