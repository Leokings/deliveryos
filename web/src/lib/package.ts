import { createHash } from "node:crypto";
import { validateEvidenceUrl } from "./protocol.ts";

const MAX_FILE_BYTES = 4800;
const MAX_TOTAL_BYTES = 12000;
const MEDIA_TYPES = new Set(["text/plain", "text/markdown", "application/json", "text/csv"]);
const SHA = /^[0-9a-fA-F]{64}$/;
const COMMIT = /^[0-9a-fA-F]{40}$/;

type PackageFile = {
  url: string;
  sha256: string;
  size_bytes: number;
  media_type: string;
  criteria: number[];
};

function fail(message: string): never { throw new Error(message); }
function objectWithKeys(value: unknown, keys: string[]): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).sort().join("|") === keys.sort().join("|");
}
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object).sort().map((key) => `${JSON.stringify(key)}:${canonical(object[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}
function sha256(body: Uint8Array | string) {
  return createHash("sha256").update(body).digest("hex");
}

async function pinnedBytes(url: string): Promise<Uint8Array> {
  validateEvidenceUrl(url);
  const response = await fetch(url, {
    redirect: "error", cache: "no-store", signal: AbortSignal.timeout(10000),
    headers: { "Accept-Encoding": "identity" },
  });
  if (!response.ok || !response.body) fail(`Evidence fetch failed (HTTP ${response.status}).`);
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > MAX_FILE_BYTES) {
        await reader.cancel();
        fail("Evidence exceeds 4,800 bytes.");
      }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  if (!size) fail("Evidence is empty.");
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return bytes;
}

function validCsv(text: string) {
  let columns = 1;
  let quoted = false;
  let closedQuote = false;
  let atFieldStart = true;
  let rowStarted = false;
  let rows = 0;
  let expected: number | null = null;
  let lastWasNewline = false;
  function endRow() {
    if (!rowStarted || (expected !== null && columns !== expected)) {
      fail("CSV rows have inconsistent columns or are blank.");
    }
    expected = columns;
    rows++;
    columns = 1;
    atFieldStart = true;
    closedQuote = false;
    rowStarted = false;
    lastWasNewline = true;
  }
  for (let index = 0; index < text.length; index++) {
    const char = text[index];
    lastWasNewline = false;
    if (quoted) {
      if (char === '"') {
        if (text[index + 1] === '"') index++;
        else { quoted = false; closedQuote = true; }
      }
      continue;
    }
    if (char === ",") {
      columns++;
      atFieldStart = true;
      closedQuote = false;
      rowStarted = true;
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && text[index + 1] === "\n") index++;
      endRow();
    } else if (char === '"' && atFieldStart) {
      quoted = true;
      atFieldStart = false;
      rowStarted = true;
    } else if (char === '"' || closedQuote) {
      fail("CSV quoting is malformed.");
    } else {
      atFieldStart = false;
      rowStarted = true;
    }
  }
  if (quoted) fail("CSV quoting is malformed.");
  if (!lastWasNewline) endRow();
  if (!rows) fail("CSV has no rows.");
}

export type PackagePreflight = {
  url: string;
  sha256: string;
  size_bytes: number;
  file_count: number;
  total_bytes: number;
  content_fingerprint: string;
  files: Array<{ url: string; media_type: string; criteria: number[]; size_bytes: number }>;
};

export async function verifyPublicPackage(manifestUrl: string, evidencePrefix: string,
  criterionCount: number): Promise<PackagePreflight> {
  validateEvidenceUrl(evidencePrefix, true);
  validateEvidenceUrl(manifestUrl);
  if (!manifestUrl.startsWith(evidencePrefix)) fail("Manifest is outside the agreed repository.");
  if (!Number.isInteger(criterionCount) || criterionCount < 1 || criterionCount > 4) {
    fail("Provide 1-4 criteria.");
  }
  const manifestBytes = await pinnedBytes(manifestUrl);
  let manifest: unknown;
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(manifestBytes);
    manifest = JSON.parse(text);
  } catch { fail("Manifest must be UTF-8 JSON."); }
  if (!objectWithKeys(manifest, ["protocol", "source_commit", "files"])) {
    fail("Manifest fields are invalid.");
  }
  if (text !== canonical(manifest) + "\n") fail("Manifest must be canonical JSON with one final newline.");
  if (manifest.protocol !== "DELIVERYOS_PACKAGE_V1" || typeof manifest.source_commit !== "string"
    || !COMMIT.test(manifest.source_commit)) fail("Manifest protocol or source commit is invalid.");
  if (!Array.isArray(manifest.files) || !manifest.files.length || manifest.files.length > 6) {
    fail("Manifest must list 1-6 files.");
  }
  const parts = new URL(manifestUrl).pathname.split("/");
  const sourcePrefix = `https://raw.githubusercontent.com/${parts[1]}/${parts[2]}/${manifest.source_commit}/`;
  const seenUrls = new Set<string>();
  const seenHashes = new Set<string>();
  const covered = new Set<number>();
  let total = 0;
  const files: PackagePreflight["files"] = [];
  for (const unknownFile of manifest.files) {
    if (!objectWithKeys(unknownFile, ["url", "sha256", "size_bytes", "media_type", "criteria"])) {
      fail("File fields are invalid.");
    }
    const file = unknownFile as PackageFile;
    if (typeof file.url !== "string") fail("File URL is invalid.");
    validateEvidenceUrl(file.url);
    if (file.url === manifestUrl || !file.url.startsWith(evidencePrefix) || !file.url.startsWith(sourcePrefix)) {
      fail("File must use the agreed repository and source commit.");
    }
    if (seenUrls.has(file.url)) fail("Duplicate file URL.");
    if (typeof file.sha256 !== "string" || !SHA.test(file.sha256)) fail("File SHA-256 is invalid.");
    const digest = file.sha256.toLowerCase();
    if (seenHashes.has(digest)) fail("Duplicate file bytes.");
    if (!Number.isInteger(file.size_bytes) || file.size_bytes < 1 || file.size_bytes > MAX_FILE_BYTES) {
      fail("File size must be 1-4800 bytes.");
    }
    if (!MEDIA_TYPES.has(file.media_type)) fail("Unsupported media type.");
    if (!Array.isArray(file.criteria) || !file.criteria.length || new Set(file.criteria).size !== file.criteria.length
      || file.criteria.some((index) => !Number.isInteger(index) || index < 0 || index >= criterionCount)) {
      fail("File criterion mapping is invalid.");
    }
    total += file.size_bytes;
    if (total > MAX_TOTAL_BYTES) fail("Package exceeds 12,000 bytes.");
    seenUrls.add(file.url);
    seenHashes.add(digest);
    file.criteria.forEach((index) => covered.add(index));
    files.push({ url: file.url, media_type: file.media_type, criteria: file.criteria, size_bytes: file.size_bytes });
  }
  if (covered.size !== criterionCount) fail("Every criterion needs a mapped file.");
  await Promise.all(manifest.files.map(async (file: PackageFile) => {
    const body = await pinnedBytes(file.url);
    if (body.length !== file.size_bytes || sha256(body) !== file.sha256.toLowerCase()) {
      fail("File bytes do not match the manifest.");
    }
    let content: string;
    try { content = new TextDecoder("utf-8", { fatal: true }).decode(body); }
    catch { fail("File must be UTF-8 text."); }
    if (!content.trim()) fail("File has no text.");
    if (file.media_type === "application/json") {
      try { JSON.parse(content); } catch { fail("JSON file is invalid."); }
    } else if (file.media_type === "text/csv") validCsv(content);
  }));
  return {
    url: manifestUrl, sha256: sha256(manifestBytes), size_bytes: manifestBytes.length,
    file_count: files.length, total_bytes: total,
    content_fingerprint: sha256(canonical([...seenHashes].sort())), files,
  };
}
