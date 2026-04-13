#!/usr/bin/env node
/**
 * Dump the HTTP request for a given test case as JSON.
 * Uses the canonical lm15 message format.
 */

import { buildHttpRequest, httpRequestToDict } from "../lm15-ts/dist/curl.js";
import { messagesFromJson } from "../lm15-ts/dist/types.js";

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

// Build options
const opts = {
  system: testCase.system,
  temperature: testCase.temperature,
  maxTokens: testCase.max_tokens,
  topP: testCase.top_p,
  stop: testCase.stop,
  stream: testCase.stream,
  tools,
  apiKey: "test-key",
};

// Handle reasoning
if (testCase.reasoning) {
  opts.reasoning = testCase.reasoning;
}

// Handle messages (canonical format)
if (testCase.messages) {
  opts.messages = messagesFromJson(testCase.messages);
}

// Build the request
let result;
if (testCase.provider) {
  // Need to inject provider passthrough into config
  // Build the request through buildHttpRequest with provider in config
  // We need to go through the lower-level path
  const { resolveProvider } = await import("../lm15-ts/dist/capabilities.js");
  const { buildDefault } = await import("../lm15-ts/dist/factory.js");

  const prompt = testCase.prompt;
  const model = testCase.model;
  const resolvedProvider = resolveProvider(model);

  // Build messages
  let messages;
  if (opts.messages) {
    messages = opts.messages;
  } else if (prompt) {
    const { Part: PartFactory } = await import("../lm15-ts/dist/types.js");
    messages = [{ role: "user", parts: [PartFactory.text(prompt)] }];
  } else {
    throw new Error("either prompt or messages required");
  }

  // Build config with provider passthrough
  const config = {};
  if (opts.maxTokens != null) config.max_tokens = opts.maxTokens;
  if (opts.temperature != null) config.temperature = opts.temperature;
  if (opts.topP != null) config.top_p = opts.topP;
  if (opts.stop) config.stop = opts.stop;
  if (opts.reasoning) {
    config.reasoning = { enabled: true, ...opts.reasoning };
  }
  config.provider = testCase.provider;

  const lmRequest = {
    model,
    messages,
    system: opts.system,
    tools: opts.tools,
    config,
  };

  const client = buildDefault({ apiKey: "test-key", providerHint: resolvedProvider });
  const adapter = client.adapters?.get(resolvedProvider);
  if (!adapter) throw new Error(`no adapter for ${resolvedProvider}`);
  const httpReq = adapter.buildRequest(lmRequest, opts.stream ?? false);
  result = httpRequestToDict(httpReq);
} else {
  result = httpRequestToDict(
    buildHttpRequest(testCase.model, testCase.prompt ?? undefined, opts)
  );
}

console.log(JSON.stringify(result, null, 2));
