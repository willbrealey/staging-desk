"""Collect one read-only Codex proposal, then run the independent preview gate."""
from pathlib import Path
import argparse
import json
import subprocess
import sys
from tempfile import TemporaryDirectory
from workflow import FIELDS, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("run_directory", type=Path, help="a new directory for this run")
    args = parser.parse_args()
    brief = subprocess.check_output(
        [sys.executable, str(ROOT / "workflow.py"), "brief", str(args.request)], text=True)
    out = args.run_directory.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "brief.txt").write_text(brief, encoding="utf-8")
    schema = {"type": "object", "additionalProperties": False,
              "properties": {k: {"type": "string"} for k in sorted(FIELDS)}, "required": sorted(FIELDS)}
    schema["properties"]["decision"]["enum"] = ["propose", "escalate"]
    with TemporaryDirectory() as isolated:
        folder = Path(isolated)
        description = folder / "proposal.schema.json"
        description.write_text(json.dumps(schema), encoding="utf-8")
        proposal = out / "proposal.json"
        command = ["codex", "exec", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check",
                   "--sandbox", "read-only", "--output-schema", str(description),
                   "--output-last-message", str(proposal), "-"]
        try:
            result = subprocess.run(command, cwd=folder, input=brief, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"Agent unavailable: {exc}. The request is saved in {out}.", file=sys.stderr)
            return 1
        if result.returncode:
            return result.returncode
    return subprocess.run([sys.executable, str(ROOT / "workflow.py"), "preview",
                           str(proposal), str(out / "preview")]).returncode


if __name__ == "__main__":
    sys.exit(main())
