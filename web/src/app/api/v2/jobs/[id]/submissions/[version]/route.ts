import { readSubmission } from "@/lib/chain";
import { badRequest, publicJson, publicOptions, upstreamError } from "@/lib/http";
import { JOB_ID_PATTERN, PACKAGES_CONTRACT_ADDRESS } from "@/lib/protocol";

export async function GET(_request: Request,
  context: { params: Promise<{ id: string; version: string }> }) {
  const { id, version } = await context.params;
  if (!JOB_ID_PATTERN.test(id) || !/^[1-9][0-9]{0,3}$/.test(version)) {
    return badRequest("Provide a valid job ID and positive version number.");
  }
  try { return publicJson(await readSubmission(id, Number(version), PACKAGES_CONTRACT_ADDRESS)); }
  catch (error) { return upstreamError("v2 submission", error); }
}

export const OPTIONS = publicOptions;
