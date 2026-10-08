import { readJob, readJobCount, readJobId } from "@/lib/chain";
import { badRequest, publicOptions, publicRecentJobs, upstreamError } from "@/lib/http";
import { PACKAGES_CONTRACT_ADDRESS } from "@/lib/protocol";

export async function GET(request: Request) {
  const rawLimit = new URL(request.url).searchParams.get("limit") ?? "5";
  if (!/^[1-5]$/.test(rawLimit)) return badRequest("limit must be an integer from 1 to 5.");
  try {
    const total = await readJobCount(PACKAGES_CONTRACT_ADDRESS);
    const jobs = [];
    for (let index = total - 1; index >= Math.max(0, total - Number(rawLimit)); index--) {
      const id = await readJobId(index, PACKAGES_CONTRACT_ADDRESS);
      jobs.push(await readJob(id, PACKAGES_CONTRACT_ADDRESS));
    }
    return publicRecentJobs({ total, jobs });
  } catch (error) { return upstreamError("v2 jobs", error); }
}

export const OPTIONS = publicOptions;
