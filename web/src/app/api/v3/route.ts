import { publicJson, publicOptions } from "@/lib/http";
import { PACKAGES_V3_CONTRACT_ADDRESS } from "@/lib/protocol";

export function GET() {
  return publicJson({
    protocol: "DELIVERYOS_PACKAGES_V3",
    network: "studionet",
    chain_id: 61999,
    contract_address: PACKAGES_V3_CONTRACT_ADDRESS,
    read_endpoints: ["/api/v3/health", "/api/v3/jobs", "/api/v3/jobs/{id}",
      "/api/v3/jobs/{id}/submissions/{version}", "/api/v3/packages/preflight",
      "/api/transactions/{hash}", "/api/v3/openapi"],
    writes: "Buyer/provider wallet signatures are required. No API-key-only write endpoint exists.",
  });
}

export const OPTIONS = publicOptions;
