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
    "https://github.com/Leokings/deliveryos/blob/main/README.md#evidence-packages-v4-current-v3-and-v2-legacy");
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

  const v4Job = { ...job, protocol: "DELIVERYOS_PACKAGES_V4" };
  await page.route(`**/api/v4/jobs/${id}`, (route) => route.fulfill({ json: v4Job }));
  await page.route(`**/api/v4/jobs/${id}/submissions/2`, (route) => route.fulfill({ json: submission }));
  await page.locator(".format-details summary").click();
  await page.getByRole("button", { name: /Up to six files v4 · current/i }).click();
  await page.getByPlaceholder("Paste a job reference").fill(id);
  await page.getByRole("button", { name: /Open job/ }).click();
  await page.getByRole("button", { name: "Close unreviewed submission" }).waitFor();
  assert.equal(await page.getByRole("button", { name: /Ask GenLayer to review/ }).count(), 0);
  assert.match(await page.locator(".next-step-copy").innerText(), /no longer valid/);
  assert.match(await page.locator(".job-detail").innerText(), /Review cutoff/);

  const buyerPage = await browser.newPage();
  await buyerPage.route(`**/api/v4/jobs/${id}`, (route) => route.fulfill({ json: v4Job }));
  await buyerPage.route(`**/api/v4/jobs/${id}/submissions/2`, (route) => route.fulfill({ json: submission }));
  await buyerPage.addInitScript((address) => {
    window.ethereum = { request: async ({ method }) => {
      if (method === "eth_requestAccounts") return [address];
      if (method === "eth_chainId") return "0xf22f";
      throw new Error(`Unexpected wallet method ${method}`);
    } };
  }, v4Job.buyer);
  await buyerPage.goto(`${base}/?version=v4&job=${id}`, { waitUntil: "networkidle" });
  await buyerPage.getByRole("button", { name: "Connect wallet" }).click();
  await buyerPage.getByRole("button", { name: /Browser wallet ·/ }).waitFor();
  assert.equal(await buyerPage.getByRole("button", { name: /Approve finished work/ }).count(), 0);
  assert.equal(await buyerPage.getByRole("button", { name: /Ask GenLayer to review/ }).count(), 0);
  await buyerPage.close();

  // A previous protocol's slow response must not become the current list.
  const racePage = await browser.newPage();
  let releaseLegacy;
  const legacyPending = new Promise((resolve) => { releaseLegacy = resolve; });
  await racePage.route("**/api/v3/jobs?limit=3", async (route) => {
    await legacyPending;
    await route.fulfill({ json: { total: 1, jobs: [{ ...job, job_id: "legacy_recent_01" }] } });
  });
  await racePage.route("**/api/v4/jobs?limit=3", (route) => route.fulfill({ json: { total: 0, jobs: [] } }));
  await racePage.goto(`${base}/?version=v3`, { waitUntil: "networkidle" });
  const legacyRequest = racePage.waitForRequest((request) => request.url().includes("/api/v3/jobs?limit=3"));
  await racePage.getByRole("tab", { name: "Explore jobs" }).click();
  await legacyRequest;
  await racePage.locator(".format-details summary").click();
  await racePage.getByRole("button", { name: /Up to six files v4 · current/i }).click();
  await racePage.getByText("No jobs have been created yet.").waitFor();
  releaseLegacy();
  await racePage.waitForTimeout(250);
  assert.equal(await racePage.getByText("legacy_recent_01").count(), 0);
  await racePage.close();

  // Preflight is part of a write workflow: no double submit or protocol switch.
  v4Job.review_deadline_epoch = Math.floor(Date.now() / 1000) + 7200;
  await page.locator(".job-head-actions").getByRole("button", { name: /Refresh/ }).click();
  await page.getByRole("button", { name: /Correct pending evidence/ }).waitFor();
  let releasePreflight;
  const preflightPending = new Promise((resolve) => { releasePreflight = resolve; });
  await page.route("**/api/v4/packages/preflight?*", async (route) => {
    await preflightPending;
    await route.fulfill({ status: 422, json: { error: "Test preflight stopped before signing." } });
  });
  await page.locator(".submit-box input").fill(submission.url);
  const preflightRequest = page.waitForRequest((request) => request.url().includes("/api/v4/packages/preflight?"));
  await page.getByRole("button", { name: /Correct pending evidence/ }).click();
  await preflightRequest;
  if (await page.locator(".format-details").getAttribute("open") === null) {
    await page.locator(".format-details summary").click();
  }
  assert.equal(await page.getByRole("button", { name: /Up to six files v3 · legacy/i }).isDisabled(), true);
  assert.equal(await page.getByRole("button", { name: /Correct pending evidence/ }).isDisabled(), true);
  releasePreflight();
  await page.locator(".alert-error").getByText(/Test preflight stopped/).waitFor();
  assert.equal(await page.locator(".alert-info").count(), 0, "failed preflight must clear the checking notice");
  assert.equal(await page.getByRole("button", { name: /Up to six files v3 · legacy/i }).isEnabled(), true);
  console.log("PASS v3 legacy soft-close, v4 strict-cutoff UI, stale-state cleanup, version-switch list race, and preflight write lock");
} finally {
  await browser.close();
}
