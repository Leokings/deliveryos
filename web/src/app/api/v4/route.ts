import { publicJson, publicOptions } from "@/lib/http";
import { PACKAGES_V4_CONTRACT_ADDRESS } from "@/lib/protocol";

export function GET() {
  return publicJson({
    protocol: "DELIVERYOS_PACKAGES_V4",
    network: "studionet",
    chain_id: 61999,
    contract_address: PACKAGES_V4_CONTRACT_ADDRESS,
    read_endpoints: ["/api/v4/health", "/api/v4/jobs", "/api/v4/jobs/{id}",
      "/api/v4/jobs/{id}/submissions/{version}", "/api/v4/packages/preflight",
      "/api/transactions/{hash}", "/api/v4/openapi"],
    writes: "Buyer/provider wallet signatures are required. No API-key-only write endpoint exists.",
  });
}

export const OPTIONS = publicOptions;
