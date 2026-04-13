#!/usr/bin/env python3
"""Dump the HTTP request for a given test case as JSON.

Uses the canonical lm15 message format for the 'messages' field.
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lm15-python"))

from lm15.types import BuiltinTool, FunctionTool, messages_from_json


def main():
    if len(sys.argv) < 2:
        print("usage: dump_request.py <test-case-json>", file=sys.stderr)
        sys.exit(1)

    case = json.loads(sys.argv[1])
    model = case["model"]
    kwargs = {}

    if "system" in case:
        kwargs["system"] = case["system"]
    if "temperature" in case:
        kwargs["temperature"] = case["temperature"]
    if "max_tokens" in case:
        kwargs["max_tokens"] = case["max_tokens"]
    if "top_p" in case:
        kwargs["top_p"] = case["top_p"]
    if "stop" in case:
        kwargs["stop"] = case["stop"]
    if "stream" in case:
        kwargs["stream"] = case["stream"]
    if case.get("reasoning"):
        kwargs["reasoning"] = case["reasoning"]

    if case.get("tools"):
        kwargs["tools"] = [
            FunctionTool(
                name=t["name"],
                description=t.get("description"),
                parameters=t.get("parameters", {"type": "object", "properties": {}}),
            )
            for t in case["tools"]
        ]

    if case.get("builtin_tools"):
        builtin = [
            BuiltinTool(name=t["name"], builtin_config=t.get("builtin_config"))
            for t in case["builtin_tools"]
        ]
        kwargs.setdefault("tools", [])
        kwargs["tools"].extend(builtin)

    # Determine prompt vs messages
    prompt = case.get("prompt")
    if case.get("messages"):
        kwargs["messages"] = messages_from_json(case["messages"])
        prompt = None

    # Provider passthrough
    provider_passthrough = case.get("provider")

    if provider_passthrough:
        from lm15.curl import _build_lm_request, http_request_to_dict, resolve_provider
        from lm15.factory import build_default
        from lm15.types import Config, LMRequest

        lm_request = _build_lm_request(model, prompt, **kwargs)

        existing_provider = dict(lm_request.config.provider or {})
        existing_provider.update(provider_passthrough)
        new_config = Config(
            max_tokens=lm_request.config.max_tokens,
            temperature=lm_request.config.temperature,
            top_p=lm_request.config.top_p,
            top_k=lm_request.config.top_k,
            stop=lm_request.config.stop,
            response_format=lm_request.config.response_format,
            tool_config=lm_request.config.tool_config,
            reasoning=lm_request.config.reasoning,
            provider=existing_provider or None,
        )

        lm_request = LMRequest(
            model=lm_request.model,
            messages=lm_request.messages,
            system=lm_request.system,
            tools=lm_request.tools,
            config=new_config,
        )

        resolved_provider = resolve_provider(model)
        client = build_default(api_key="test-key", provider_hint=resolved_provider)
        adapter = client.adapters.get(resolved_provider)
        stream = case.get("stream", False)
        http_req = adapter.build_request(lm_request, stream=stream)
        result = http_request_to_dict(http_req)
    else:
        from lm15.curl import dump_http
        result = dump_http(model, prompt, api_key="test-key", **kwargs)

    # Redact auth
    if "headers" in result:
        for k in list(result["headers"]):
            kl = k.lower()
            if kl in ("authorization", "x-api-key", "x-goog-api-key"):
                result["headers"][k] = "REDACTED"

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
