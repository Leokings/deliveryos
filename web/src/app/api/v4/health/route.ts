import { readJobCount } from "@/lib/chain";
import { publicJson, publicOptions, upstreamError } from "@/lib/http";
import { PACKAGES_V4_CONTRACT_ADDRESS } from "@/lib/protocol";

export async function GET() {
  try {
    return publicJson({ status: "ok", protocol: "DELIVERYOS_PACKAGES_V4", network: "studionet",
      chain_id: 61999, contract_address: PACKAGES_V4_CONTRACT_ADDRESS,
      job_count: await readJobCount(PACKAGES_V4_CONTRACT_ADDRESS) });
  } catch (error) { return upstreamError("v4 health", error); }
}

export const OPTIONS = publicOptions;
