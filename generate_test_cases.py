#!/usr/bin/env python3
"""
Generate test_cases.json from curl-fixtures.

For each lm15-scope fixture, reverse-maps the wire-format body back to
logical inputs using the canonical lm15 message format.

Usage:
    python3 cross-sdk-curl-tests/generate_test_cases.py
    python3 cross-sdk-curl-tests/generate_test_cases.py --dry-run
"""

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("pip install pyyaml", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).parent.parent
FIXTURES_DIR = ROOT / "curl-fixtures"
OUTPUT = Path(__file__).parent / "test_cases.json"
DRY_RUN = "--dry-run" in sys.argv

PROVIDERS = ["openai", "anthropic", "gemini"]

# Fields handled natively (not sent to provider passthrough)
OPENAI_NATIVE = {"model", "input", "stream", "instructions", "temperature",
                  "max_output_tokens", "tools"}
ANTHROPIC_NATIVE = {"model", "messages", "stream", "system", "temperature",
                     "max_tokens", "tools"}
GEMINI_NATIVE = {"contents", "systemInstruction", "tools"}


# ── OpenAI ────────────────────────────────────────────────────────────────

def openai_input_to_canonical(inp: list) -> list[dict]:
    """Convert OpenAI input array to canonical lm15 messages."""
    messages = []
    for item in inp:
        role = item.get("role")
        if role in ("user", "assistant"):
            content = item.get("content")
            if isinstance(content, str):
                messages.append({"role": role, "parts": [{"type": "text", "text": content}]})
            elif isinstance(content, list):
                parts = []
                for c in content:
                    ct = c.get("type", "")
                    if ct in ("input_text", "text"):
                        parts.append({"type": "text", "text": c["text"]})
                    elif ct == "input_image":
                        part = {"type": "image", "source": {}}
                        if "image_url" in c:
                            url = c["image_url"]
                            if url.startswith("data:"):
                                # data URI → base64
                                header, data = url.split(",", 1)
                                media_type = header.split(":")[1].split(";")[0]
                                part["source"] = {"type": "base64", "data": data, "media_type": media_type}
                            else:
                                part["source"] = {"type": "url", "url": url, "media_type": "image/png"}
                        if c.get("detail"):
                            part["source"]["detail"] = c["detail"]
                        parts.append(part)
                    else:
                        parts.append({"type": "text", "text": json.dumps(c)})
                messages.append({"role": role, "parts": parts})
        elif item.get("type") == "function_call":
            args = item.get("arguments", "{}")
            if isinstance(args, str):
                args = json.loads(args)
            messages.append({
                "role": "assistant",
                "parts": [{
                    "type": "tool_call",
                    "id": item["call_id"],
                    "name": item["name"],
                    "arguments": args,
                }]
            })
        elif item.get("type") == "function_call_output":
            messages.append({
                "role": "tool",
                "parts": [{
                    "type": "tool_result",
                    "id": item["call_id"],
                    "content": item.get("output", ""),
                }]
            })
    return messages


def extract_openai(fixture: dict) -> dict:
    body = fixture["request"]["body"]
    case: dict = {"model": body["model"]}

    inp = body.get("input", [])
    messages = openai_input_to_canonical(inp)

    if len(messages) == 1 and messages[0]["role"] == "user" and len(messages[0]["parts"]) == 1 and messages[0]["parts"][0]["type"] == "text":
        case["prompt"] = messages[0]["parts"][0]["text"]
    else:
        case["messages"] = messages

    if body.get("instructions"):
        case["system"] = body["instructions"]
    if body.get("stream"):
        case["stream"] = True
    if body.get("temperature") is not None:
        case["temperature"] = body["temperature"]
    if body.get("max_output_tokens") is not None:
        case["max_tokens"] = body["max_output_tokens"]

    tools = [t for t in body.get("tools", []) if t.get("type") == "function"]
    if tools:
        case["tools"] = [{"name": t["name"], "description": t.get("description"),
                          "parameters": t.get("parameters", {"type": "object", "properties": {}})}
                         for t in tools]

    passthrough = {k: v for k, v in body.items() if k not in OPENAI_NATIVE}
    if passthrough:
        case["provider"] = passthrough
    return case


