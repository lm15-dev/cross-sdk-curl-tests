#!/usr/bin/env python3
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lm15-python2"))

from lm15.types import BuiltinTool, FunctionTool, Request, Config, Message
from lm15.serde import messages_from_json

def main():
    if len(sys.argv) < 2:
        print("usage: dump_request.py <test-case-json>", file=sys.stderr)
        sys.exit(1)

    case = json.loads(sys.argv[1])
    model = case["model"]
    
    # Infer provider from model or ID
    provider_name = case["id"].split(".")[0]

    if provider_name == "openai":
        from lm15.providers.openai import OpenAILM
        lm = OpenAILM(api_key="test-key")
    elif provider_name == "anthropic":
        from lm15.providers.anthropic import AnthropicLM
        lm = AnthropicLM(api_key="test-key")
    elif provider_name == "gemini":
        from lm15.providers.gemini import GeminiLM
        lm = GeminiLM(api_key="test-key")
    else:
        raise ValueError(f"Unknown provider: {provider_name}")

    kwargs = {}
    config_kwargs = {}

    if "system" in case:
        kwargs["system"] = case["system"]
        
    if "temperature" in case:
        config_kwargs["temperature"] = case["temperature"]
    if "max_tokens" in case:
        config_kwargs["max_tokens"] = case["max_tokens"]
    if "top_p" in case:
        config_kwargs["top_p"] = case["top_p"]
    if "stop" in case:
        config_kwargs["stop"] = case["stop"]
    if case.get("reasoning"):
        from lm15.serde import reasoning_from_dict
        config_kwargs["reasoning"] = reasoning_from_dict(case["reasoning"])

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
            BuiltinTool(name=t["name"], config=t.get("builtin_config"))
            for t in case["builtin_tools"]
        ]
        kwargs.setdefault("tools", [])
        kwargs["tools"].extend(builtin)

    prompt = case.get("prompt")
    if case.get("messages"):
        raw_msgs = case["messages"]
        for m in raw_msgs:
            for p in m.get("parts", []):
                if "source" in p:
                    src = p.pop("source")
                    src.pop("type", None)
                    p.update(src)
                if "arguments" in p:
                    p["input"] = p.pop("arguments")
        kwargs["messages"] = messages_from_json(raw_msgs)
        prompt = None
    elif prompt is not None:
        kwargs["messages"] = [Message.user(prompt)]

    # Provider passthrough
    provider_passthrough = case.get("provider")

    if provider_passthrough:
        if "tool_choice" in provider_passthrough:
            tc_raw = provider_passthrough["tool_choice"]
            if isinstance(tc_raw, str):
                tc_dict = {"mode": tc_raw}
            elif isinstance(tc_raw, dict):
                tc_dict = {"mode": tc_raw.get("type", "auto")}
                if tc_dict["mode"] in ("tool", "function"):
                    tc_dict["mode"] = "required"
                    tc_dict["allowed"] = [tc_raw["name"]]
                elif tc_dict["mode"] == "any":
                    tc_dict["mode"] = "required"
                if "disable_parallel_tool_use" in tc_raw:
                    tc_dict["parallel"] = not tc_raw["disable_parallel_tool_use"]
            from lm15.serde import tool_choice_from_dict
            config_kwargs["tool_choice"] = tool_choice_from_dict(tc_dict)
            
        # other passthrough fields might be response_format, reasoning etc.
        if "response_format" in provider_passthrough:
            config_kwargs["response_format"] = provider_passthrough["response_format"]
        
        # Everything else in provider passthrough is extensions
        extensions = {k: v for k, v in provider_passthrough.items() if k not in ["tool_choice", "response_format"]}
        if extensions:
            config_kwargs["extensions"] = extensions

    stream = case.get("stream", False)

    req = Request(
        model=model,
        messages=tuple(kwargs["messages"]),
        system=kwargs.get("system"),
        tools=tuple(kwargs.get("tools", [])),
        config=Config(**config_kwargs)
    )

    transport_req = lm.build_request(req, stream=stream)

    # Redact auth in headers
    headers = {}
    for k, v in transport_req.headers:
        kl = k.lower()
        if kl in ("authorization", "x-api-key", "x-goog-api-key"):
            headers[k] = "REDACTED"
        else:
            headers[k] = v

    # Reconstruct result
    result = {
        "method": transport_req.method,
        "url": transport_req.url,
        "headers": headers,
    }
    
    if transport_req.body:
        try:
            result["body"] = json.loads(transport_req.body.decode("utf-8"))
        except Exception:
            result["body"] = transport_req.body.decode("utf-8")
            
    if "?" in transport_req.url:
        import urllib.parse
        parsed = urllib.parse.urlparse(transport_req.url)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        result["params"] = params
        result["url"] = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    else:
        result["params"] = None

    print(json.dumps(result, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
