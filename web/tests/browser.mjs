import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const base = process.env.BASE_URL ?? "http://localhost:3001";
const browser = await chromium.launch({ headless: true });
try {
  await mkdir("artifacts", { recursive: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const home = await page.goto(base, { waitUntil: "networkidle" });
  assert.equal(home.status(), 200);
  await page.getByRole("heading", { name: /Good work deserves/i }).waitFor();
  await page.screenshot({ path: "artifacts/desktop.png", fullPage: true });

  await page.getByRole("button", { name: "See a live decision" }).click();
  await page.getByRole("heading", { name: "deliveryos_cb5bcede778b4248" }).waitFor();
  assert.match(await page.locator(".job-detail").innerText(), /ACCEPTED/);
  assert.match(await page.locator(".job-detail").innerText(), /MET/);

  await page.getByRole("tab", { name: "Start a job" }).click();
  await page.getByRole("button", { name: "Create job" }).click();
  assert.match(await page.locator(".alert-error").innerText(), /Job ID/);
  await page.getByRole("button", { name: "Generate" }).click();
  assert.match(await page.locator(".inline-input input").inputValue(), /^job_[a-f0-9]{16}$/);

  await page.getByRole("tab", { name: "Agent API" }).click();
  assert.match(await page.locator(".api-disclaimer").innerText(), /API key by itself cannot authorize/);
  const spec = await page.request.get(`${base}/api/openapi`);
  assert.equal(spec.status(), 200);
  assert.equal((await spec.json()).openapi, "3.1.0");

  await page.getByRole("button", { name: /Evidence package v2/i }).click();
  await page.getByRole("button", { name: "See a live decision" }).click();
  await page.getByRole("heading", { name: "package_f2131d0cd28244b2" }).waitFor();
  assert.match(await page.locator(".job-detail").innerText(), /MET/);
  assert.match(await page.locator(".job-detail").innerText(), /2 files/);
  const v2Health = await page.request.get(`${base}/api/v2/health`);
  assert.equal(v2Health.status(), 200);
  assert.equal((await v2Health.json()).protocol, "DELIVERYOS_PACKAGES_V2");
  const v2Spec = await page.request.get(`${base}/api/v2/openapi`);
  assert.equal(v2Spec.status(), 200);
  assert.equal((await v2Spec.json()).info.version, "2.0.0");
  const manifest = "https://raw.githubusercontent.com/Leokings/deliveryos/d8a674033c477f0d2bcae59ab8049cb2bdd86e37/examples/package_v2/package.json";
  const prefix = "https://raw.githubusercontent.com/Leokings/deliveryos/";
  const preflight = await page.request.get(`${base}/api/v2/packages/preflight?url=${encodeURIComponent(manifest)}&prefix=${encodeURIComponent(prefix)}&criteria=2`);
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
  await mobile.screenshot({ path: "artifacts/mobile.png", fullPage: true });
  assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), true, "mobile page must not overflow horizontally");
  assert.deepEqual(errors, [], `browser errors: ${errors.join(", ")}`);
  console.log("PASS v1/v2 desktop render, live job detail, form validation, agent API, v2 package preflight, mocked wallet network switch, mobile width, no page errors");
  console.log(`Screenshots: artifacts/desktop.png and artifacts/mobile.png (${base})`);
} finally {
  await browser.close();
}
