import { readJobCount } from "@/lib/chain";
import { publicJson, publicOptions, upstreamError } from "@/lib/http";
import { CHAIN_ID, CONTRACT_ADDRESS, NETWORK } from "@/lib/protocol";

export async function GET() {
  try {
    const jobCount = await readJobCount();
    return publicJson({ status: "ok", network: NETWORK, chain_id: CHAIN_ID, contract_address: CONTRACT_ADDRESS, job_count: jobCount });
  } catch (error) {
    return upstreamError("health", error);
  }
}

export const OPTIONS = publicOptions;
