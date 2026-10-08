import { createClient } from "genlayer-js";
import { studionet } from "genlayer-js/chains";
import { TransactionHashVariant, type TransactionHash } from "genlayer-js/types";
import { CONTRACT_ADDRESS, type Job, type Submission } from "./protocol";

const client = createClient({ chain: studionet });

export async function readJob(jobId: string): Promise<Job> {
  return await client.readContract({
    address: CONTRACT_ADDRESS,
    functionName: "get_job",
    args: [jobId],
    transactionHashVariant: TransactionHashVariant.LATEST_FINAL,
  }) as Job;
}

export async function readSubmission(jobId: string, version: number): Promise<Submission> {
  return await client.readContract({
    address: CONTRACT_ADDRESS,
    functionName: "get_submission",
    args: [jobId, version],
    transactionHashVariant: TransactionHashVariant.LATEST_FINAL,
  }) as Submission;
}

export async function readJobCount(): Promise<number> {
  const value = await client.readContract({
    address: CONTRACT_ADDRESS,
    functionName: "get_job_count",
    args: [],
    transactionHashVariant: TransactionHashVariant.LATEST_FINAL,
  });
  return Number(value);
}

export async function readJobId(index: number): Promise<string> {
  return await client.readContract({
    address: CONTRACT_ADDRESS,
    functionName: "get_job_id",
    args: [index],
    transactionHashVariant: TransactionHashVariant.LATEST_FINAL,
  }) as string;
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
