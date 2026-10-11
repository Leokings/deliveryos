import { getPassportContractAddress, readProviderProfile, readProviderReceipt } from "@/lib/chain";
import { publicJson, publicOptions, upstreamError } from "@/lib/http";
import { ADDRESS_PATTERN } from "@/lib/protocol";

function jsonSafe(value: unknown) {
  return JSON.parse(JSON.stringify(value, (_key, item) =>
    typeof item === "bigint" ? item.toString() : item,
  ));
}

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const wallet = params.get("wallet") ?? "";
  const rawLimit = params.get("limit") ?? "5";
  if (!ADDRESS_PATTERN.test(wallet)) {
    return publicJson({ error: "wallet must be a 0x-prefixed 20-byte address." }, 400);
  }
  if (!/^(?:[1-9]|10)$/.test(rawLimit)) {
    return publicJson({ error: "limit must be an integer from 1 to 10." }, 400);
  }

  let passport: `0x${string}` | null;
  try {
    passport = getPassportContractAddress();
  } catch {
    return publicJson({ error: "Provider Passport address is misconfigured." }, 503);
  }
  if (!passport) {
    return publicJson({ error: "Provider Passport is not deployed or configured yet." }, 503);
  }

  try {
    const profile = jsonSafe(await readProviderProfile(wallet as `0x${string}`, passport)) as {
      receipt_count?: number | string;
    };
    const count = Number(profile.receipt_count ?? 0);
    if (!Number.isSafeInteger(count) || count < 0) throw new Error("Invalid receipt count returned by Passport");
    const start = Math.max(0, count - Number(rawLimit));
    const receipts = [];
    for (let index = count - 1; index >= start; index--) {
      receipts.push(jsonSafe(await readProviderReceipt(wallet as `0x${string}`, index, passport)));
    }
    return publicJson({
      network: "studionet",
      chain_id: 61999,
      passport_contract_address: passport,
      profile,
      receipt_count: count,
      receipts,
      receipts_returned: receipts.length,
      order: "newest_first",
    });
  } catch (error) {
    return upstreamError("provider passport", error);
  }
}

export const OPTIONS = publicOptions;
