#!/usr/bin/env node
/**
 * Dump the HTTP request for a given test case as JSON.
 * Run after `npm run build` in lm15-ts.
 */

import { dumpHttp } from "../lm15-ts/dist/curl.js";
import type { Tool } from "../lm15-ts/dist/types.js";

const caseJson = process.argv[2];
if (!caseJson) {
  console.error("usage: dump_request.ts <test-case-json>");
  process.exit(1);
}

const testCase = JSON.parse(caseJson) as {
  model: string;
  prompt: string;
  system?: string;
  temperature?: number;
  maxTokens?: number;
  stream?: boolean;
  tools?: Array<{ name: string; description?: string; parameters?: Record<string, unknown> }>;
};

const tools: Tool[] | undefined = testCase.tools?.map(t => ({
  type: "function" as const,
  name: t.name,
  description: t.description,
  parameters: t.parameters ?? { type: "object", properties: {} },
}));

const result = dumpHttp(testCase.model, testCase.prompt, {
  system: testCase.system,
  temperature: testCase.temperature,
  maxTokens: testCase.maxTokens,
  stream: testCase.stream,
  tools,
  env: process.env.LM15_ENV ?? ".env",
});

console.log(JSON.stringify(result, null, 2));
