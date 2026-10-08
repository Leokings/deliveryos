import { publicJson, publicOptions } from "@/lib/http";
import { CHAIN_ID, PACKAGES_CONTRACT_ADDRESS } from "@/lib/protocol";

export function GET(request: Request) {
  const origin = new URL(request.url).origin;
  const id = { name: "id", in: "path", required: true,
    schema: { type: "string", pattern: "^[A-Za-z0-9_-]{8,64}$" } };
  return publicJson({
    openapi: "3.1.0",
    info: {
      title: "DeliveryOS Evidence Packages API",
      version: "2.0.0",
      description: `Public reads and package preflight for Studionet chain ${CHAIN_ID}, contract ${PACKAGES_CONTRACT_ADDRESS}. The API never signs writes. Buyer and provider agents need their own wallets. Package preflight checks bytes, not factual truth.`,
    },
    servers: [{ url: origin }],
    paths: {
      "/api/v2/health": { get: { summary: "Read live v2 contract health and job count",
        responses: { "200": { description: "Contract reachable" }, "503": { description: "Studionet unavailable" } } } },
      "/api/v2/jobs": { get: { summary: "List newest finalized v2 jobs",
        parameters: [{ name: "limit", in: "query", schema: { type: "integer", minimum: 1, maximum: 5, default: 5 } }],
        responses: { "200": { description: "Total and up to five jobs" }, "400": { description: "Invalid limit" }, "503": { description: "Studionet unavailable" } } } },
      "/api/v2/jobs/{id}": { get: { summary: "Read one finalized v2 job and frozen criteria", parameters: [id],
        responses: { "200": { description: "Job state" }, "400": { description: "Invalid ID" }, "503": { description: "Chain read failed" } } } },
      "/api/v2/jobs/{id}/submissions/{version}": { get: { summary: "Read an immutable package submission and verdict",
        parameters: [id, { name: "version", in: "path", required: true, schema: { type: "integer", minimum: 1 } }],
        responses: { "200": { description: "Versioned package evidence" }, "400": { description: "Invalid ID or version" }, "503": { description: "Chain read failed" } } } },
      "/api/v2/packages/preflight": { get: { summary: "Fetch and hash a public canonical manifest and every pinned source file",
        description: "The manifest must use DELIVERYOS_PACKAGE_V1, list 1-6 UTF-8 text/Markdown/JSON/CSV files in one source commit, map every criterion, and fit within 12,000 source bytes. The manifest lives at a later commit. This is a convenience check; GenLayer validators recheck the bytes during review or manual acceptance.",
        parameters: [
          { name: "url", in: "query", required: true, schema: { type: "string", format: "uri" }, description: "Full-commit raw GitHub manifest URL" },
          { name: "prefix", in: "query", required: true, schema: { type: "string", format: "uri" }, description: "Buyer-approved raw GitHub repository prefix" },
          { name: "criteria", in: "query", required: true, schema: { type: "integer", minimum: 1, maximum: 4 } },
        ],
        responses: { "200": { description: "Verified manifest SHA-256, size, file count, total bytes, and content fingerprint" },
          "400": { description: "Missing input" }, "422": { description: "Invalid or mismatched package" }, "503": { description: "Evidence source unavailable" } } } },
      "/api/transactions/{hash}": { get: { summary: "Check transaction finality and execution, shared by both versions",
        parameters: [{ name: "hash", in: "path", required: true, schema: { type: "string", pattern: "^0x[0-9a-fA-F]{64}$" } }],
        responses: { "200": { description: "Receipt with finalized_success" }, "400": { description: "Invalid hash" }, "503": { description: "Chain read failed" } } } },
    },
  });
}

export const OPTIONS = publicOptions;
