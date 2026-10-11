import assert from "node:assert/strict";
import { test } from "node:test";
import { lookupPassport, PASSPORT_DEPLOYMENTS } from "../src/lib/passport.ts";

const wallet = ("0x" + "a".repeat(40)) as `0x${string}`;
const [active, legacy] = PASSPORT_DEPLOYMENTS;
function fixture(activeRegistered = true) {
  return {
    async profile(_wallet: string, address: string) {
      return { wallet, registered: address === legacy.passport_contract_address || activeRegistered,
        receipt_count: address === active.passport_contract_address ? 2n : 1n,
        display_name: address === active.passport_contract_address ? "Active" : "Legacy" };
    },
    async receipt(_wallet: string, index: number, address: string) {
      const deployment = address === active.passport_contract_address ? active : legacy;
      return { receipt_id: (address === active.passport_contract_address ? (index ? "b" : "a") : "c").repeat(64),
        source_contract: deployment.source_contract_address, provider: wallet,
        decided_epoch: address === active.passport_contract_address ? (index ? 10 : 30) : 20 };
    },
  };
}

test("Passport preserves both histories and immutable receipt fields", async () => {
  const reader = fixture();
  const result = await lookupPassport(wallet, 5, active.passport_contract_address, reader);
  assert.equal(result.receipt_count, 3);
  assert.equal(result.profile.display_name, "Active");
  assert.deepEqual(result.receipts.map((r) => r.decided_epoch), [30, 20, 10]);
  assert.deepEqual(result.receipts[2], await reader.receipt(wallet, 1, active.passport_contract_address));
  assert.equal(result.passport_deployments.length, 2);
  assert.match(result.order, /within_recently_recorded/);
});

test("Passport falls back to the registered legacy profile without losing active outcomes", async () => {
  const result = await lookupPassport(wallet, 5, active.passport_contract_address, fixture(false));
  assert.equal(result.profile.display_name, "Legacy");
  assert.equal(result.profile_passport_contract_address, legacy.passport_contract_address);
  assert.equal(result.profile.receipt_count, 3);
});

test("Passport bounds reads and explains late recovered decisions", async () => {
  let reads = 0;
  const reader = fixture();
  const result = await lookupPassport(wallet, 1, active.passport_contract_address, {
    ...reader, receipt: async (...args) => { reads++; return reader.receipt(...args); },
  });
  assert.equal(reads, 2);
  assert.equal(result.receipts_returned, 1);
  assert.equal(result.receipts[0].decided_epoch, 20);
  assert.match(result.selection, /late recovered/);
});

test("Passport fails closed on upstream errors, invalid counts or wrong provenance", async () => {
  const reader = fixture();
  await assert.rejects(lookupPassport(wallet, 5, active.passport_contract_address, {
    ...reader, profile: async () => { throw new Error("unavailable"); },
  }), /unavailable/);
  await assert.rejects(lookupPassport(wallet, 5, active.passport_contract_address, {
    ...reader, profile: async () => ({ wallet, registered: true, receipt_count: -1 }),
  }), /Invalid provider/);
  await assert.rejects(lookupPassport(wallet, 5, active.passport_contract_address, {
    ...reader, receipt: async () => ({ receipt_id: "a".repeat(64), source_contract: wallet,
      provider: wallet, decided_epoch: 10 }),
  }), /Invalid receipt/);
  await assert.rejects(lookupPassport(wallet, 5, wallet, reader), /Unsupported active/);
});
