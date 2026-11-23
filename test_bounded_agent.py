import unittest

from bounded_agent import BoundedAgent


class BudgetTests(unittest.TestCase):
    def test_no_generation_when_tokens_exceed_budget(self):
        calls = []
        def provider(path, payload):
            calls.append(path)
            return {"input_tokens": 16000}
        agent = BoundedAgent("test", "1", "2", ".10", provider)
        with self.assertRaisesRegex(ValueError, "token"):
            agent("request", {"decision"}, ["accept"])
        self.assertEqual(calls, ["/input_tokens"])

    def test_no_generation_when_spend_exceeds_budget(self):
        calls = []
        def provider(path, payload):
            calls.append(path)
            return {"input_tokens": 200}
        agent = BoundedAgent("test", "1", "100", ".10", provider)
        with self.assertRaisesRegex(ValueError, "USD"):
            agent("request", {"decision"}, ["accept"])
        self.assertEqual(calls, ["/input_tokens"])

    def test_two_call_ceiling_output_limit_and_no_tools(self):
        seen = []
        def provider(path, payload):
            if path:
                return {"input_tokens": 100}
            seen.append(payload)
            return {"status": "completed", "output": [
                {"type": "message", "content": [{"type": "output_text", "text": '{"decision":"accept"}'}]}]}
        agent = BoundedAgent("test", "1", "2", ".10", provider)
        for _ in range(2):
            self.assertIn(b"accept", agent("request", {"decision"}, ["accept"]))
        with self.assertRaisesRegex(ValueError, "Two model"):
            agent("request", {"decision"}, ["accept"])
        self.assertEqual(len(seen), 2)
        self.assertTrue(all(p["max_output_tokens"] == 1200 and p["tools"] == [] for p in seen))
        self.assertEqual(agent.receipt()["reserved_tokens"], 2600)

    def test_failed_generation_keeps_reservation_and_never_retries(self):
        def provider(path, payload):
            if path:
                return {"input_tokens": 100}
            return {"status": "incomplete"}
        agent = BoundedAgent("test", "1", "2", ".10", provider)
        with self.assertRaisesRegex(ValueError, "allowance"):
            agent("request", {"decision"}, ["accept"])
        self.assertGreater(agent.reserved, 0)
        self.assertEqual(agent.calls, 1)

    def test_negative_nan_and_zero_rates_rejected(self):
        for rate in ("NaN", "-1", "0", "Infinity"):
            with self.assertRaises(ValueError):
                BoundedAgent("test", rate, "1", ".10")