# ── Anthropic ─────────────────────────────────────────────────────────────

def anthropic_messages_to_canonical(msgs: list) -> list[dict]:
    """Convert Anthropic messages to canonical lm15 messages."""
    messages = []
    for m in msgs:
        role = m["role"]
        content = m.get("content")
        if isinstance(content, str):
            messages.append({"role": role, "parts": [{"type": "text", "text": content}]})
        elif isinstance(content, list):
            parts = []
            for c in content:
                ct = c.get("type", "")
                if ct == "text":
                    parts.append({"type": "text", "text": c["text"]})
                elif ct == "image":
                    src = c.get("source", {})
                    part = {"type": "image", "source": {
                        "type": src.get("type", "url"),
                        "media_type": src.get("media_type", "image/png"),
                    }}
                    if src.get("url"):
                        part["source"]["url"] = src["url"]
                    if src.get("data"):
                        part["source"]["data"] = src["data"]
                    parts.append(part)
                elif ct == "tool_use":
                    parts.append({
                        "type": "tool_call",
                        "id": c["id"],
                        "name": c["name"],
                        "arguments": c.get("input", {}),
                    })
                elif ct == "tool_result":
                    parts.append({
                        "type": "tool_result",
                        "id": c["tool_use_id"],
                        "content": c.get("content", ""),
                    })
                else:
                    parts.append({"type": "text", "text": json.dumps(c)})

            # Remap role: if all parts are tool_result, use role "tool"
            if all(p["type"] == "tool_result" for p in parts):
                role = "tool"
            messages.append({"role": role, "parts": parts})
    return messages


def extract_anthropic(fixture: dict) -> dict:
    body = fixture["request"]["body"]
    case: dict = {"model": body["model"]}

    msgs = body.get("messages", [])
    messages = anthropic_messages_to_canonical(msgs)

    if len(messages) == 1 and messages[0]["role"] == "user" and len(messages[0]["parts"]) == 1 and messages[0]["parts"][0]["type"] == "text":
        case["prompt"] = messages[0]["parts"][0]["text"]
    else:
        case["messages"] = messages

    if body.get("system"):
        case["system"] = body["system"]
    if body.get("max_tokens") is not None:
        case["max_tokens"] = body["max_tokens"]
    if body.get("temperature") is not None:
        case["temperature"] = body["temperature"]
    if body.get("stream"):
        case["stream"] = True

    tools = body.get("tools", [])
    if tools:
        case["tools"] = [{"name": t["name"], "description": t.get("description"),
                          "parameters": t.get("input_schema", {"type": "object", "properties": {}})}
                         for t in tools]

    passthrough = {k: v for k, v in body.items() if k not in ANTHROPIC_NATIVE}
    if passthrough:
        case["provider"] = passthrough
    return case


# ── Gemini ────────────────────────────────────────────────────────────────

def gemini_contents_to_canonical(contents: list) -> list[dict]:
    """Convert Gemini contents to canonical lm15 messages."""
    messages = []
    for c in contents:
        role = "assistant" if c.get("role") == "model" else c.get("role", "user")
        raw_parts = c.get("parts", [])
        parts = []
        for p in raw_parts:
            if "text" in p:
                parts.append({"type": "text", "text": p["text"]})
            elif "inlineData" in p or "inline_data" in p:
                d = p.get("inlineData") or p["inline_data"]
                parts.append({"type": "image", "source": {
                    "type": "base64",
                    "data": d["data"],
                    "media_type": d.get("mime_type", "image/png"),
                }})
            elif "functionCall" in p:
                fc = p["functionCall"]
                parts.append({
                    "type": "tool_call",
                    "id": fc.get("id", ""),
                    "name": fc["name"],
                    "arguments": fc.get("args", {}),
                })
            elif "functionResponse" in p:
                fr = p["functionResponse"]
                # Extract the result text from the response object
                resp = fr.get("response", {})
                result_val = resp.get("result", "")
                if isinstance(result_val, dict):
                    result_text = json.dumps(result_val)
                else:
                    result_text = str(result_val)
                part_d: dict = {
                    "type": "tool_result",
                    "id": fr.get("id", ""),
                    "content": result_text,
                }
                if fr.get("name"):
                    part_d["name"] = fr["name"]
                parts.append(part_d)
            else:
                parts.append({"type": "text", "text": json.dumps(p)})

        # Remap: tool_result parts from gemini come as "user" role, should be "tool"
        if all(p["type"] == "tool_result" for p in parts):
            role = "tool"
        messages.append({"role": role, "parts": parts})
    return messages


