import assert from "node:assert/strict";
import test from "node:test";
import { JOB_ID_PATTERN, TX_HASH_PATTERN, validateEvidenceUrl, repositoryPrefixFromInput, explainStatus, explainNextStep, explainWriteFailure } from "../src/lib/protocol.ts";

const base = "https://raw.githubusercontent.com/Leokings/digital-deliverable-verifier/";
const commit = "c58779c534ddae9f127bffc2e06584b6f56a9f9a";

test("accepts a public GitHub repository prefix and full commit-pinned file", () => {
  assert.equal(validateEvidenceUrl(base, true).href, base);
  assert.equal(validateEvidenceUrl(`${base}${commit}/tests/fixtures/installation-guide.txt`).hostname, "raw.githubusercontent.com");
});

test("rejects mutable, foreign, redirected or ambiguous evidence URLs", () => {
  const rejected = [
    `${base}main/file.txt`,
    `${base}${commit}/`,
    `${base}${commit}/../secret.txt`,
    `${base}${commit}//file.txt`,
    `${base}${commit}/file.txt?download=1`,
    `${base}${commit}/file%2Fname.txt`,
    `https://raw.githubusercontent.com.evil.test/owner/repo/${commit}/file.txt`,
    `https://user@raw.githubusercontent.com/owner/repo/${commit}/file.txt`,
    `https://raw.githubusercontent.com:443/owner/repo/${commit}/file.txt`,
    `http://raw.githubusercontent.com/owner/repo/${commit}/file.txt`,
  ];
  for (const value of rejected) assert.throws(() => validateEvidenceUrl(value), value);
});

test("prefix requires repository root and no commit", () => {
  assert.throws(() => validateEvidenceUrl(`${base}${commit}/`, true));
  assert.throws(() => validateEvidenceUrl("https://raw.githubusercontent.com/owner/repo", true));
});

test("buyer can paste a normal GitHub repository link", () => {
  assert.equal(repositoryPrefixFromInput("https://github.com/Leokings/deliveryos"),
    "https://raw.githubusercontent.com/Leokings/deliveryos/");
  assert.equal(repositoryPrefixFromInput(" https://github.com/Leokings/deliveryos/ "),
    "https://raw.githubusercontent.com/Leokings/deliveryos/");
  assert.equal(repositoryPrefixFromInput(base), base);
  for (const value of ["https://github.com/owner/repo/tree/main", "https://github.com/owner/repo?tab=readme",
    "https://github.com.evil.test/owner/repo", "https://user@github.com/owner/repo",
    "https://github.com/owner/..", "http://github.com/owner/repo"]) {
    assert.throws(() => repositoryPrefixFromInput(value), value);
  }
});

test("public route identifiers are constrained", () => {
  assert.ok(JOB_ID_PATTERN.test("job_2026_01"));
  assert.ok(!JOB_ID_PATTERN.test("short"));
  assert.ok(!JOB_ID_PATTERN.test("../../admin"));
  assert.ok(TX_HASH_PATTERN.test(`0x${"a".repeat(64)}`));
  assert.ok(!TX_HASH_PATTERN.test(`0x${"a".repeat(63)}`));
});

test("finality copy never implies payment", () => {
  assert.match(explainStatus("ACCEPTED"), /No payment is moved/);
});

test("next-step copy matches the wallet role and status", () => {
  assert.match(explainNextStep("PROPOSED", "buyer"), /Send this job's link/);
  assert.match(explainNextStep("PROPOSED", "provider"), /accept or decline/);
  assert.match(explainNextStep("SUBMITTED", "buyer"), /approve or request/);
  assert.match(explainNextStep("ACCEPTED", "observer"), /finished/);
});

test("temporary Studionet write failures have safe, plain-language guidance", () => {
  assert.match(explainWriteFailure("eth_sendRawTransaction: Rate limit exceeded: 500 requests per hour"), /Check this job and your wallet activity/);
  assert.doesNotMatch(explainWriteFailure("eth_sendRawTransaction: Rate limit exceeded"), /eth_sendRawTransaction/);
  assert.match(explainWriteFailure("HTTP 503"), /temporarily unavailable/);
  assert.equal(explainWriteFailure("Wallet rejected"), "Wallet rejected");
});
