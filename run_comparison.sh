#!/usr/bin/env bash
# Cross-SDK HTTP request comparison.
#
# Runs each test case through Python, TypeScript, Go, Rust, and Julia SDKs,
# dumps the HTTP request each would send, and diffs them.
#
# Prerequisites:
#   - Python 3.10+ with lm15-python on sys.path
#   - Node 18+ with lm15-ts built (npm run build)
#   - Go with lm15-go
#   - Rust with lm15-rs
#   - Julia with lm15-jl
#   - .env file with at least one provider key (or set LM15_ENV)
#
# Usage:
#   bash cross-sdk-curl-tests/run_comparison.sh
#   bash cross-sdk-curl-tests/run_comparison.sh --curl  # also print curl commands
#   bash cross-sdk-curl-tests/run_comparison.sh --live  # actually run the curls

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CASES_FILE="$SCRIPT_DIR/test_cases.json"
OUTPUT_DIR="$SCRIPT_DIR/output"
SHOW_CURL=false
RUN_LIVE=false

for arg in "$@"; do
    case "$arg" in
        --curl) SHOW_CURL=true ;;
        --live) RUN_LIVE=true ;;
    esac
done

mkdir -p "$OUTPUT_DIR"

# Count cases
CASE_COUNT=$(python3 -c "import json; print(len(json.load(open('$CASES_FILE'))['cases']))")
echo "=== Cross-SDK HTTP Request Comparison ==="
echo "Cases: $CASE_COUNT"
echo ""

PASS=0
FAIL=0
SKIP=0

