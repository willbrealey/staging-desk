"""Offline contract, reviewer handoff, replay and public-catalog regressions."""
import json
import sys
from pathlib import Path
from subprocess import run as cli
from tempfile import TemporaryDirectory
import unittest

from run_agent import run
from workflow import ROOT, assess, bytes_from, catalog, digest, replay


def encode(data):
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


REQUEST = b"Clarify in EN/DE that the pending report is saved locally and waiting to sync. Keep the count."
PROPOSAL = {"decision": "propose", "key": "report.sync.pending", "en": "Saved locally, waiting to sync ({count})",
            "de": "Lokal gespeichert, wartet auf Synchronisierung ({count})", "reason": "Clarify the label."}


def review(request=REQUEST, proposal=None, **changes):
    raw = encode(PROPOSAL) if proposal is None else proposal
    return encode({"decision": "accept", "reason": "Both labels describe a local save pending upload.",
                   "request_sha256": digest(request), "proposal_sha256": digest(raw), **changes})


class GateTests(unittest.TestCase):
    def test_complete_handoff_creates_ready_decision(self):
        result = assess(REQUEST, encode(PROPOSAL), review())
        self.assertEqual(result["status"], "ready")
        self.assertEqual([c["status"] for c in result["checks"]], ["pass"] * 3)
        self.assertEqual(result["after"]["de"], PROPOSAL["de"])
        self.assertEqual(len(result["sha256"]), 64)

    def test_english_and_german_each_require_a_single_literal_count(self):
        for lang in ("en", "de"):
            for text in ("Text", "{n}", "{count!r}", "{{count}}", "{count:03}", "{count} {count}"):
                with self.subTest(lang=lang, text=text):
                    raw = encode({**PROPOSAL, lang: text})
                    result = assess(REQUEST, raw, review(proposal=raw))
                    self.assertEqual(result["status"], "blocked")
                    self.assertIn(lang + ":", result["reason"])
                    self.assertEqual(result["checks"][2]["status"], "skipped")

    def test_invalid_author_envelope_or_scope_cannot_reach_review(self):
        for raw in (b"[]", b"invalid", b'{"key": "a", "key": "b"}', encode({**PROPOSAL, "de": 2}),
                    encode({**PROPOSAL, "reason": ""}), encode({**PROPOSAL, "auth": True}),
                    encode({**PROPOSAL, "key": "report.sync.sent"}), encode({**PROPOSAL, "decision": "unknown"})):
            with self.subTest(raw=raw):
                result = assess(REQUEST, raw, review(proposal=raw))
                self.assertEqual(result["checks"][0]["status"], "fail")
                self.assertIsNone(result["sha256"])

    def test_labels_must_be_short_plain_printable_text(self):
        for label in ("", "{count}" + "a" * 140, "<em>{count}</em>", "{count}\nother"):
            with self.subTest(label=label):
                self.assertEqual(assess(REQUEST, encode({**PROPOSAL, "en": label}))["checks"][1]["status"], "fail")

    def test_requires_reviewer_and_original_hashes(self):
        author = encode(PROPOSAL)
        for candidate in (None, b"[]", review(request=b"Earlier request"), review(proposal=author + b" "),
                          review(decision="unknown"), review(decision="approve"), review(reason="")):
            with self.subTest(candidate=candidate):
                result = assess(REQUEST, author, candidate)
                self.assertEqual(result["status"], "blocked")
                self.assertIsNone(result["sha256"])
                self.assertEqual(result["checks"][2]["status"], "fail")

    def test_review_decision_can_reject_valid_structure_or_escalate_request(self):
        for verdict, status in (("reject", "blocked"), ("escalate", "escalated")):
            with self.subTest(verdict=verdict):
                result = assess(REQUEST, encode(PROPOSAL), review(decision=verdict, reason="Meaning changed."))
                self.assertEqual(result["status"], status)
                self.assertEqual(result["reviewer"], "Meaning changed.")
                self.assertIsNone(result["sha256"])

    def test_decision_key_changes_for_request_proposal_and_reviewer(self):
        raw = encode(PROPOSAL)
        keys = {assess(REQUEST, raw, review())["sha256"],
                assess(REQUEST + b" ", raw, review(request=REQUEST + b" "))["sha256"],
                assess(REQUEST, raw + b"\n", review(proposal=raw + b"\n"))["sha256"],
                assess(REQUEST, raw, review(reason="Independently verified."))["sha256"]}
        self.assertEqual(len(keys), 4)
        self.assertNotIn(None, keys)

    def test_author_escalation_cannot_carry_labels_or_reach_reviewer(self):
        esc = {**PROPOSAL, "decision": "escalate", "en": "", "de": ""}
        self.assertEqual(assess(REQUEST, encode(esc))["status"], "escalated")
        self.assertEqual(assess(REQUEST, encode({**esc, "en": "sent"}))["status"], "blocked")


class ReplayTests(unittest.TestCase):
    def test_recorded_cases_satisfy_expected_outcomes(self):
        ordered = json.loads(catalog())
        self.assertEqual([c["status"] for c in ordered], ["ready", "blocked", "escalated"])
        self.assertEqual(ordered[0]["source"], "Recorded live Codex author and reviewer")
        self.assertIn("de: preserve", ordered[1]["reason"])
        self.assertIsNone(ordered[2]["after"])

    def test_committed_public_catalog_is_reproducible(self):
        self.assertEqual(catalog(), (ROOT / "web/public/cases.json").read_text(encoding="utf-8"))

    def test_legacy_author_only_submission_fails_closed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "request.txt").write_bytes(REQUEST)
            (root / "proposal.json").write_bytes(encode(PROPOSAL))
            proc = cli([sys.executable, str(ROOT / "workflow.py"), "replay", str(root)], capture_output=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(json.loads(proc.stdout)["status"], "blocked")
            self.assertFalse((root / "receipt.json").exists())

    def test_empty_request_and_oversize_file_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            assess(b"\n", encode(PROPOSAL), review())
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "request.txt"
            path.write_bytes(b"a" * 8193)
            with self.assertRaisesRegex(ValueError, "8 KiB"):
                bytes_from(path)

    def test_fresh_orchestration_uses_two_roles_and_keeps_a_replayable_receipt(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = root / "request.txt"
            request.write_bytes(REQUEST)
            out = root / "recorded"
            calls = []
            def invoke(prompt, fields, decisions):
                calls.append(decisions)
                if decisions[0] == "propose":
                    return encode(PROPOSAL)
                self.assertIn(digest(REQUEST), prompt)
                self.assertIn(digest(encode(PROPOSAL)), prompt)
                self.assertNotIn(PROPOSAL["reason"], prompt)
                return review()
            outcome = run(request, out, invoke)
            self.assertEqual(calls, [["propose", "escalate"], ["accept", "reject", "escalate"]])
            self.assertEqual(outcome["status"], "ready")
            self.assertEqual(outcome, replay(out))
            self.assertEqual(outcome, json.loads((out / "receipt.json").read_text()))
            with self.assertRaises(FileExistsError):
                run(request, out, invoke)

    def test_author_scope_violation_short_circuits_second_call(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            request = folder / "request.txt"
            request.write_bytes(REQUEST)
            calls = []
            def invoke(prompt, fields, choices):
                calls.append(choices)
                return encode({**PROPOSAL, "de": "Anzahl fehlt"})
            out = folder / "run"
            self.assertEqual(run(request, out, invoke)["status"], "blocked")
            self.assertEqual(len(calls), 1)
            self.assertFalse((out / "review.json").exists())


if __name__ == "__main__":
    unittest.main()
