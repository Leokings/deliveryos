import { getPassportContractAddress, readProviderProfile, readProviderReceipt } from "@/lib/chain";
import { publicJson, publicOptions, upstreamError } from "@/lib/http";
import { ADDRESS_PATTERN } from "@/lib/protocol";
import { lookupPassport } from "@/lib/passport";

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
    return publicJson(await lookupPassport(wallet as `0x${string}`, Number(rawLimit), passport, {
      profile: readProviderProfile, receipt: readProviderReceipt,
    }));
  } catch (error) {
    return upstreamError("provider passport", error);
  }
}

export const OPTIONS = publicOptions;
