"""Tool-free Responses author/reviewer with token and configured spend ceilings."""
import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from run_agent import run


def api(path, payload):
    request = Request("https://api.openai.com/v1/responses" + path,
                      data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json",
                               "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]})
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read(1_048_577)
    except HTTPError as exc:
        raise ValueError(f"Model provider rejected the request with HTTP {exc.code}") from None
    if len(raw) > 1_048_576:
        raise ValueError("Provider response exceeds limit")
    return json.loads(raw)


class BoundedAgent:
    def __init__(self, model, input_rate, output_rate, budget, invoke=api):
        self.model = model
        self.input_rate = Decimal(input_rate)
        self.output_rate = Decimal(output_rate)
        self.budget = Decimal(budget)
        if not all(x.is_finite() and x > 0 for x in (self.input_rate, self.output_rate, self.budget)):
            raise ValueError("Rates and USD budget must be finite positive numbers")
        self.invoke = invoke
        self.calls = 0
        self.reserved = Decimal(0)
        self.tokens = 0

    def __call__(self, prompt, fields, decisions):
        if self.calls >= 2:
            raise ValueError("Two model calls exhausted")
        schema = {"type": "object", "additionalProperties": False, "required": sorted(fields),
                  "properties": {name: {"type": "string"} for name in fields}}
        schema["properties"]["decision"]["enum"] = decisions
        payload = {"model": self.model, "input": prompt, "store": False,
                   "tools": [], "max_output_tokens": 1200,
                   "text": {"format": {"type": "json_schema", "name": "copy_review",
                                       "strict": True, "schema": schema}}}
        count_payload = {key: value for key, value in payload.items()
                         if key not in {"store", "max_output_tokens"}}
        inputs = self.invoke("/input_tokens", count_payload)["input_tokens"]
        if not isinstance(inputs, int) or inputs < 1 or self.tokens + inputs + 1200 > 16000:
            raise ValueError("16,000 token request budget exceeded")
        reservation = (inputs * self.input_rate + 1200 * self.output_rate) / 1_000_000
        if self.reserved + reservation > self.budget:
            raise ValueError("Configured USD request budget exceeded")
        self.reserved += reservation
        self.tokens += inputs + 1200
        self.calls += 1
        response = self.invoke("", payload)
        if response.get("status") != "completed":
            raise ValueError("Model did not complete within output allowance")
        output = [part["text"] for item in response.get("output", []) if item.get("type") == "message"
                  for part in item.get("content", []) if part.get("type") == "output_text"]
        encoded = "".join(output).encode()
        if not encoded or len(encoded) > 8192:
            raise ValueError("Model output exceeds proposal limit or is empty")
        return encoded

    def receipt(self):
        return {"model": self.model, "calls": self.calls, "reserved_tokens": self.tokens,
                "reserved_usd": str(self.reserved), "limit_usd": str(self.budget),
                "input_usd_per_million": str(self.input_rate),
                "output_usd_per_million": str(self.output_rate)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--input-usd-per-million", required=True)
    parser.add_argument("--output-usd-per-million", required=True)
    parser.add_argument("--budget-usd", default="0.10")
    args = parser.parse_args()
    if args.directory.exists():
        parser.error("Choose a new run directory to preserve previous evidence")
    agent = BoundedAgent(args.model, args.input_usd_per_million,
                         args.output_usd_per_million, args.budget_usd)
    try:
        result = run(args.request, args.directory, agent)
        return 0 if result["status"] == "ready" else 1
    finally:
        if (args.directory / "request.txt").is_file():
            (args.directory / "budget.json").write_text(json.dumps(agent.receipt(), indent=2) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
