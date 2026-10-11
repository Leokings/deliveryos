import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const base = process.env.BASE_URL ?? "http://localhost:3001";
const wallet = "0x1563915e194d8cfba1943570603f7606a3115508";
const legacyWallet = "0xa7D72Fbbe2B148187512A0534Aef62A11f92faFE";
const source = "0x1ea0dfc62647353aff10657b5ed0319cc0eb5d7e";
const activePassport = "0x821070E1254bB22e23DC80D06a5b6E6C198b0176";
const browser = await chromium.launch({ headless: true });
function canonical(value) {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value && typeof value === "object") return "{" + Object.keys(value).sort()
    .map((key) => JSON.stringify(key) + ":" + canonical(value[key])).join(",") + "}";
  return JSON.stringify(value);
}
try {
  await mkdir("artifacts", { recursive: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const response = await page.request.get(base + "/api/passport?wallet=" + wallet);
  assert.equal(response.status(), 200);
  assert.equal(response.headers()["access-control-allow-origin"], "*");
  assert.equal(response.headers()["cache-control"], "no-store");
  const body = await response.json();
  assert.equal(body.passport_contract_address, activePassport);
  assert.equal(body.passport_deployments.length, 2);
  const receipt = body.receipts.find((item) => item.source_contract === source);
  assert.ok(receipt, "The finalized production V6 receipt must be visible");
  const { receipt_id, ...fields } = receipt;
  assert.equal(createHash("sha256").update(canonical(fields)).digest("hex"), receipt_id);
  assert.equal(receipt.verdict, "ACCEPTED");
  assert.deepEqual(receipt.criterion_statuses, ["MET", "MET"]);
  const legacy = await page.request.get(base + "/api/passport?wallet=" + legacyWallet);
  assert.equal(legacy.status(), 200);
  const legacyBody = await legacy.json();
  assert.ok(legacyBody.receipts.some((item) => item.receipt_id ===
    "4117ee65032fb4456f31f27ebd8b7b169dd09fc156d64271a4d623908d7782a0"),
    "The original V5 receipt must still be visible");
  assert.equal((await page.request.get(base + "/api/passport?wallet=0x" + "0".repeat(40))).status(), 400);
  assert.equal((await page.request.get(base + "/api/passport?wallet=" + wallet + "&limit=11")).status(), 400);
  await page.goto(base + "/passport?wallet=" + wallet, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: receipt.job_id + " · version 1" }).waitFor();
  assert.match(await page.locator(".passport-results").innerText(), /ACCEPTED/);
  assert.match(await page.locator(".passport-hero").innerText(), /V5 and V6/);
  assert.equal(await page.getByRole("button", { name: "Connect wallet" }).count(), 0,
    "Public lookup must not need wallet authorization");
  await page.screenshot({ path: "artifacts/passport-v6-desktop.png", fullPage: true });
  await page.locator("#passport-wallet").fill("not-an-address");
  await page.getByRole("button", { name: "Look up" }).click();
  assert.match(await page.locator(".passport-alert").innerText(), /valid/);
  assert.equal(await page.locator(".passport-results").count(), 0);
  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
  mobile.on("pageerror", (error) => errors.push(error.message));
  await mobile.goto(base + "/passport?wallet=" + legacyWallet, { waitUntil: "networkidle" });
  await mobile.getByRole("heading", { name: /passport_smoke_20261011/ }).waitFor();
  assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
  await mobile.screenshot({ path: "artifacts/passport-v5-preserved-mobile.png", fullPage: true });
  assert.deepEqual(errors, []);
  console.log("PASS production V6 receipt, recomputed ID, preserved V5 history, public API headers, invalid inputs, no-wallet lookup, desktop/mobile rendering, stale-state clearing, no page errors");
  console.log(JSON.stringify({ base, job_id: receipt.job_id, receipt_id, receipt_count: body.receipt_count,
    legacy_receipt_count: legacyBody.receipt_count, active_passport: body.passport_contract_address }));
} finally {
  await browser.close();
}
