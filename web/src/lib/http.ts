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

export function upstreamError(area: string, error: unknown) {
  console.error(`DeliveryOS ${area} upstream error`, error);
  return publicJson({ error: "Studionet is unavailable or did not return the requested state. Try again shortly." }, 503);
}

export function publicOptions() {
  return new Response(null, { status: 204, headers: publicHeaders });
}
