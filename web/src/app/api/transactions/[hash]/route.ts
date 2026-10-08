import { readTransaction } from "@/lib/chain";
import { badRequest, publicJson, publicOptions, upstreamError } from "@/lib/http";
import { TX_HASH_PATTERN } from "@/lib/protocol";
import type { TransactionHash } from "genlayer-js/types";

export async function GET(_request: Request, context: { params: Promise<{ hash: string }> }) {
  const { hash } = await context.params;
  if (!TX_HASH_PATTERN.test(hash)) return badRequest("Transaction hash must be a 0x-prefixed 32-byte hash.");
  try {
    return publicJson(await readTransaction(hash as TransactionHash));
  } catch (error) {
    return upstreamError("transaction", error);
  }
}

export const OPTIONS = publicOptions;
