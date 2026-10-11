export type PassportDeployment = {
  passport_contract_address: `0x${string}`;
  source_contract_address: `0x${string}`;
  protocol: string;
};

export const PASSPORT_DEPLOYMENTS: PassportDeployment[] = [
  {
    passport_contract_address: "0x821070E1254bB22e23DC80D06a5b6E6C198b0176",
    source_contract_address: "0x1eA0dfc62647353aFf10657B5eD0319cC0Eb5D7E",
    protocol: "DELIVERYOS_PACKAGES_V6",
  },
  {
    passport_contract_address: "0x238df7427B425347648fDA8A62aff6FB3f4871e4",
    source_contract_address: "0xde76b4a05B28Aa6fee5250C87aAefACee1cf1A9E",
    protocol: "DELIVERYOS_PACKAGES_V5",
  },
];

type Profile = { wallet: string; registered: boolean; display_name: string; receipt_count: number | string; [key: string]: unknown };
type Receipt = { receipt_id: string; source_contract: string; provider: string; decided_epoch: number; [key: string]: unknown };
type Reader = {
  profile(wallet: `0x${string}`, address: `0x${string}`): Promise<unknown>;
  receipt(wallet: `0x${string}`, index: number, address: `0x${string}`): Promise<unknown>;
};

function jsonSafe<T>(value: unknown): T {
  return JSON.parse(JSON.stringify(value, (_key, item) => typeof item === "bigint" ? item.toString() : item)) as T;
}

export async function lookupPassport(wallet: `0x${string}`, limit: number,
  active: `0x${string}`, reader: Reader) {
  const selected = PASSPORT_DEPLOYMENTS.find((item) => item.passport_contract_address.toLowerCase() === active.toLowerCase());
  if (!selected) throw new Error("Unsupported active Passport deployment");
  const deployments = [selected, ...PASSPORT_DEPLOYMENTS.filter((item) => item !== selected)];
  const profiles: Profile[] = [];
  const receipts: Receipt[] = [];
  const metadata: Array<PassportDeployment & { receipt_count: number }> = [];
  let total = 0;
  for (const deployment of deployments) {
    const profile = jsonSafe<Profile>(await reader.profile(wallet, deployment.passport_contract_address));
    const count = Number(profile.receipt_count);
    if (!Number.isSafeInteger(count) || count < 0 || typeof profile.registered !== "boolean"
        || profile.wallet.toLowerCase() !== wallet.toLowerCase()) {
      throw new Error("Invalid provider profile returned by Passport");
    }
    profiles.push(profile);
    total += count;
    if (!Number.isSafeInteger(total)) throw new Error("Invalid total receipt count");
    metadata.push({ ...deployment, receipt_count: count });
    for (let index = count - 1; index >= Math.max(0, count - limit); index--) {
      const receipt = jsonSafe<Receipt>(await reader.receipt(wallet, index, deployment.passport_contract_address));
      if (!/^[0-9a-f]{64}$/.test(receipt.receipt_id)
          || receipt.source_contract.toLowerCase() !== deployment.source_contract_address.toLowerCase()
          || receipt.provider.toLowerCase() !== wallet.toLowerCase()
          || !Number.isSafeInteger(receipt.decided_epoch) || receipt.decided_epoch <= 0) {
        throw new Error("Invalid receipt returned by Passport");
      }
      // Keep immutable receipt bytes/fields intact. Provenance is separate metadata.
      receipts.push(receipt);
    }
  }
  const chosenProfile = Math.max(0, profiles.findIndex((profile) => profile.registered));
  receipts.sort((a, b) => b.decided_epoch - a.decided_epoch || a.receipt_id.localeCompare(b.receipt_id));
  return {
    network: "studionet", chain_id: 61999, passport_contract_address: active,
    profile_passport_contract_address: deployments[chosenProfile].passport_contract_address,
    passport_deployments: metadata,
    profile: { ...profiles[chosenProfile], receipt_count: total },
    receipt_count: total, receipts: receipts.slice(0, limit),
    receipts_returned: Math.min(limit, receipts.length),
    order: "decision_time_descending_within_recently_recorded",
    selection: "Latest recorded entries per registry, bounded by limit; late recovered older decisions may appear.",
  };
}
