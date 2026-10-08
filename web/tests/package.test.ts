import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { after, test } from "node:test";
import { verifyPublicPackage } from "../src/lib/package.ts";


const prefix = "https://raw.githubusercontent.com/Leokings/deliveryos/";
const source = "57d2030ae236590df08475d70296078b3efd4923";
const manifestCommit = "d8a674033c477f0d2bcae59ab8049cb2bdd86e37";
const manifestUrl = `${prefix}${manifestCommit}/examples/package_v2/package.json`;
const guideUrl = `${prefix}${source}/examples/package_v2/source/guide.md`;
const factsUrl = `${prefix}${source}/examples/package_v2/source/facts.json`;
const manifest = readFileSync(new URL("../../examples/package_v2/package.json", import.meta.url))
  .toString("utf-8").replaceAll("\r\n", "\n");
const guide = "# DeliveryOS package fixture\n\nInstall the example service with `python -m pip install -r requirements.txt`.\nAfter installation, run `python -m deliveryos_agent.mcp_server` to start its MCP endpoint.\n";
const facts = '{"install_command":"python -m pip install -r requirements.txt","verify_command":"python -m deliveryos_agent.mcp_server"}\n';
const originalFetch = globalThis.fetch;

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object).sort().map((key) => `${JSON.stringify(key)}:${canonical(object[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function mockFetch(overrides: Record<string, string> = {}) {
  const bodies: Record<string, string> = { [manifestUrl]: manifest, [guideUrl]: guide, [factsUrl]: facts, ...overrides };
  globalThis.fetch = async (input) => {
    const body = bodies[String(input)];
    return body === undefined ? new Response("Not found", { status: 404 }) : new Response(body, { status: 200 });
  };
}

after(() => { globalThis.fetch = originalFetch; });

test("v2 preflight verifies canonical manifest, both files, and fingerprint", async () => {
  mockFetch();
  const result = await verifyPublicPackage(manifestUrl, prefix, 2);
  assert.equal(result.sha256, "4b33e4b5f89d0c3772298c50431fed8f1bc78e641125f4eafec518c44192c083");
  assert.equal(result.file_count, 2);
  assert.equal(result.total_bytes, 320);
  assert.equal(result.content_fingerprint, "d5f1feb0b21032dc1ac85985cddfad7ace6a3c178b29840f1993e3c1292f0059");
});

test("v2 preflight rejects changed bytes and noncanonical JSON", async () => {
  mockFetch({ [guideUrl]: "forged" });
  await assert.rejects(verifyPublicPackage(manifestUrl, prefix, 2), /do not match/);
  mockFetch({ [manifestUrl]: JSON.stringify(JSON.parse(manifest), null, 2) + "\n" });
  await assert.rejects(verifyPublicPackage(manifestUrl, prefix, 2), /canonical JSON/);
});

test("v2 preflight rejects cross-commit and private-host references", async () => {
  const data = JSON.parse(manifest);
  data.files[0].url = `${prefix}${"f".repeat(40)}/guide.md`;
  mockFetch({ [manifestUrl]: canonical(data) + "\n" });
  await assert.rejects(verifyPublicPackage(manifestUrl, prefix, 2), /source commit/);
  await assert.rejects(verifyPublicPackage("https://localhost/private", prefix, 2));
});

test("v2 preflight rejects an invalid JSON artifact", async () => {
  const bad = "{not-json}";
  const data = JSON.parse(manifest);
  data.files[1].sha256 = createHash("sha256").update(bad).digest("hex");
  data.files[1].size_bytes = bad.length;
  mockFetch({ [manifestUrl]: canonical(data) + "\n", [factsUrl]: bad });
  await assert.rejects(verifyPublicPackage(manifestUrl, prefix, 2), /JSON file is invalid/);
});

test("v2 preflight accepts quoted CSV and rejects malformed or ragged CSV", async () => {
  const data = JSON.parse(manifest);
  data.files[1].media_type = "text/csv";
  for (const [csv, expected] of [
    ['name,value\n"foo, bar",1\n', null],
    ['name,value\n"foo, bar,1\n', /CSV quoting is malformed/],
    ['name,value\nfoo\n', /inconsistent columns/],
  ] as const) {
    data.files[1].sha256 = createHash("sha256").update(csv).digest("hex");
    data.files[1].size_bytes = Buffer.byteLength(csv);
    mockFetch({ [manifestUrl]: canonical(data) + "\n", [factsUrl]: csv });
    if (expected) await assert.rejects(verifyPublicPackage(manifestUrl, prefix, 2), expected);
    else assert.equal((await verifyPublicPackage(manifestUrl, prefix, 2)).file_count, 2);
  }
});
