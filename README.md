# Cross-SDK Curl Tests

Verify that all five lm15 implementations (Python, TypeScript, Go, Rust, Julia) produce the **same HTTP request body** for identical logical calls, validated against live-tested curl fixtures.

## How it works

1. **Curl fixtures** in `../curl-fixtures/cases/` define the ground truth — correct HTTP request bodies, live-tested against real APIs
2. **Test cases** are auto-generated from those fixtures by `generate_test_cases.py`, using the canonical lm15 message format
3. Each SDK has a `dump_request` script that builds the provider-level HTTP request *without sending it*
4. The **coverage report** (`../curl-fixtures/coverage_report.py`) compares SDK outputs against fixture bodies and reports matches/gaps

## Quick start

```bash
# From the repo root

# 1. Generate test cases from curl fixtures
python3 cross-sdk-curl-tests/generate_test_cases.py

# 2. Run all SDKs and generate the coverage report
#    (runs each dump_request script, saves outputs, compares to fixtures)
python3 curl-fixtures/coverage_report.py --json

# 3. Or run the legacy comparison script
bash cross-sdk-curl-tests/run_comparison.sh
```

## Test case format

Test cases use the **canonical lm15 message format**. They're auto-generated — don't edit `test_cases.json` by hand. Instead, edit the fixture in `../curl-fixtures/cases/` and regenerate:

```bash
python3 cross-sdk-curl-tests/generate_test_cases.py
```

### Simple case (prompt shorthand)

```json
{
  "id": "openai.basic_text",
  "model": "gpt-4.1-mini",
  "prompt": "Say hello."
}
```

### With config parameters

```json
{
  "id": "openai.temperature",
  "model": "gpt-4.1-mini",
  "prompt": "Write a haiku.",
  "temperature": 0.7,
  "max_tokens": 50
}
```

### Multi-turn conversation (canonical message format)

```json
{
  "id": "openai.multi_turn",
  "model": "gpt-4.1-mini",
  "messages": [
    {"role": "user", "parts": [{"type": "text", "text": "What is 2 + 2?"}]},
    {"role": "assistant", "parts": [{"type": "text", "text": "four"}]},
    {"role": "user", "parts": [{"type": "text", "text": "Repeat in uppercase."}]}
  ]
}
```

### Tool calls and results

```json
{
  "id": "anthropic.multi_turn_tool_result",
  "model": "claude-sonnet-4-5",
  "messages": [
    {"role": "user", "parts": [{"type": "text", "text": "What is 2 + 2?"}]},
    {"role": "assistant", "parts": [{"type": "tool_call", "id": "call_1", "name": "calc", "arguments": {"expr": "2+2"}}]},
    {"role": "tool", "parts": [{"type": "tool_result", "id": "call_1", "content": "4"}]}
  ],
  "tools": [{"name": "calc", "description": "Calculate", "parameters": {"type": "object", "properties": {"expr": {"type": "string"}}}}]
}
```

### Image input

```json
{
  "id": "openai.image_url",
  "model": "gpt-4.1-mini",
  "messages": [
    {"role": "user", "parts": [
      {"type": "text", "text": "Describe this image."},
      {"type": "image", "source": {"type": "url", "url": "https://example.com/img.png", "media_type": "image/png", "detail": "low"}}
    ]}
  ]
}
```

### Provider passthrough

Fields not natively abstracted by lm15 (tool_choice, structured output, thinking config, etc.) are passed through via the `provider` field, which gets merged into the request body:

```json
{
  "id": "openai.tool_choice_auto",
  "model": "gpt-4.1-mini",
  "prompt": "What is the weather?",
  "tools": [{"name": "get_weather", "description": "Get weather", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}}],
  "provider": {"tool_choice": "auto"}
}
```

## Canonical message format

All 5 SDKs implement `messages_from_json` / `messages_to_json` for the canonical format. Part types:

| Part type | Fields | Description |
|---|---|---|
| `text` | `text` | Plain text |
| `image` | `source: {type, url\|data, media_type, detail}` | Image (URL or base64) |
| `audio` | `source: {type, url\|data, media_type}` | Audio |
| `video` | `source: {type, url\|data, media_type}` | Video |
| `document` | `source: {type, url\|data, media_type}` | Document/PDF |
| `tool_call` | `id, name, arguments` | Assistant requests a tool call |
| `tool_result` | `id, content, name?, is_error?` | Tool execution result |
| `thinking` | `text, redacted?, summary?` | Model reasoning trace |

## File structure

```
cross-sdk-curl-tests/
├── generate_test_cases.py   # Generates test_cases.json from curl fixtures
├── test_cases.json          # Auto-generated — don't edit by hand
├── dump_request.py          # Python: test case → HTTP request
├── dump_request.mjs         # TypeScript: test case → HTTP request
├── dump_request.go          # Go: test case → HTTP request (build with go build)
├── dump_request.jl          # Julia: test case → HTTP request
├── run_comparison.sh        # Legacy runner (compares SDKs to each other)
└── output/                  # Generated SDK outputs (gitignored)
    ├── openai.basic_text.py.json
    ├── openai.basic_text.ts.json
    └── ...
```

## Coverage report

The coverage report lives in `../curl-fixtures/` and joins everything together:

```bash
python3 curl-fixtures/coverage_report.py          # markdown report
python3 curl-fixtures/coverage_report.py --json    # + machine-readable
python3 curl-fixtures/coverage_report.py --strict   # exit 1 if gaps exist
```

It shows, for each provider feature:
- Whether a curl fixture exists
- Whether it passes live testing
- Whether it's in lm15 scope or provider-only
- Whether each of the 5 SDKs produces a matching request body

## What this catches

- Field name mismatches between SDKs (e.g., `max_tokens` vs `maxTokens` in the wire format)
- Missing parameters (one SDK sends `temperature`, another doesn't)
- Different tool encoding (schema format, `tool_use` vs `function_call`)
- System prompt placement differences (message vs top-level field)
- Multi-turn message serialization differences
- Image/media part encoding differences
- Provider API drift (fixture live tests fail → update fixture → SDK tests fail → fix SDKs)

## What it does NOT test

- Response parsing (only request building is tested)
- Streaming SSE behavior (only that `stream: true` is set)
- Error handling
- Features marked `scope: provider` in `features.yaml` (42 provider-only features)
