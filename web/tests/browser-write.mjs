/**
 * Opt-in live Studionet browser write test. Generates an ephemeral test wallet;
 * no secret is stored or funded. The EIP-1193 shim signs exactly what the UI
 * asks an injected wallet to sign, then relays the raw transaction to Studionet.
 */
import assert from "node:assert/strict";
import { chromium } from "playwright";
import { generatePrivateKey, privateKeyToAccount } from "viem/accounts";

const base = process.env.BASE_URL ?? "http://localhost:3001";
const version = process.env.DELIVERYOS_TEST_VERSION === "v2" ? "v2" : "v1";
const apiBase = version === "v2" ? "/api/v2" : "/api";
const rpcUrl = "https://studio.genlayer.com/api";
const account = privateKeyToAccount(generatePrivateKey());
const jobId = `${version}_browser_${crypto.randomUUID().replaceAll("-", "").slice(0, 16)}`;
const providerAddress = "0x1563915e194D8CfBA1943570603F7606A3115508";

async function rpc(method, params) {
  const response = await fetch(rpcUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  });
  const result = await response.json();
  if (result.error) throw new Error(`${method}: ${result.error.message}`);
  return result.result;
}

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 850 } });
  page.on("pageerror", (error) => console.error("PAGE ERROR", error.message));
  await page.exposeFunction("deliveryosSignTransaction", async (tx) => {
    const serialized = await account.signTransaction({
      type: "legacy",
      to: tx.to,
      data: tx.data,
      value: BigInt(tx.value ?? "0x0"),
      gas: BigInt(tx.gas),
      gasPrice: BigInt(tx.gasPrice),
      nonce: Number(BigInt(tx.nonce)),
      chainId: Number(BigInt(tx.chainId)),
    });
    const hash = await rpc("eth_sendRawTransaction", [serialized]);
    console.log("DELIVERYOS_BROWSER_TX", hash);
    return hash;
  });
  await page.addInitScript((address) => {
    let chain = "0x1";
    window.ethereum = {
      request: async ({ method, params }) => {
        if (method === "eth_requestAccounts") return [address];
        if (method === "eth_chainId") return chain;
        if (method === "wallet_switchEthereumChain") { chain = params[0].chainId; return null; }
        if (method === "eth_sendTransaction") return window.deliveryosSignTransaction(params[0]);
        throw new Error(`Unsupported test-wallet request: ${method}`);
      },
    };
  }, account.address);
  await page.goto(`${base}/?version=${version}`, { waitUntil: "networkidle" });
  if (version === "v2") await page.locator(".format-details").getByText(/up to 6 public files/i).waitFor();
  await page.getByRole("button", { name: "Connect wallet" }).click();
  await page.getByRole("button", { name: /Browser wallet ·/ }).waitFor();
  await page.getByRole("tab", { name: "Create request" }).click();
  await page.locator(".inline-input input").fill(jobId);
  await page.getByPlaceholder("0x…").fill(providerAddress);
  await page.getByPlaceholder(/Describe the finished result/).fill("Deliver the public Digital Deliverable Verifier installation guide with its actual install command.");
  await page.getByPlaceholder(/Includes a 200-word summary/).fill("The guide explicitly includes the command python -m pip install -r requirements.txt.");
  await page.getByPlaceholder("https://github.com/owner/repository").fill("https://github.com/Leokings/digital-deliverable-verifier");
  const due = new Date(Date.now() + 3 * 86400_000);
  const local = new Date(due.getTime() - due.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  await page.locator('input[type="datetime-local"]').fill(local);
  console.log("DELIVERYOS_BROWSER_JOB", jobId);
  await page.locator(".panel-main").getByRole("button", { name: /Create request/ }).click();
  await page.locator(".tx-line code, .alert-error").first().waitFor({ timeout: 60000 });
  const alert = page.locator(".alert-error");
  if (await alert.isVisible()) throw new Error(`UI write failed: ${await alert.innerText()}`);
  const displayed = await page.locator(".tx-line code").innerText();
  console.log("DELIVERYOS_BROWSER_BUYER", account.address);
  console.log("DELIVERYOS_BROWSER_TX_SHORT", displayed);
  await page.locator(".tx-good").waitFor({ timeout: 240000 });
  await page.getByRole("heading", { name: jobId }).waitFor({ timeout: 30000 });
  const job = await (await page.request.get(`${base}${apiBase}/jobs/${jobId}`)).json();
  assert.equal(job.status, "PROPOSED");
  assert.equal(job.protocol, version === "v2" ? "DELIVERYOS_PACKAGES_V2" : "DELIVERYOS_V1");
  assert.equal(job.buyer.toLowerCase(), account.address.toLowerCase());
  assert.equal(job.evidence_prefix, "https://raw.githubusercontent.com/Leokings/digital-deliverable-verifier/");
  await page.getByRole("button", { name: /Copy job link/ }).waitFor();
  console.log(`PASS ${version} browser EIP-1193 wallet signed a real Studionet job; finalized execution and chain state verified`);
} finally {
  await browser.close();
}
