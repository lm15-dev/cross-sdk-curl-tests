#!/usr/bin/env python3
"""
Generate test_cases.json from curl-fixtures.

For each lm15-scope fixture, reverse-maps the wire-format body back to
logical inputs (model, prompt, messages, system, tools, provider passthrough).

Usage:
    python3 cross-sdk-curl-tests/generate_test_cases.py
    python3 cross-sdk-curl-tests/generate_test_cases.py --dry-run  # print without writing
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

# ── Known fields per provider that map to native lm15 kwargs ──────────────

# These are extracted from the body and mapped to test case fields.
# Everything else goes to "provider" passthrough.

OPENAI_NATIVE = {"model", "input", "stream", "instructions", "temperature",
                  "max_output_tokens", "tools"}
ANTHROPIC_NATIVE = {"model", "messages", "stream", "system", "temperature",
                     "max_tokens", "tools"}
GEMINI_NATIVE = {"contents", "systemInstruction", "tools"}


def extract_openai(fixture):
    """Reverse-map an OpenAI Responses API body to logical inputs."""
    body = fixture["request"]["body"]
    case = {"model": body["model"]}

    # Extract messages from input
    inp = body.get("input", [])
    messages = extract_openai_messages(inp)

    if len(messages) == 1 and messages[0]["role"] == "user" and "text" in messages[0]:
        # Single user message → use prompt shorthand
        case["prompt"] = messages[0]["text"]
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

    # Tools
    tools = body.get("tools", [])
    function_tools = [t for t in tools if t.get("type") == "function"]
    if function_tools:
        case["tools"] = [
            {
                "name": t["name"],
                "description": t.get("description"),
                "parameters": t.get("parameters", {"type": "object", "properties": {}}),
            }
            for t in function_tools
        ]

    # Everything else → provider passthrough
    passthrough = {k: v for k, v in body.items() if k not in OPENAI_NATIVE}
    if passthrough:
        case["provider"] = passthrough

    return case


def extract_openai_messages(inp):
    """Extract messages from OpenAI input array."""
    messages = []
    for item in inp:
        role = item.get("role")
        if role in ("user", "assistant"):
            content = item.get("content")
            if isinstance(content, str):
                messages.append({"role": role, "text": content})
            elif isinstance(content, list):
                # Check if it's just a single text part
                text_parts = [c for c in content if c.get("type") in ("input_text", "text")]
                non_text = [c for c in content if c.get("type") not in ("input_text", "text")]
                if len(text_parts) == 1 and not non_text:
                    messages.append({"role": role, "text": text_parts[0]["text"]})
                else:
                    messages.append({"role": role, "content": content})
        elif item.get("type") in ("function_call", "function_call_output"):
            messages.append(item)
    return messages


def extract_anthropic(fixture):
    """Reverse-map an Anthropic Messages API body to logical inputs."""
    body = fixture["request"]["body"]
    case = {"model": body["model"]}

    msgs = body.get("messages", [])
    messages = extract_anthropic_messages(msgs)

    if len(messages) == 1 and messages[0]["role"] == "user" and "text" in messages[0]:
        case["prompt"] = messages[0]["text"]
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

    # Tools
    tools = body.get("tools", [])
    if tools:
        case["tools"] = [
            {
                "name": t["name"],
                "description": t.get("description"),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            }
            for t in tools
        ]

    # Everything else → provider passthrough
    passthrough = {k: v for k, v in body.items() if k not in ANTHROPIC_NATIVE}
    if passthrough:
        case["provider"] = passthrough

    return case


def extract_anthropic_messages(msgs):
    """Extract messages from Anthropic messages array."""
    messages = []
    for m in msgs:
        role = m["role"]
        content = m.get("content")
        if isinstance(content, str):
            messages.append({"role": role, "text": content})
        elif isinstance(content, list):
            text_parts = [c for c in content if c.get("type") == "text"]
            non_text = [c for c in content if c.get("type") != "text"]
            if len(text_parts) == 1 and not non_text:
                messages.append({"role": role, "text": text_parts[0]["text"]})
            else:
                messages.append({"role": role, "content": content})
    return messages


def extract_gemini(fixture):
    """Reverse-map a Gemini API body to logical inputs."""
    body = fixture["request"]["body"]
    case = {"model": fixture["id"].split(".")[0]}  # gemini model is in the URL, not body

    # Extract model from fixture URL
    url = fixture["request"]["url"]
    # URL like: .../models/gemini-2.5-flash:generateContent
    if "/models/" in url:
        model_part = url.split("/models/")[1].split(":")[0]
        case["model"] = model_part

    contents = body.get("contents", [])
    messages = extract_gemini_messages(contents)

    if len(messages) == 1 and messages[0]["role"] == "user" and "text" in messages[0]:
        case["prompt"] = messages[0]["text"]
    else:
        case["messages"] = messages

    # System instruction
    sys_inst = body.get("systemInstruction")
    if sys_inst:
        parts = sys_inst.get("parts", [])
        if len(parts) == 1:
            case["system"] = parts[0].get("text", "")

    # Streaming — determined by URL, not body
    if "streamGenerateContent" in url:
        case["stream"] = True

    # Tools
    tools_arr = body.get("tools", [])
    if tools_arr:
        func_decls = []
        for t in tools_arr:
            for fd in t.get("functionDeclarations", []):
                func_decls.append({
                    "name": fd["name"],
                    "description": fd.get("description"),
                    "parameters": fd.get("parameters", {"type": "object", "properties": {}}),
                })
        if func_decls:
            case["tools"] = func_decls

    # generationConfig → extract native fields, rest to passthrough
    gen_cfg = body.get("generationConfig", {})
    remaining_gen_cfg = {}
    if "maxOutputTokens" in gen_cfg:
        case["max_tokens"] = gen_cfg["maxOutputTokens"]
    else:
        remaining_gen_cfg.update({k: v for k, v in gen_cfg.items() if k == "maxOutputTokens"})

    if "stopSequences" in gen_cfg:
        case["stop"] = gen_cfg["stopSequences"]

    # Everything else in generationConfig → provider passthrough
    for k, v in gen_cfg.items():
        if k not in ("maxOutputTokens", "stopSequences"):
            remaining_gen_cfg[k] = v

    # Non-native top-level fields → provider passthrough
    passthrough = {}
    for k, v in body.items():
        if k not in GEMINI_NATIVE and k != "generationConfig":
            passthrough[k] = v

    if remaining_gen_cfg:
        passthrough["generationConfig"] = remaining_gen_cfg

    if passthrough:
        case["provider"] = passthrough

    return case


def extract_gemini_messages(contents):
    """Extract messages from Gemini contents array."""
    messages = []
    for c in contents:
        role = "assistant" if c.get("role") == "model" else c.get("role", "user")
        parts = c.get("parts", [])
        if len(parts) == 1 and "text" in parts[0]:
            messages.append({"role": role, "text": parts[0]["text"]})
        else:
            messages.append({"role": role, "parts": parts})
    return messages


def generate():
    with open(FIXTURES_DIR / "features.yaml") as f:
        features = yaml.safe_load(f)

    fixtures = {}
    for f in sorted((FIXTURES_DIR / "cases").rglob("*.json")):
        data = json.loads(f.read_text())
        fixtures[data["id"]] = data

    cases = []
    for provider in ["openai", "anthropic", "gemini"]:
        for fname, finfo in features[provider]["features"].items():
            if finfo.get("scope") != "lm15":
                continue
            fid = f"{provider}.{fname}"
            fixture = fixtures.get(fid)
            if not fixture:
                continue

            try:
                if provider == "openai":
                    case = extract_openai(fixture)
                elif provider == "anthropic":
                    case = extract_anthropic(fixture)
                elif provider == "gemini":
                    case = extract_gemini(fixture)
                else:
                    continue

                case["id"] = fid
                # Move id to front
                case = {"id": case.pop("id"), **case}
                cases.append(case)
            except Exception as e:
                print(f"  ⚠️  {fid}: {e}", file=sys.stderr)

    output = {
        "description": "Cross-SDK curl test cases — auto-generated from curl-fixtures. "
                       "Each case defines logical inputs that all SDKs should produce "
                       "identical HTTP request bodies for. "
                       "Regenerate with: python3 cross-sdk-curl-tests/generate_test_cases.py",
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
