import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from workflow import ROOT, render, validate


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.good = json.loads((ROOT / "examples/proposal.json").read_text())
        self.fixture = json.loads((ROOT / "examples/missing-count.json").read_text())

    def test_missing_count_stops_before_staging(self):
        with self.assertRaisesRegex(ValueError, "de: preserve"):
            validate(self.fixture)

    def test_only_one_message_and_both_locales(self):
        for patch in [{"key": "report.sync.sent"}, {"status": "sent"}, {"de": ""}, {"de": 3}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validate({**self.good, **patch})

    def test_escalation_stops_before_staging(self):
        with self.assertRaisesRegex(ValueError, "engineer review"):
            validate({**self.good, "decision": "escalate", "reason": "Changes upload behaviour."})

    def test_only_supported_placeholder_and_plain_text(self):
        for de in ["{n}", "{count!r}", "{{count}}", "{count} {count}", "<b>{count}</b>"]:
            with self.subTest(de=de), self.assertRaises(ValueError):
                validate({**self.good, "de": de})

    def test_preview_shows_separate_states_and_escapes_copy(self):
        labels = validate({**self.good, "en": "Queued & saved ({count})"})
        page = render(labels, "demo")
        for expected in ["Queued &amp; saved (3)", "Pending (3)", "Gesendet", "Sent", "Awaiting product-owner review"]:
            self.assertIn(expected, page)

    def test_cli_real_files_review_receipt_and_rejected_output(self):
        with TemporaryDirectory() as temp:
            out = Path(temp) / "preview"
            cmd = [sys.executable, str(ROOT / "workflow.py"), "preview"]
            bad = ROOT / "examples/missing-count.json"
            good = ROOT / "examples/proposal.json"
            failure = subprocess.run([*cmd, str(bad), str(out)], capture_output=True, text=True)
            self.assertNotEqual(failure.returncode, 0)
            self.assertIn("de: preserve", failure.stderr)
            self.assertFalse(out.exists())
            subprocess.run([*cmd, str(good), str(out)], check=True, capture_output=True)
            receipt = json.loads((out / "receipt.json").read_text())
            self.assertEqual(receipt["proposal_sha256"], hashlib.sha256(good.read_bytes()).hexdigest())
            self.assertEqual(receipt["status"], "awaiting_product_owner_review")
            self.assertNotEqual(subprocess.run([*cmd, str(good), str(out)], capture_output=True).returncode, 0)

    def test_duplicate_fields_are_rejected(self):
        with TemporaryDirectory() as temp:
            proposal = Path(temp) / "duplicate.json"
            proposal.write_text('{"decision":"propose","decision":"escalate"}')
            result = subprocess.run([sys.executable,str(ROOT / "workflow.py"),"preview",str(proposal),str(Path(temp)/"out")],
                                    capture_output=True,text=True)
            self.assertIn("duplicate proposal field",result.stderr)
            self.assertNotEqual(result.returncode,0)


if __name__ == "__main__":
    unittest.main()
