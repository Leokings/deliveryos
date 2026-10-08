import assert from "node:assert/strict";
import { chromium } from "playwright";

const base = process.env.BASE_URL ?? "http://localhost:3001";
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const provider = "0x2222222222222222222222222222222222222222";
  const id = "job_example_03";
  const job = {
    protocol: "DELIVERYOS_PACKAGES_V3", job_id: id,
    buyer: "0x1111111111111111111111111111111111111111", provider,
    brief: "Deliver a public two-file package with a short guide and verification record.",
    criteria: ["The guide names the installation command."],
    evidence_prefix: "https://raw.githubusercontent.com/example/repo/",
    due_epoch: Math.floor(Date.now() / 1000) + 3600,
    submission_deadline_epoch: Math.floor(Date.now() / 1000) + 3600,
    review_deadline_epoch: Math.floor(Date.now() / 1000) + 7200,
    max_revisions: 1, revision_count: 0, current_version: 2,
    status: "SUBMITTED", latest_statuses: [], decision_source: "",
    scope_digest: "a".repeat(64), created_epoch: Math.floor(Date.now() / 1000), decided_epoch: 0,
    last_reviewed_fingerprint: "",
  };
  const submission = { job_id: id, version: 2, provider,
    url: "https://raw.githubusercontent.com/example/repo/" + "a".repeat(40) + "/package.json",
    sha256: "b".repeat(64), size_bytes: 110, submitted_epoch: Math.floor(Date.now() / 1000),
    statuses: [], verdict: "", evidence_type: "PACKAGE", content_fingerprint: "",
    file_count: 0, total_bytes: 0 };
  await page.route(`**/api/v3/jobs/${id}`, (route) => route.fulfill({ json: job }));
  await page.route(`**/api/v3/jobs/${id}/submissions/2`, (route) => route.fulfill({ json: submission }));
  await page.route("**/api/v3/jobs/audit_unknown_2026", (route) => route.fulfill({
    status: 404, json: { error: "Job was not found on this contract." },
  }));
  await page.addInitScript((address) => {
    window.ethereum = { request: async ({ method }) => {
      if (method === "eth_requestAccounts") return [address];
      if (method === "eth_chainId") return "0xf22f";
      throw new Error(`Unexpected wallet method ${method}`);
    } };
  }, provider);
  await page.goto(`${base}/?version=v3&job=${id}`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: id }).waitFor();
  await page.getByRole("button", { name: "Connect wallet" }).click();
  await page.getByRole("button", { name: /Browser wallet ·/ }).waitFor();
  await page.getByRole("button", { name: /Correct pending evidence/ }).waitFor();
  assert.match(await page.locator(".submit-box").innerText(), /cutoff stays/);
  assert.match(await page.locator(".job-detail").innerText(), /Unreviewed close available after/);
  assert.equal(await page.getByRole("link", { name: /How to prepare a package/ }).getAttribute("href"),
    "https://github.com/Leokings/deliveryos/blob/main/README.md#evidence-packages-v3-current-v2-legacy");
  job.review_deadline_epoch = Math.floor(Date.now() / 1000) - 1;
  await page.locator(".job-head-actions").getByRole("button", { name: /Refresh/ }).click();
  await page.getByRole("button", { name: "Close unreviewed submission" }).waitFor();
  assert.equal(await page.getByRole("button", { name: /Correct pending evidence/ }).count(), 0);
  assert.match(await page.locator(".actions-card").innerText(), /Closing is available, not automatic/);
  assert.match(await page.locator(".actions-card").innerText(), /buyer may still approve/);
  await page.getByPlaceholder("Paste a job reference").fill("audit_unknown_2026");
  await page.getByRole("button", { name: /Open job/ }).click();
  await page.locator(".alert-error").getByText(/not found/i).waitFor();
  assert.equal(await page.locator(".job-detail").count(), 0);
  assert.equal(new URL(page.url()).searchParams.has("job"), false);
  console.log("PASS v3 correction CTA, accurate soft-close copy, package guide link, wallet role, and stale-state cleanup");
} finally {
  await browser.close();
}
