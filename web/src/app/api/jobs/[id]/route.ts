import { readJob } from "@/lib/chain";
import { badRequest, isMissingViewError, notFound, publicJson, publicOptions, upstreamError } from "@/lib/http";
import { JOB_ID_PATTERN } from "@/lib/protocol";

export async function GET(_request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!JOB_ID_PATTERN.test(id)) return badRequest("Job ID must be 8-64 letters, digits, underscores or hyphens.");
  try {
    return publicJson(await readJob(id));
  } catch (error) {
    return isMissingViewError(error) ? notFound("Job") : upstreamError("job", error);
  }
}

export const OPTIONS = publicOptions;
