import assert from "node:assert/strict";
import test from "node:test";
import { isMissingViewError, notFound, upstreamError } from "../src/lib/http.ts";

test("only the known pure-view revert is classified as a missing record", async () => {
  const missing = { name: "InvalidInputRpcError", code: -32000,
    details: "execution failed", cause: { message: "execution failed" } };
  assert.equal(isMissingViewError(missing), true);
  assert.equal(isMissingViewError({ ...missing, details: "rate limit exceeded" }), false);
  assert.equal(isMissingViewError({ ...missing, code: -32005 }), false);
  assert.equal(isMissingViewError(new Error("network error")), false);
  const response = notFound("Job");
  assert.equal(response.status, 404);
  assert.match((await response.json()).error, /Job was not found/);
});

test("Studionet quota is surfaced distinctly without inventing a retry time", async () => {
  const original = console.error;
  console.error = () => undefined;
  try {
    const response = upstreamError("job", new Error("Rate limit exceeded: 500 requests per hour"));
    assert.equal(response.status, 429);
    assert.match((await response.json()).error, /hourly request limit/);
  } finally {
    console.error = original;
  }
});