for i in $(seq 0 $((CASE_COUNT - 1))); do
    CASE_JSON=$(python3 -c "
import json
cases = json.load(open('$CASES_FILE'))['cases']
print(json.dumps(cases[$i]))
")
    CASE_ID=$(echo "$CASE_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

    echo "--- $CASE_ID ---"

    # Python
    PY_OUT="$OUTPUT_DIR/${CASE_ID}.py.json"
    if python3 "$SCRIPT_DIR/dump_request.py" "$CASE_JSON" > "$PY_OUT" 2>/dev/null; then
        echo "  ✅ Python"
    else
        echo "  ❌ Python (failed)"
        SKIP=$((SKIP + 1))
        continue
    fi

    # TypeScript
    TS_OUT="$OUTPUT_DIR/${CASE_ID}.ts.json"
    if [ ! -f "$ROOT/lm15-ts/dist/curl.js" ]; then
        (cd "$ROOT/lm15-ts" && npm run build >/dev/null 2>&1) || true
    fi
    if node "$SCRIPT_DIR/dump_request.mjs" "$CASE_JSON" > "$TS_OUT" 2>/dev/null; then
        echo "  ✅ TypeScript"
    else
        echo "  ⚠️  TypeScript (skipped)"
        TS_OUT=""
    fi

    # Go
    GO_OUT="$OUTPUT_DIR/${CASE_ID}.go.json"
    GO_BIN="$OUTPUT_DIR/dump_request_go"
    if (cd "$ROOT/lm15-go" && go build -o "$GO_BIN" ../cross-sdk-curl-tests/dump_request.go) 2>/dev/null; then
        true
    else
        GO_BIN=""
    fi
    if [ -n "$GO_BIN" ] && "$GO_BIN" "$CASE_JSON" > "$GO_OUT" 2>/dev/null; then
        echo "  ✅ Go"
    else
        echo "  ⚠️  Go (skipped)"
        GO_OUT=""
    fi

    # Rust
    RS_OUT="$OUTPUT_DIR/${CASE_ID}.rs.json"
    RS_BIN="$ROOT/lm15-rs/target/debug/dump_request"
    if [ ! -x "$RS_BIN" ]; then
        if (cd "$ROOT/lm15-rs" && cargo build --quiet --bin dump_request) 2>/dev/null; then
            true
        else
            RS_BIN=""
        fi
    fi
    if [ -n "$RS_BIN" ] && "$RS_BIN" "$CASE_JSON" > "$RS_OUT" 2>/dev/null; then
        echo "  ✅ Rust"
    else
        echo "  ⚠️  Rust (skipped)"
        RS_OUT=""
    fi

    # Julia
    JL_OUT="$OUTPUT_DIR/${CASE_ID}.jl.json"
    if julia --project="$ROOT/lm15-jl" "$SCRIPT_DIR/dump_request.jl" "$CASE_JSON" > "$JL_OUT" 2>/dev/null; then
        echo "  ✅ Julia"
    else
        echo "  ⚠️  Julia (skipped)"
        JL_OUT=""
    fi

    # Compare: normalize both by sorting keys and stripping auth
    MATCH=true

    if [ -n "$TS_OUT" ] && [ -f "$TS_OUT" ]; then
        # Compare Python vs TypeScript (body only — URLs and header names may differ in case)
        PY_BODY=$(python3 -c "import json,sys; d=json.load(open('$PY_OUT')); print(json.dumps(d.get('body'), sort_keys=True))")
        TS_BODY=$(python3 -c "import json,sys; d=json.load(open('$TS_OUT')); print(json.dumps(d.get('body'), sort_keys=True))")
        if [ "$PY_BODY" = "$TS_BODY" ]; then
            echo "  ✅ Python ≡ TypeScript (body match)"
        else
            echo "  ❌ Python ≠ TypeScript (body differs)"
            diff <(echo "$PY_BODY" | python3 -m json.tool) <(echo "$TS_BODY" | python3 -m json.tool) || true
            MATCH=false
        fi
    fi

    if [ -n "$GO_OUT" ] && [ -f "$GO_OUT" ]; then
        PY_BODY=$(python3 -c "import json; d=json.load(open('$PY_OUT')); print(json.dumps(d.get('body'), sort_keys=True))")
        GO_BODY=$(python3 -c "import json; d=json.load(open('$GO_OUT')); print(json.dumps(d.get('body'), sort_keys=True))")
        if [ "$PY_BODY" = "$GO_BODY" ]; then
            echo "  ✅ Python ≡ Go (body match)"
        else
            echo "  ❌ Python ≠ Go (body differs)"
            diff <(echo "$PY_BODY" | python3 -m json.tool) <(echo "$GO_BODY" | python3 -m json.tool) || true
            MATCH=false
        fi
    fi

    if [ -n "$RS_OUT" ] && [ -f "$RS_OUT" ]; then
        PY_BODY=$(python3 -c "import json; d=json.load(open('$PY_OUT')); print(json.dumps(d.get('body'), sort_keys=True))")
        RS_BODY=$(python3 -c "import json; d=json.load(open('$RS_OUT')); print(json.dumps(d.get('body'), sort_keys=True))")
        if [ "$PY_BODY" = "$RS_BODY" ]; then
            echo "  ✅ Python ≡ Rust (body match)"
        else
            echo "  ❌ Python ≠ Rust (body differs)"
            diff <(echo "$PY_BODY" | python3 -m json.tool) <(echo "$RS_BODY" | python3 -m json.tool) || true
            MATCH=false
        fi
    fi

    if [ -n "$JL_OUT" ] && [ -f "$JL_OUT" ]; then
        PY_BODY=$(python3 -c "import json; d=json.load(open('$PY_OUT')); print(json.dumps(d.get('body'), sort_keys=True))")
        JL_BODY=$(python3 -c "import json; d=json.load(open('$JL_OUT')); print(json.dumps(d.get('body'), sort_keys=True))")
        if [ "$PY_BODY" = "$JL_BODY" ]; then
            echo "  ✅ Python ≡ Julia (body match)"
        else
            echo "  ❌ Python ≠ Julia (body differs)"
            diff <(echo "$PY_BODY" | python3 -m json.tool) <(echo "$JL_BODY" | python3 -m json.tool) || true
            MATCH=false
        fi
    fi

    if $MATCH; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
    fi

    # Optionally show curl
    if $SHOW_CURL; then
        echo ""
        echo "  curl command (from Python):"
        python3 -c "
import sys, os, json
sys.path.insert(0, os.path.join('$ROOT', 'lm15-python'))
from lm15.curl import dump_curl
case = json.loads('$CASE_JSON')
kwargs = {}
if 'system' in case: kwargs['system'] = case['system']
if 'temperature' in case: kwargs['temperature'] = case['temperature']
if 'max_tokens' in case: kwargs['max_tokens'] = case['max_tokens']
if 'stream' in case: kwargs['stream'] = case['stream']
if case.get('tools'):
    from lm15.types import FunctionTool
    kwargs['tools'] = [FunctionTool(name=t['name'], description=t.get('description'), parameters=t.get('parameters')) for t in case['tools']]
print(dump_curl(case['model'], case['prompt'], env=os.environ.get('LM15_ENV', '.env'), redact_auth=True, **kwargs))
" 2>/dev/null || echo "  (curl generation failed)"
        echo ""
    fi

    # Optionally run live
    if $RUN_LIVE; then
        echo "  Running curl..."
        python3 -c "
import sys, os, json
sys.path.insert(0, os.path.join('$ROOT', 'lm15-python'))
from lm15.curl import dump_curl
case = json.loads('$CASE_JSON')
kwargs = {}
if 'system' in case: kwargs['system'] = case['system']
if 'temperature' in case: kwargs['temperature'] = case['temperature']
if 'max_tokens' in case: kwargs['max_tokens'] = case['max_tokens']
if case.get('tools'):
    from lm15.types import FunctionTool
    kwargs['tools'] = [FunctionTool(name=t['name'], description=t.get('description'), parameters=t.get('parameters')) for t in case['tools']]
print(dump_curl(case['model'], case['prompt'], env=os.environ.get('LM15_ENV', '.env'), redact_auth=False, **kwargs))
" 2>/dev/null | bash -s 2>&1 | head -20
        echo ""
    fi

    echo ""
done

echo "=== Summary ==="
echo "Pass: $PASS"
echo "Fail: $FAIL"
echo "Skip: $SKIP"

if [ $FAIL -gt 0 ]; then
    exit 1
fi
