#!/usr/bin/env python3
"""Dump the HTTP request for a given test case as JSON."""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lm15-python"))

from lm15.curl import dump_http


def main():
    if len(sys.argv) < 2:
        print("usage: dump_request.py <test-case-json>", file=sys.stderr)
        sys.exit(1)

    case = json.loads(sys.argv[1])
    model = case["model"]
    prompt = case["prompt"]
    kwargs = {}
    if "system" in case:
        kwargs["system"] = case["system"]
    if "temperature" in case:
        kwargs["temperature"] = case["temperature"]
    if "max_tokens" in case:
        kwargs["max_tokens"] = case["max_tokens"]
    if "stream" in case:
        kwargs["stream"] = case["stream"]
    if case.get("tools"):
        from lm15.types import FunctionTool
        kwargs["tools"] = [
            FunctionTool(
                name=t["name"],
                description=t.get("description"),
                parameters=t.get("parameters", {"type": "object", "properties": {}}),
            )
            for t in case["tools"]
        ]

    result = dump_http(model, prompt, api_key="test-key", **kwargs)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
