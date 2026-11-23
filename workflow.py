"""A single UI-copy proposal, checked independently before a local staging preview."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

ROOT = Path(__file__).resolve().parent
KEY = "report.sync.pending"
STATES = {
    "pending": {"en": "Pending ({count})", "de": "Ausstehend ({count})"},
    "sent": {"en": "Sent", "de": "Gesendet"},
}
FIELDS = {"decision", "key", "en", "de", "reason"}
LANGUAGES = {"en": "English", "de": "Deutsch"}


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate proposal field: {key}")
        result[key] = value
    return result


def validate(proposal):
    if not isinstance(proposal, dict) or set(proposal) != FIELDS:
        raise ValueError("expected only decision, key, en, de and reason")
    if not all(isinstance(v, str) for v in proposal.values()):
        raise ValueError("all proposal values must be text")
    if proposal["decision"] == "escalate":
        raise ValueError("engineer review requested: " + proposal["reason"][:300])
    if proposal["decision"] != "propose" or proposal["key"] != KEY:
        raise ValueError(f"only a copy proposal for {KEY} can reach staging")
    if not proposal["reason"].strip() or len(proposal["reason"]) > 500:
        raise ValueError("provide a short explanation for the reviewer")

    for lang in LANGUAGES:
        value = proposal[lang]
        if not value.strip() or len(value) > 140 or not value.isprintable() or "<" in value or ">" in value:
            raise ValueError(f"{lang}: expected a single plain-text label of at most 140 characters")
        remainder = value.replace("{count}", "")
        if value.count("{count}") != 1 or "{" in remainder or "}" in remainder:
            raise ValueError(f"{lang}: preserve exactly one literal {{count}} placeholder")
    return {lang: proposal[lang] for lang in LANGUAGES}


def render(labels, digest):
    panels = []
    for lang, title in LANGUAGES.items():
        before = escape(STATES["pending"][lang].format(count=3))
        after = escape(labels[lang].format(count=3))
        sent = escape(STATES["sent"][lang])
        rows = "".join(
            f'<div class="variant"><dt>{heading}</dt><dd lang="{lang}">{value}</dd></div>'
            for heading, value in [("Before", before), ("Proposed", after), ("Sent status", sent)]
        )
        panels.append(f'<section><h2>{title}</h2><dl>{rows}</dl></section>')
    return (ROOT / "preview.html").read_text(encoding="utf-8").replace("{{PANELS}}", "".join(panels)).replace("{{DIGEST}}", digest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prompt = sub.add_parser("brief", help="Write the context for a single coding agent to stdout")
    prompt.add_argument("request", type=Path)
    check = sub.add_parser("preview", help="Check agent JSON and write a new, local preview directory")
    check.add_argument("proposal", type=Path)
    check.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "brief":
        directions = (ROOT / "agent-brief.txt").read_text(encoding="utf-8")
        print(directions, "\nCurrent labels:", json.dumps(STATES, ensure_ascii=False),
              "\nProduct-owner request:\n", args.request.read_text(encoding="utf-8"))
        return 0

    try:
        with args.proposal.open("rb") as stream:
            raw = stream.read(8193)
        if len(raw) > 8192:
            raise ValueError("proposal exceeds 8 KiB")
        proposal = json.loads(raw, object_pairs_hook=unique_fields)
        labels = validate(proposal)
        fingerprint = sha256(raw).hexdigest()
        page = render(labels, fingerprint[:12])
        receipt = {"proposal_sha256": fingerprint, "allowed_key": KEY, "locales": list(labels),
                   "status": "awaiting_product_owner_review", "model_explanation": proposal["reason"]}
        # Never overwrite a previous preview. Each reviewed proposal keeps its receipt.
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("use a new output directory for each preview")
        with TemporaryDirectory(dir=args.output.parent) as temp:
            stage = Path(temp) / "preview"
            stage.mkdir()
            (stage / "index.html").write_text(page, encoding="utf-8")
            (stage / "receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            stage.rename(args.output)
    except (OSError, ValueError) as exc:
        print(f"Preview not created: {exc}", file=sys.stderr)
        return 1
    print(f"Ready for product-owner review: {args.output / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
