#!/usr/bin/env node
/**
 * Dump the HTTP request for a given test case as JSON.
 */

import { dumpHttp } from "../lm15-ts/dist/curl.js";

const caseJson = process.argv[2];
if (!caseJson) {
  console.error("usage: dump_request.mjs <test-case-json>");
  process.exit(1);
}

const testCase = JSON.parse(caseJson);

const tools = testCase.tools?.map(t => ({
  type: "function",
  name: t.name,
  description: t.description,
  parameters: t.parameters ?? { type: "object", properties: {} },
}));

const result = dumpHttp(testCase.model, testCase.prompt, {
  system: testCase.system,
  temperature: testCase.temperature,
  maxTokens: testCase.max_tokens,
  stream: testCase.stream,
  tools,
  apiKey: "test-key",
});

console.log(JSON.stringify(result, null, 2));
