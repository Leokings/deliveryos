export const publicHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Cache-Control": "no-store",
};

export function publicJson(data: unknown, status = 200) {
  return Response.json(data, { status, headers: publicHeaders });
}

// Recent jobs are identical for every visitor. Cache only successful list
// responses at Vercel's CDN; individual job reads remain uncached and fresh.
export function publicRecentJobs(data: unknown) {
  return Response.json(data, { headers: {
    ...publicHeaders,
    "Vercel-CDN-Cache-Control": "public, s-maxage=30, stale-while-revalidate=90",
  } });
}

export function badRequest(message: string) {
  return publicJson({ error: message }, 400);
}

export function notFound(resource: string) {
  return publicJson({ error: `${resource} was not found on this contract.` }, 404);
}

// Studionet's gen_call currently returns a generic -32000 "execution failed"
// for a UserError raised by get_job/get_submission. Restrict this test to
// those pure views at the call site; a transport failure must remain a 503.
export function isMissingViewError(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const value = error as { name?: unknown; code?: unknown; details?: unknown; cause?: unknown };
  const cause = value.cause as { message?: unknown } | undefined;
  return value.name === "InvalidInputRpcError" && value.code === -32000
    && value.details === "execution failed" && cause?.message === "execution failed";
}

export function upstreamError(area: string, error: unknown) {
  console.error(`DeliveryOS ${area} upstream error`, error);
  const message = error instanceof Error ? error.message : String(error);
  if (/rate limit exceeded|\b-32029\b|\b429\b/i.test(message)) {
    return publicJson({ error: "Studionet's hourly request limit was reached. Check transaction or job state before retrying later." }, 429);
  }
  return publicJson({ error: "Studionet is unavailable or did not return the requested state. Try again shortly." }, 503);
}

export function publicOptions() {
  return new Response(null, { status: 204, headers: publicHeaders });
}
