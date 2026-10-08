export const CHAIN_ID = 61999;
export const NETWORK = "studionet";
export const CONTRACT_ADDRESS = "0xef13Bfe9A9B0b4cE7EB4AfC2d8EDd8A6c6D43e40" as const;
export const PACKAGES_CONTRACT_ADDRESS = "0x6AdA7535b224343D48175930bd4874201B3f8860" as const;
export const PACKAGES_V3_CONTRACT_ADDRESS = "0x89fFB4Ced8C0befa594B470629b3b15827749DbF" as const;
export const PACKAGES_V4_CONTRACT_ADDRESS = "0x4254924698AA7d4195BC2D734D3b767F6296Ff65" as const;
export type ContractVersion = "v1" | "v2" | "v3" | "v4";
export function contractFor(version: ContractVersion) {
  return version === "v4" ? PACKAGES_V4_CONTRACT_ADDRESS
    : version === "v3" ? PACKAGES_V3_CONTRACT_ADDRESS
    : version === "v2" ? PACKAGES_CONTRACT_ADDRESS : CONTRACT_ADDRESS;
}
export const EXPLORER = "https://explorer-studio.genlayer.com";
export const JOB_ID_PATTERN = /^[A-Za-z0-9_-]{8,64}$/;
export const TX_HASH_PATTERN = /^0x[0-9a-fA-F]{64}$/;
export const ADDRESS_PATTERN = /^0x[0-9a-fA-F]{40}$/;
export const MAX_EVIDENCE_BYTES = 4800;

export type Job = {
  protocol: string;
  job_id: string;
  buyer: string;
  provider: string;
  brief: string;
  criteria: string[];
  evidence_prefix: string;
  due_epoch: number;
  submission_deadline_epoch: number;
  review_deadline_epoch?: number;
  max_revisions: number;
  revision_count: number;
  last_reviewed_fingerprint?: string;
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
  evidence_type?: string;
  content_fingerprint?: string;
  file_count?: number;
  total_bytes?: number;
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

/** Accept a normal GitHub repository link in the buyer form, but keep the
 * contract's stricter raw.githubusercontent.com repository prefix on chain. */
export function repositoryPrefixFromInput(value: string): string {
  const trimmed = value.trim();
  if (trimmed.startsWith("https://raw.githubusercontent.com/")) {
    validateEvidenceUrl(trimmed, true);
    return trimmed;
  }
  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    throw new Error("Paste a public GitHub repository link, such as https://github.com/owner/repo.");
  }
  const parts = /^\/([A-Za-z0-9-]+)\/([A-Za-z0-9._-]+)\/?$/.exec(url.pathname);
  if (url.origin !== "https://github.com" || url.username || url.password || url.port
      || url.search || url.hash || !parts || parts[2] === "." || parts[2] === "..") {
    throw new Error("Use a public GitHub repository link without a branch, file path, or query.");
  }
  const prefix = `https://raw.githubusercontent.com/${parts[1]}/${parts[2]}/`;
  validateEvidenceUrl(prefix, true);
  return prefix;
}

export function explainStatus(status: string, version?: ContractVersion): string {
  const messages: Record<string, string> = {
    PROPOSED: "Waiting for the provider to accept the frozen terms.",
    ACTIVE: "The provider can submit the first deliverable.",
    SUBMITTED: version === "v4"
      ? "The buyer can accept, either party can request validator review, or the provider can correct evidence—but only through the fixed review cutoff. Afterward the result can only be closed as inconclusive."
      : version === "v3"
      ? "The buyer can accept, either party can request validator review, or the provider can correct pending evidence before the correction cutoff."
      : "The buyer can accept, or either party can request validator review.",
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

export function explainNextStep(status: string, role: "buyer" | "provider" | "observer", version?: ContractVersion): string {
  if (status === "PROPOSED") {
    if (role === "buyer") return "Send this job's link to the person or agent you invited.";
    if (role === "provider") return "Read the request below, then accept or decline it.";
  }
  if (status === "ACTIVE" || status === "REVISION") {
    if (role === "provider") return "Publish the finished public files, then submit their pinned link.";
    if (role === "buyer") return "The invitee is working. Come back when they submit a version.";
  }
  if (status === "SUBMITTED") {
    if (role === "buyer") return version === "v4"
      ? "Read the submitted files, then approve or request GenLayer review before the cutoff."
      : "Read the submitted files below, then approve or request GenLayer review.";
    if (role === "provider") return version === "v4"
      ? "Wait for approval or request review before the cutoff. You can correct pending evidence until then."
      : version === "v3"
      ? "Wait for approval or request review. You can replace pending evidence before the correction cutoff."
      : "The work is submitted. Wait for approval or request GenLayer review.";
  }
  if (["ACCEPTED", "REJECTED", "INCONCLUSIVE", "EXPIRED", "CANCELLED", "DECLINED"].includes(status)) {
    return "This job is finished. The decision and evidence are shown below.";
  }
  return "Read this public job below. Connect the invited wallet to take an action.";
}

export function explainWriteFailure(message: string): string {
  if (/rate limit exceeded|\b429\b/i.test(message)) {
    return "Studionet has reached its request limit. Check this job and your wallet activity before retrying later.";
  }
  if (/\b50[23]\b|failed to fetch|network error/i.test(message)) {
    return "Studionet is temporarily unavailable. Check this job and your wallet activity before retrying.";
  }
  return message || "The wallet did not complete the transaction. Check its activity before retrying.";
}
