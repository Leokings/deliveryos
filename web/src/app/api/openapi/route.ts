import { publicJson, publicOptions } from "@/lib/http";
import { CHAIN_ID, CONTRACT_ADDRESS } from "@/lib/protocol";

export function GET(request: Request) {
  const origin = new URL(request.url).origin;
  const error = { type: "object", properties: { error: { type: "string" } } };
  const job = { type: "object", description: "Finalized DeliveryOS job state, including parties, frozen scope, deadline and verdict." };
  return publicJson({
    openapi: "3.1.0",
    info: {
      title: "DeliveryOS Read API",
      version: "1.0.0",
      description: `Public, read-only access to GenLayer Studionet chain ${CHAIN_ID}, contract ${CONTRACT_ADDRESS}. Writes require each party's own wallet via GenLayer or the bundled MCP client. No API key or custodial signer is provided.`,
    },
    servers: [{ url: origin }],
    paths: {
      "/api/health": { get: { summary: "Check live contract reads", responses: { "200": { description: "Contract reachable" }, "503": { description: "Studionet unavailable" } } } },
      "/api/jobs": { get: { summary: "List up to five newest finalized jobs", parameters: [{ name: "limit", in: "query", schema: { type: "integer", minimum: 1, maximum: 5, default: 5 } }], responses: { "200": { description: "Job list", content: { "application/json": { schema: { type: "object", properties: { total: { type: "integer" }, jobs: { type: "array", items: job } } } } } }, "400": { description: "Invalid limit", content: { "application/json": { schema: error } } } } } },
      "/api/jobs/{id}": { get: { summary: "Read a finalized job", parameters: [{ name: "id", in: "path", required: true, schema: { type: "string", pattern: "^[A-Za-z0-9_-]{8,64}$" } }], responses: { "200": { description: "Job state", content: { "application/json": { schema: job } } }, "400": { description: "Invalid job ID" }, "503": { description: "Chain read failed" } } } },
      "/api/jobs/{id}/submissions/{version}": { get: { summary: "Read an immutable submitted version and its verdict", parameters: [{ name: "id", in: "path", required: true, schema: { type: "string" } }, { name: "version", in: "path", required: true, schema: { type: "integer", minimum: 1 } }], responses: { "200": { description: "Versioned submission" }, "400": { description: "Invalid ID or version" }, "503": { description: "Chain read failed" } } } },
      "/api/transactions/{hash}": { get: { summary: "Check consensus and execution, not just lifecycle", parameters: [{ name: "hash", in: "path", required: true, schema: { type: "string", pattern: "^0x[0-9a-fA-F]{64}$" } }], responses: { "200": { description: "Transaction status with finalized_success boolean" }, "400": { description: "Invalid hash" }, "503": { description: "Chain read failed" } } } },
      "/api/evidence": { get: { summary: "Validate and hash a public commit-pinned GitHub text file", parameters: [{ name: "url", in: "query", required: true, schema: { type: "string", format: "uri" } }], responses: { "200": { description: "SHA-256 and byte length" }, "400": { description: "Invalid URL" }, "422": { description: "Unavailable or unsuitable evidence" } } } },
    },
  });
}

export const OPTIONS = publicOptions;
