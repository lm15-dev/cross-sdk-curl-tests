#!/usr/bin/env python3
"""Dump the HTTP request for a given test case as JSON."""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lm15-python"))

from lm15.curl import dump_http
from lm15.types import FunctionTool, Message, Part


def build_messages(case):
    """Build lm15 Message objects from test case messages array."""
    msgs = []
    for m in case["messages"]:
        role = m["role"]
        content = m.get("content")

        # OpenAI-style function_call / function_call_output items
        if m.get("type") == "function_call":
            # These are provider-specific items that get passed through raw
            # We can't build them from lm15 messages — they'll be in provider passthrough
            continue
        if m.get("type") == "function_call_output":
            continue

        if isinstance(content, str):
            if role == "user":
                msgs.append(Message.user(content))
            elif role == "assistant":
                msgs.append(Message.assistant(content))
        elif isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, str):
                    parts.append(Part.text_part(c))
                elif c.get("type") in ("text", "input_text"):
                    parts.append(Part.text_part(c["text"]))
                elif c.get("type") in ("image", "input_image"):
                    # Image URL
                    url = None
                    if "image_url" in c:
                        url = c["image_url"]
                    elif "source" in c and c["source"].get("type") == "url":
                        url = c["source"]["url"]
                    if url:
                        parts.append(Part.image_url_part(url))
                elif c.get("type") == "tool_use":
                    parts.append(Part(type="tool_call", tool_call_id=c["id"],
                                      tool_name=c["name"],
                                      tool_args=c.get("input", {})))
                elif c.get("type") == "tool_result":
                    parts.append(Part(type="tool_result", tool_call_id=c["tool_use_id"],
                                      text=json.dumps(c.get("content", ""))))
            msgs.append(Message(role=role, parts=tuple(parts)))
        elif content is None and role == "assistant":
            # Assistant with tool_use blocks (anthropic multi-turn)
            msgs.append(Message.assistant(""))
    return msgs


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

    # Provider passthrough for fields not natively abstracted
    if case.get("provider"):
        # _build_lm_request doesn't expose provider kwarg directly,
        # but we can monkey-patch it through
        kwargs["_provider_passthrough"] = case["provider"]

    # Determine prompt vs messages
    prompt = case.get("prompt")
    messages = case.get("messages")

    if messages:
        kwargs["messages"] = build_messages(case)
        prompt = None

    # Build the request
    # We need to handle provider passthrough specially
    provider_passthrough = kwargs.pop("_provider_passthrough", None)

    if provider_passthrough:
        # We need to go lower-level to inject provider config
        from lm15.curl import _build_lm_request, build_http_request, http_request_to_dict
        from lm15.types import Config

        # Build LMRequest first
        lm_request = _build_lm_request(model, prompt, **kwargs)

        # Inject provider passthrough into config
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

        from lm15.types import LMRequest as LMReq
        lm_request = LMReq(
            model=lm_request.model,
            messages=lm_request.messages,
            system=lm_request.system,
            tools=lm_request.tools,
            config=new_config,
        )

        # Build HTTP request from LMRequest
        from lm15.curl import resolve_provider
        from lm15.factory import build_default
        resolved_provider = resolve_provider(model)
        client = build_default(api_key="test-key", provider_hint=resolved_provider)
        adapter = client.adapters.get(resolved_provider)
        stream = case.get("stream", False)
        http_req = adapter.build_request(lm_request, stream=stream)
        result = http_request_to_dict(http_req)
    else:
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
