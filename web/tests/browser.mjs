import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const base = process.env.BASE_URL ?? "http://localhost:3001";
const browser = await chromium.launch({ headless: true });
try {
  await mkdir("artifacts", { recursive: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const errors = [];
  let recentRequests = 0;
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => { if (request.url().includes("/api/v4/jobs?limit=3")) recentRequests++; });
  const home = await page.goto(base, { waitUntil: "networkidle" });
  assert.equal(home.status(), 200);
  await page.getByRole("heading", { name: /Work together/i }).waitFor();
  const canonical = await browser.newPage();
  await canonical.goto(`${base}/?version=v2`, { waitUntil: "networkidle" });
  assert.equal(new URL(canonical.url()).search, "", "a stale no-job v2 URL should become the current v4 root");
  await canonical.locator(".format-details summary").click();
  await canonical.getByRole("button", { name: /Up to six files v2 · legacy/i }).click();
  assert.equal(new URL(canonical.url()).searchParams.get("version"), "v2", "legacy browsing remains available by explicit choice");
  await canonical.getByRole("button", { name: /Up to six files v4 · current/i }).click();
  assert.equal(new URL(canonical.url()).search, "", "returning to v4 should restore the clean root URL");
  await canonical.goto(`${base}/?version=v2&job=package_f2131d0cd28244b2`, { waitUntil: "networkidle" });
  await canonical.getByRole("heading", { name: "package_f2131d0cd28244b2" }).waitFor();
  assert.equal(new URL(canonical.url()).searchParams.get("version"), "v2", "historical job links must remain versioned");
  await canonical.close();
  assert.equal(recentRequests, 0, "landing view should not spend Studionet RPC calls on recent jobs");
  assert.match(await page.locator(".hero-copy").innerText(), /no wallet needed/i);
  assert.match(await page.locator(".format-details").innerText(), /up to 6 public files/i);
  assert.equal(await page.locator(".format-details").getAttribute("open"), null);
  assert.match(await page.locator('.inline-input input').inputValue(), /^job_[a-f0-9]{16}$/);
  assert.ok(await page.locator('input[type="datetime-local"]').inputValue());
  await page.locator(".handoff-row").last().evaluate((element) => Promise.all(
    element.getAnimations().map((animation) => animation.finished)));
  await page.screenshot({ path: "artifacts/desktop.png", fullPage: true });

  await page.getByRole("button", { name: /Explore a completed example/ }).click();
  await page.getByRole("heading", { name: "package_v4_2d746c70318d4b36" }).waitFor();
  assert.match(await page.locator(".job-detail").innerText(), /ACCEPTED/);
  assert.match(await page.locator(".job-detail").innerText(), /MET/);
  assert.match(await page.locator(".job-detail").innerText(), /2 files/);
  assert.doesNotMatch(await page.locator(".job-detail").innerText(), /Review closes/);
  assert.match(await page.locator(".proof-strip").innerText(), /happened on Studionet/);
  await page.screenshot({ path: "artifacts/example-decision.png", fullPage: true });
  const review = await page.request.get(new URL(await page.getByRole("link", { name: /Review transaction/ }).getAttribute("href"), base).toString());
  assert.equal(review.status(), 200);
  assert.equal((await review.json()).finalized_success, true);
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.getByRole("button", { name: /Copy job link/ }).click();
  const sharedLink = await page.evaluate(() => navigator.clipboard.readText());
  assert.match(sharedLink, /\?version=v4&job=package_v4_2d746c70318d4b36$/);
  const invited = await browser.newPage();
  await invited.goto(sharedLink, { waitUntil: "networkidle" });
  await invited.getByRole("heading", { name: "package_v4_2d746c70318d4b36" }).waitFor();
  assert.equal(await invited.getByRole("tab", { name: "Open invite" }).getAttribute("aria-selected"), "true");
  assert.match(await invited.locator(".next-step-copy").innerText(), /finished/);
  await invited.close();

  await page.getByRole("tab", { name: "Open invite" }).click();
  await page.getByPlaceholder("Paste a job reference").fill("audit_unknown_2026");
  await page.getByRole("button", { name: /Open job/ }).click();
  await page.locator(".alert-error").getByText(/not found/i).waitFor();
  assert.equal(await page.locator(".job-detail").count(), 0, "failed lookup must not leave the previous accepted job visible");
  assert.equal(new URL(page.url()).searchParams.has("job"), false);
  assert.equal((await page.request.get(`${base}/api/v4/jobs/audit_unknown_2026`)).status(), 404);

  await page.getByRole("tab", { name: "Create request" }).click();
  await page.locator(".panel-main").getByRole("button", { name: "Create request" }).click();
  assert.match(await page.locator(".alert-error").innerText(), /provider wallet address/);
  await page.getByRole("button", { name: "New ID" }).click();
  assert.match(await page.locator(".inline-input input").inputValue(), /^job_[a-f0-9]{16}$/);

  await page.getByRole("tab", { name: "Agent setup" }).click();
  assert.equal(await page.locator(".alert-error").count(), 0, "old form errors should clear when changing tasks");
  assert.match(await page.locator(".agent-simple-flow").innerText(), /local MCP command/);
  await page.locator(".agent-advanced summary").click();
  assert.match(await page.locator(".api-disclaimer").innerText(), /API key alone cannot sign/);
  await page.screenshot({ path: "artifacts/agent-setup.png", fullPage: true });
  const spec = await page.request.get(`${base}/openapi.json`);
  assert.equal(spec.status(), 200);
  assert.equal((await spec.json()).openapi, "3.1.0");
  assert.equal((await spec.json()).info.version, "4.0.0");
  const llms = await page.request.get(`${base}/llms.txt`);
  assert.equal(llms.status(), 200);
  assert.match(await llms.text(), /not a public job marketplace/);

  await page.locator(".format-details summary").click();
  await page.getByRole("button", { name: /Single file v1/i }).click();
  await page.getByRole("button", { name: /Explore a completed example/ }).click();
  await page.getByRole("heading", { name: "deliveryos_cb5bcede778b4248" }).waitFor();
  assert.match(await page.locator(".job-detail").innerText(), /ACCEPTED/);
  await page.getByRole("button", { name: /Up to six files v2 · legacy/i }).click();
  await page.getByRole("button", { name: /Explore a completed example/ }).click();
  await page.getByRole("heading", { name: "package_f2131d0cd28244b2" }).waitFor();
  assert.match(await page.locator(".job-detail").innerText(), /ACCEPTED/);
  const v2Health = await page.request.get(`${base}/api/v2/health`);
  assert.equal(v2Health.status(), 200);
  assert.equal((await v2Health.json()).protocol, "DELIVERYOS_PACKAGES_V2");
  const v2Spec = await page.request.get(`${base}/api/v2/openapi`);
  assert.equal(v2Spec.status(), 200);
  assert.equal((await v2Spec.json()).info.version, "2.0.0");
  await page.getByRole("button", { name: /Up to six files v3 · legacy/i }).click();
  const v3Health = await page.request.get(`${base}/api/v3/health`);
  assert.equal(v3Health.status(), 200);
  assert.equal((await v3Health.json()).protocol, "DELIVERYOS_PACKAGES_V3");
  await page.getByRole("button", { name: /Up to six files v4 · current/i }).click();
  const v4Health = await page.request.get(`${base}/api/v4/health`);
  assert.equal(v4Health.status(), 200);
  assert.equal((await v4Health.json()).protocol, "DELIVERYOS_PACKAGES_V4");
  const manifest = "https://raw.githubusercontent.com/Leokings/deliveryos/d8a674033c477f0d2bcae59ab8049cb2bdd86e37/examples/package_v2/package.json";
  const prefix = "https://raw.githubusercontent.com/Leokings/deliveryos/";
  const preflight = await page.request.get(`${base}/api/v4/packages/preflight?url=${encodeURIComponent(manifest)}&prefix=${encodeURIComponent(prefix)}&criteria=2`);
  assert.equal(preflight.status(), 200);
  assert.equal((await preflight.json()).file_count, 2);
  await page.screenshot({ path: "artifacts/packages-desktop.png", fullPage: true });

  const walletPage = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await walletPage.addInitScript(() => {
    let chain = "0x1";
    window.ethereum = {
      request: async ({ method, params }) => {
        if (method === "eth_requestAccounts") return ["0x1111111111111111111111111111111111111111"];
        if (method === "eth_chainId") return chain;
        if (method === "wallet_switchEthereumChain") { chain = params[0].chainId; return null; }
        throw new Error(`Unexpected wallet method ${method}`);
      },
    };
  });
  await walletPage.goto(base, { waitUntil: "networkidle" });
  await walletPage.getByRole("button", { name: "Connect wallet" }).click();
  await walletPage.getByRole("button", { name: /Browser wallet · 0x111/ }).waitFor();
  assert.equal(await walletPage.evaluate(() => window.ethereum.request({ method: "eth_chainId" })), "0xf22f");
  await walletPage.close();

  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  mobile.on("pageerror", (error) => errors.push(error.message));
  await mobile.goto(base, { waitUntil: "networkidle" });
  await mobile.locator(".handoff-row").last().evaluate((element) => Promise.all(
    element.getAnimations().map((animation) => animation.finished)));
  await mobile.screenshot({ path: "artifacts/mobile.png", fullPage: true });
  assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), true, "mobile page must not overflow horizontally");
  const reduced = await browser.newPage({ reducedMotion: "reduce" });
  await reduced.goto(base, { waitUntil: "networkidle" });
  assert.equal(await reduced.locator(".live-pulse").first().evaluate((el) => getComputedStyle(el).animationName), "none");
  await reduced.close();
  assert.deepEqual(errors, [], `browser errors: ${errors.join(", ")}`);
  console.log("PASS v4-first UI, no initial recent-job RPC, real review proof, share/deep-link handoff, missing-job 404 and stale-state recovery, form defaults, agent setup, API discovery, v1/v2/v3 legacy, v4 package preflight, mocked wallet switch, mobile width, reduced motion, no page errors");
  console.log(`Screenshots: artifacts/desktop.png and artifacts/mobile.png (${base})`);
} finally {
  await browser.close();
}
