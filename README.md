# Cross-SDK Curl Tests

Verify that all five lm15 implementations (Python, TypeScript, Go, Rust, Julia) produce the **same HTTP request body** for identical logical calls.

## How it works

1. **Test cases** are defined in `test_cases.json` — each is a model + prompt + config
2. Each SDK has a `dump_request` script that builds the provider-level HTTP request *without sending it*
3. The runner compares the JSON bodies across SDKs and reports mismatches

## Quick start

```bash
# From the repo root
bash cross-sdk-curl-tests/run_comparison.sh
```

## Options

```bash
# Show the curl command for each test case
bash cross-sdk-curl-tests/run_comparison.sh --curl

# Actually execute the curls against live APIs (requires API keys)
bash cross-sdk-curl-tests/run_comparison.sh --live
```

## Using from each SDK

### Python

```python
from lm15.curl import dump_curl, dump_http

# Get a curl command
print(dump_curl("gpt-4.1-mini", "Hello.", env=".env"))

# Get the structured HTTP request (for programmatic comparison)
import json
print(json.dumps(dump_http("gpt-4.1-mini", "Hello.", env=".env"), indent=2))
```

### TypeScript

```typescript
import { dumpCurl, dumpHttp } from "lm15";

console.log(dumpCurl("gpt-4.1-mini", "Hello."));
console.log(JSON.stringify(dumpHttp("gpt-4.1-mini", "Hello."), null, 2));
```

### Go

```go
curl, _ := lm15.DumpCurl("gpt-4.1-mini", "Hello.", nil)
fmt.Println(curl)

dict, _ := lm15.DumpHTTP("gpt-4.1-mini", "Hello.", nil)
out, _ := json.MarshalIndent(dict, "", "  ")
fmt.Println(string(out))
```

### Rust

```rust
use lm15::{dump_curl, dump_http, CurlOptions};

let opts = CurlOptions {
    env: Some(".env".into()),
    ..Default::default()
};

println!("{}", dump_curl("gpt-4.1-mini", Some("Hello."), Some(&opts)).unwrap());
println!("{}", serde_json::to_string_pretty(
    &dump_http("gpt-4.1-mini", Some("Hello."), Some(&opts)).unwrap()
).unwrap());
```

### Julia

```julia
using LM15

println(dump_curl("gpt-4.1-mini", "Hello.", env=".env"))
println(LM15.JSON.serialize(dump_http("gpt-4.1-mini", "Hello.", env=".env")))
```

## What gets compared

The comparison focuses on the **request body** (the JSON payload sent to the provider). This is where semantic differences would matter — different field names, missing parameters, different tool encoding, etc.

Headers and URLs are checked for structural similarity but not exact match (header casing, auth redaction, etc.).

## Adding test cases

Add entries to `test_cases.json`. The format:

```json
{
  "id": "provider.description",
  "model": "model-name",
  "prompt": "The user prompt",
  "system": "Optional system prompt",
  "temperature": 0.7,
  "max_tokens": 100,
  "stream": true,
  "tools": [
    {
      "name": "tool_name",
      "description": "Tool description",
      "parameters": { "type": "object", "properties": { ... } }
    }
  ]
}
```

## What this catches

- Field name mismatches between SDKs (e.g., `max_tokens` vs `maxTokens` in the wire format)
- Missing parameters (one SDK sends `temperature`, another doesn't)
- Different tool encoding (schema format differences)
- System prompt placement differences (message vs top-level field)
- Streaming flag differences
