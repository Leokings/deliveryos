export const CHAIN_ID = 61999;
export const NETWORK = "studionet";
export const CONTRACT_ADDRESS = "0xef13Bfe9A9B0b4cE7EB4AfC2d8EDd8A6c6D43e40" as const;
export const EXPLORER = "https://explorer-studio.genlayer.com";
export const JOB_ID_PATTERN = /^[A-Za-z0-9_-]{8,64}$/;
export const TX_HASH_PATTERN = /^0x[0-9a-fA-F]{64}$/;
export const ADDRESS_PATTERN = /^0x[0-9a-fA-F]{40}$/;
export const MAX_EVIDENCE_BYTES = 4800;

export type Job = {
  job_id: string;
  buyer: string;
  provider: string;
  brief: string;
  criteria: string[];
  evidence_prefix: string;
  due_epoch: number;
  submission_deadline_epoch: number;
  max_revisions: number;
  revision_count: number;
  current_version: number;
  status: string;
  latest_statuses: string[];
  decision_source: string;
  scope_digest: string;
  created_epoch: number;
  decided_epoch: number;
};

export type Submission = {
  job_id: string;
  version: number;
  provider: string;
  url: string;
  sha256: string;
  size_bytes: number;
  submitted_epoch: number;
  statuses: string[];
  verdict: string;
};

export function validateEvidenceUrl(value: string, prefix = false): URL {
  if (typeof value !== "string" || value.length > 1024 || !value.startsWith("https://")) {
    throw new Error("Evidence must be a plain HTTPS URL, at most 1,024 characters.");
  }
  if (/[?#%\\\s]/.test(value)) {
    throw new Error("Evidence URL cannot contain query, fragment, encoding, slash escapes or whitespace.");
  }
  if (/(?:\/|^)\.{1,2}(?:\/|$)/.test(value)) {
    throw new Error("Evidence URL cannot contain dot path segments.");
  }
  const authority = value.slice("https://".length).split("/", 1)[0];
  if (authority.toLowerCase() !== "raw.githubusercontent.com") {
    throw new Error("Evidence must be served from raw.githubusercontent.com without credentials or a port.");
  }
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error("Evidence URL is malformed.");
  }
  if (url.origin !== "https://raw.githubusercontent.com" || url.username || url.password || url.port) {
    throw new Error("Evidence must be served from raw.githubusercontent.com.");
  }
  if (!/^\/[A-Za-z0-9._~/-]+$/.test(url.pathname) || url.pathname.includes("//")) {
    throw new Error("Evidence path has unsupported characters.");
  }
  const parts = url.pathname.split("/");
  if (!parts[1] || !parts[2] || parts.some((part) => part === "." || part === "..")) {
    throw new Error("Evidence URL must name a public owner and repository.");
  }
  if (prefix) {
    if (parts.length !== 4 || parts[3] !== "" || !value.endsWith("/")) {
      throw new Error("Repository prefix must be https://raw.githubusercontent.com/owner/repo/.");
    }
  } else if (parts.length < 5 || !/^[0-9a-fA-F]{40}$/.test(parts[3]) || !parts.at(-1)) {
    throw new Error("Evidence URL needs a full 40-character commit SHA and a file path.");
  }
  return url;
}

export function explainStatus(status: string): string {
  const messages: Record<string, string> = {
    PROPOSED: "Waiting for the provider to accept the frozen terms.",
    ACTIVE: "The provider can submit the first deliverable.",
    SUBMITTED: "The buyer can accept, or either party can request validator review.",
    REVISION: "The provider may submit changed evidence before the revision deadline.",
    ACCEPTED: "A final acceptance decision is recorded. No payment is moved.",
    REJECTED: "The final submitted version did not meet the criteria.",
    INCONCLUSIVE: "The evidence or review did not establish an acceptance.",
    EXPIRED: "No deliverable arrived before the deadline.",
    CANCELLED: "The buyer cancelled before provider acceptance.",
    DECLINED: "The provider declined the proposal.",
  };
  return messages[status] ?? "Read the on-chain job for its current status.";
}
