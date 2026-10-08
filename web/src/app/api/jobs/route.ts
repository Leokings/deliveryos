import { readJob, readJobCount, readJobId } from "@/lib/chain";
import { badRequest, publicJson, publicOptions, upstreamError } from "@/lib/http";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const rawLimit = url.searchParams.get("limit") ?? "5";
  if (!/^[1-5]$/.test(rawLimit)) return badRequest("limit must be an integer from 1 to 5.");
  const limit = Number(rawLimit);
  try {
    const total = await readJobCount();
    const jobs = [];
    for (let index = total - 1; index >= Math.max(0, total - limit); index--) {
      const id = await readJobId(index);
      jobs.push(await readJob(id));
    }
    return publicJson({ total, jobs });
  } catch (error) {
    return upstreamError("jobs", error);
  }
}

export const OPTIONS = publicOptions;
