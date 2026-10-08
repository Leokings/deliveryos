import { publicJson, publicOptions } from "@/lib/http";
import { CHAIN_ID, CONTRACT_ADDRESS, NETWORK } from "@/lib/protocol";

export function GET() {
  return publicJson({
    name: "DeliveryOS read API",
    network: NETWORK,
    chain_id: CHAIN_ID,
    contract_address: CONTRACT_ADDRESS,
    write_access: "Wallet-signed GenLayer transactions only. The public HTTP API never holds a signing key.",
    endpoints: {
      health: "/api/health",
      jobs: "/api/jobs?limit=5",
      job: "/api/jobs/{job_id}",
      submission: "/api/jobs/{job_id}/submissions/{version}",
      transaction: "/api/transactions/{transaction_hash}",
      evidence: "/api/evidence?url={commit_pinned_raw_github_url}",
      openapi: "/api/openapi",
    },
  });
}

export const OPTIONS = publicOptions;