def extract_gemini(fixture: dict) -> dict:
    body = fixture["request"]["body"]
    url = fixture["request"]["url"]

    case: dict = {}
    if "/models/" in url:
        case["model"] = url.split("/models/")[1].split(":")[0]

    contents = body.get("contents", [])
    messages = gemini_contents_to_canonical(contents)

    if len(messages) == 1 and messages[0]["role"] == "user" and len(messages[0]["parts"]) == 1 and messages[0]["parts"][0]["type"] == "text":
        case["prompt"] = messages[0]["parts"][0]["text"]
    else:
        case["messages"] = messages

    sys_inst = body.get("systemInstruction")
    if sys_inst:
        parts = sys_inst.get("parts", [])
        if len(parts) == 1:
            case["system"] = parts[0].get("text", "")

    if "streamGenerateContent" in url:
        case["stream"] = True

    tools_arr = body.get("tools", [])
    func_decls = []
    for t in tools_arr:
        for fd in t.get("functionDeclarations", []):
            func_decls.append({"name": fd["name"], "description": fd.get("description"),
                               "parameters": fd.get("parameters", {"type": "object", "properties": {}})})
    if func_decls:
        case["tools"] = func_decls

    gen_cfg = body.get("generationConfig", {})
    if "maxOutputTokens" in gen_cfg:
        case["max_tokens"] = gen_cfg["maxOutputTokens"]
    if "stopSequences" in gen_cfg:
        case["stop"] = gen_cfg["stopSequences"]

    remaining_gen_cfg = {k: v for k, v in gen_cfg.items() if k not in ("maxOutputTokens", "stopSequences")}
    passthrough: dict = {}
    for k, v in body.items():
        if k not in GEMINI_NATIVE and k != "generationConfig":
            passthrough[k] = v
    if remaining_gen_cfg:
        passthrough["generationConfig"] = remaining_gen_cfg
    if passthrough:
        case["provider"] = passthrough
    return case


# ── Main ──────────────────────────────────────────────────────────────────

EXTRACTORS = {"openai": extract_openai, "anthropic": extract_anthropic, "gemini": extract_gemini}


def generate():
    with open(FIXTURES_DIR / "features.yaml") as f:
        features = yaml.safe_load(f)

    fixtures = {}
    for fp in sorted((FIXTURES_DIR / "cases").rglob("*.json")):
        data = json.loads(fp.read_text())
        fixtures[data["id"]] = data

    cases = []
    for provider in PROVIDERS:
        for fname, finfo in features[provider]["features"].items():
            if finfo.get("scope") != "lm15":
                continue
            fid = f"{provider}.{fname}"
            fixture = fixtures.get(fid)
            if not fixture:
                continue
            try:
                case = EXTRACTORS[provider](fixture)
                case = {"id": fid, **case}
                cases.append(case)
            except Exception as e:
                print(f"  ⚠️  {fid}: {e}", file=sys.stderr)

    output = {
        "description": "Cross-SDK curl test cases — auto-generated from curl-fixtures. "
                       "Uses the canonical lm15 message format for the 'messages' field. "
                       "Regenerate: python3 cross-sdk-curl-tests/generate_test_cases.py",
        "cases": cases,
    }

    text = json.dumps(output, indent=2, ensure_ascii=False) + "\n"
    if DRY_RUN:
        print(text)
    else:
        OUTPUT.write_text(text)
        print(f"Written {len(cases)} cases to {OUTPUT}")
    return cases


if __name__ == "__main__":
    generate()
