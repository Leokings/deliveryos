import { createClient } from "genlayer-js";
import { studionet } from "genlayer-js/chains";
import { TransactionHashVariant, type TransactionHash } from "genlayer-js/types";
import { CONTRACT_ADDRESS, type Job, type Submission } from "./protocol";

const client = createClient({ chain: studionet });

export async function readJob(jobId: string, address: `0x${string}` = CONTRACT_ADDRESS): Promise<Job> {
  return await client.readContract({
    address,
    functionName: "get_job",
    args: [jobId],
    transactionHashVariant: TransactionHashVariant.LATEST_FINAL,
  }) as Job;
}

export async function readSubmission(jobId: string, version: number, address: `0x${string}` = CONTRACT_ADDRESS): Promise<Submission> {
  return await client.readContract({
    address,
    functionName: "get_submission",
    args: [jobId, version],
    transactionHashVariant: TransactionHashVariant.LATEST_FINAL,
  }) as Submission;
}

export async function readJobCount(address: `0x${string}` = CONTRACT_ADDRESS): Promise<number> {
  const value = await client.readContract({
    address,
    functionName: "get_job_count",
    args: [],
    transactionHashVariant: TransactionHashVariant.LATEST_FINAL,
  });
  return Number(value);
}

export async function readJobId(index: number, address: `0x${string}` = CONTRACT_ADDRESS): Promise<string> {
  return await client.readContract({
    address,
    functionName: "get_job_id",
    args: [index],
    transactionHashVariant: TransactionHashVariant.LATEST_FINAL,
  }) as string;
}

/** Provider Passport is a separately deployed V5/V6 companion contract. */
export function getPassportContractAddress(): `0x${string}` | null {
  const address = process.env.DELIVERYOS_PASSPORT_ADDRESS;
  if (!address) return null;
  if (!/^0x(?!0{40}$)[0-9a-fA-F]{40}$/.test(address)) {
    throw new Error("DELIVERYOS_PASSPORT_ADDRESS must be a 20-byte contract address");
  }
  return address as `0x${string}`;
}

export async function readProviderProfile(wallet: `0x${string}`, passport: `0x${string}`) {
  return await client.readContract({
    address: passport,
    functionName: "get_provider_profile",
    args: [wallet],
    transactionHashVariant: TransactionHashVariant.LATEST_FINAL,
  });
}

export async function readProviderReceipt(wallet: `0x${string}`, index: number, passport: `0x${string}`) {
  return await client.readContract({
    address: passport,
    functionName: "get_provider_receipt",
    args: [wallet, index],
    transactionHashVariant: TransactionHashVariant.LATEST_FINAL,
  });
}

export async function readTransaction(hash: TransactionHash) {
  const tx = await client.getTransaction({ hash });
  // The stable SDK exposes the raw Studionet receipt as well as decoded fields.
  // Check the leader's execution result: FINALIZED alone also covers reverts.
  const raw = tx as typeof tx & {
    result_name?: string;
    consensus_data?: { leader_receipt?: Array<{ execution_result?: string }> };
  };
  const consensus = raw.result_name ?? tx.resultName ?? "UNKNOWN";
  const execution = raw.consensus_data?.leader_receipt?.[0]?.execution_result
    ?? tx.txExecutionResultName ?? "UNKNOWN";
  return {
    transaction_hash: hash,
    status: tx.statusName ?? "UNKNOWN",
    consensus_result: consensus,
    execution_result: execution,
    finalized_success: tx.statusName === "FINALIZED"
      && (consensus === "AGREE" || consensus === "MAJORITY_AGREE")
      && (execution === "SUCCESS" || execution === "FINISHED_WITH_RETURN"),
  };
}
