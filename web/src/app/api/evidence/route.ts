import { createHash } from "node:crypto";
import { badRequest, publicJson, publicOptions, upstreamError } from "@/lib/http";
import { MAX_EVIDENCE_BYTES, validateEvidenceUrl } from "@/lib/protocol";

export async function GET(request: Request) {
  const raw = new URL(request.url).searchParams.get("url");
  if (!raw) return badRequest("A public, commit-pinned raw GitHub URL is required.");
  let url: URL;
  try {
    url = validateEvidenceUrl(raw);
  } catch (error) {
    return badRequest((error as Error).message);
  }
  try {
    const response = await fetch(url, {
      redirect: "error",
      headers: { "Accept-Encoding": "identity" },
      signal: AbortSignal.timeout(10000),
      cache: "no-store",
    });
    if (!response.ok || !response.body) {
      return publicJson({ error: `Evidence was not available (HTTP ${response.status}).` }, 422);
    }
    const reader = response.body.getReader();
    const chunks: Uint8Array[] = [];
    let total = 0;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        total += value.length;
        if (total > MAX_EVIDENCE_BYTES) {
          await reader.cancel();
          return publicJson({ error: "Evidence exceeds the 4,800-byte contract limit." }, 422);
        }
        chunks.push(value);
      }
    } finally {
      reader.releaseLock();
    }
    const body = Buffer.concat(chunks);
    if (!body.length) return publicJson({ error: "Evidence is empty." }, 422);
    const text = new TextDecoder("utf-8", { fatal: true }).decode(body);
    if (!text.trim()) return publicJson({ error: "Evidence has no text." }, 422);
    return publicJson({ url: url.href, sha256: createHash("sha256").update(body).digest("hex"), size_bytes: body.length });
  } catch (error) {
    return upstreamError("evidence", error);
  }
}

export const OPTIONS = publicOptions;
