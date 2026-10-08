import { publicJson, publicOptions } from "@/lib/http";
import { PACKAGES_CONTRACT_ADDRESS } from "@/lib/protocol";

export function GET() {
  return publicJson({
    protocol: "DELIVERYOS_PACKAGES_V2",
    network: "studionet",
    chain_id: 61999,
    contract_address: PACKAGES_CONTRACT_ADDRESS,
    read_endpoints: ["/api/v2/health", "/api/v2/jobs", "/api/v2/jobs/{id}",
      "/api/v2/jobs/{id}/submissions/{version}", "/api/v2/packages/preflight",
      "/api/transactions/{hash}", "/api/v2/openapi"],
    writes: "Buyer/provider wallet signatures are required. No API-key-only write endpoint exists.",
  });
}

export const OPTIONS = publicOptions;
