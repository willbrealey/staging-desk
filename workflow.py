"""Replay the review of a bounded UI copy change using Python's standard library."""
import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KEY = "report.sync.pending"
BEFORE = {"en": "Pending ({count})", "de": "Ausstehend ({count})"}
AUTHOR_FIELDS = {"decision", "key", "en", "de", "reason"}
REVIEW_FIELDS = {"decision", "baseline_sha256", "request_sha256", "proposal_sha256", "reason"}
PUBLIC_CASES = ROOT / "web/public/cases.json"
CASES = [
    ("ready", "Clarify the pending status", "Recorded live Codex author and reviewer"),
    ("blocked", "A translation loses the count", "Constructed regression fixture"),
    ("escalated", "Change when reports count as sent", "Constructed scope fixture"),
]


def digest(raw):
    return sha256(raw).hexdigest()


def baseline():
    return {"key": KEY, "labels": BEFORE.copy()}


def baseline_digest():
    encoded = json.dumps(baseline(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return digest(encoded.encode("utf-8"))


def bytes_from(path):
    with path.open("rb") as stream:
        data = stream.read(8193)
    if len(data) > 8192:
        raise ValueError(f"{path.name} exceeds the 8 KiB input limit")
    return data


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate field: {key}")
        result[key] = value
    return result


def read_object(raw, fields):
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_fields)
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("required fields: " + ", ".join(sorted(fields)))
    if not all(isinstance(v, str) for v in value.values()):
        raise ValueError("every proposal and review field must be a string")
    if not value["reason"].strip() or not value["reason"].isprintable() or len(value["reason"]) > 600:
        raise ValueError("provide a short, single-line reason")
    return value


def request_text(raw):
    text = raw.decode("utf-8").strip()
    if not text:
        raise ValueError("the product-owner request is empty")
    return text


def scope(proposal):
    if proposal["decision"] == "escalate":
        if proposal["en"] or proposal["de"]:
            raise ValueError("escalations must leave both proposed labels empty")
        return "escalated"
    if proposal["decision"] != "propose" or proposal["key"] != KEY:
        raise ValueError(f"only {KEY} may be changed")
    return "proposed"


def verify_labels(labels):
    for lang, value in labels.items():
        if not value.strip() or len(value) > 140 or not value.isprintable() or "<" in value or ">" in value:
            raise ValueError(f"{lang}: expected one plain-text label of 1–140 characters")
        other = value.replace("{count}", "")
        if value.count("{count}") != 1 or "{" in other or "}" in other:
            raise ValueError(f"{lang}: preserve exactly one literal {{count}} placeholder")


def assess(request_raw, proposal_raw, review_raw=None):
    """The only route to a ready decision. Hashes bind reviewed bytes, not model identity."""
    request = request_text(request_raw)
    hashes = {"baseline_sha256": baseline_digest(), "request_sha256": digest(request_raw),
              "proposal_sha256": digest(proposal_raw)}
    checks = [
        {"name": name, "status": "skipped", "detail": "Earlier checks must pass first."}
        for name in ("Edit scope", "Translation contract", "Independent review")
    ]
    result = {"request": request, "status": "blocked", "reason": "", "before": BEFORE.copy(),
              "after": None, "checks": checks, "reviewer": None, "sha256": None, **hashes}
    index = 0
    try:
        author = read_object(proposal_raw, AUTHOR_FIELDS)
        if scope(author) == "escalated":
            result.update(status="escalated", reason=author["reason"])
            checks[0].update(status="fail", detail="Behaviour changes require an engineer.")
            return result
        checks[0].update(status="pass", detail=f"Only the {KEY} display key is in scope.")
        index = 1
        result["after"] = {lang: author[lang] for lang in BEFORE}
        verify_labels(result["after"])
        checks[1].update(status="pass", detail="Both plain-text labels retain the exact {count} placeholder.")
        index = 2
        if review_raw is None:
            raise ValueError("an independent review of these exact inputs is required")
        review = read_object(review_raw, REVIEW_FIELDS)
        if any(review[field] != value for field, value in hashes.items()):
            raise ValueError("the review refers to another baseline, request or proposal")
        result["reviewer"] = review["reason"]
        if review["decision"] in {"reject", "escalate"}:
            if review["decision"] == "escalate":
                result["status"] = "escalated"
            raise ValueError(review["reason"])
        if review["decision"] != "accept":
            raise ValueError("unknown reviewer verdict")
        checks[2].update(status="pass", detail=review["reason"])
        # Tie the human decision to the displayed baseline and the reviewed change.
        reviewed = ":".join([hashes["baseline_sha256"], hashes["request_sha256"],
                             hashes["proposal_sha256"], digest(review_raw)])
        result.update(status="ready", reason="Verified for product-owner review.", sha256=digest(reviewed.encode("ascii")))
    except (ValueError, RecursionError) as exc:
        result["reason"] = str(exc)
        checks[index].update(status="fail", detail=str(exc))
    return result


def replay(directory):
    review = directory / "review.json"
    return assess(bytes_from(directory / "request.txt"), bytes_from(directory / "proposal.json"),
                  bytes_from(review) if review.is_file() else None)


def catalog():
    rows = []
    for kind, title, source in CASES:
        data = replay(ROOT / "evidence" / kind)
        if data["status"] != kind:
            raise ValueError(f"{kind} fixture produced {data['status']}: {data['reason']}")
        rows.append({"id": kind, "title": title, "source": source, **data})
    return json.dumps(rows, ensure_ascii=False, indent=2) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    replay_cmd = sub.add_parser("replay", help="Read request.txt, proposal.json and optional review.json")
    replay_cmd.add_argument("directory", type=Path)
    export = sub.add_parser("export", help="Generate the public UI from the recorded cases")
    export.add_argument("--check", action="store_true", help="Fail when the public catalog is stale")
    args = parser.parse_args()
    try:
        if args.command == "replay":
            result = replay(args.directory)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["status"] == "ready" else 1
        data = catalog()
        if args.check:
            if PUBLIC_CASES.read_text(encoding="utf-8") != data:
                raise ValueError("stale case catalog: run python3 workflow.py export")
        else:
            PUBLIC_CASES.parent.mkdir(parents=True, exist_ok=True)
            PUBLIC_CASES.write_text(data, encoding="utf-8")
        print("Verified three review cases.")
        return 0
    except (ValueError, OSError, RecursionError) as exc:
        print(f"Review stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
