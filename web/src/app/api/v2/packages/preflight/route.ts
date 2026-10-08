import { badRequest, publicJson, publicOptions } from "@/lib/http";
import { verifyPublicPackage } from "@/lib/package";

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const url = params.get("url");
  const prefix = params.get("prefix");
  const criteria = params.get("criteria");
  if (!url || !prefix || !criteria || !/^[1-4]$/.test(criteria)) {
    return badRequest("Provide url, approved repository prefix, and 1-4 criteria.");
  }
  try {
    return publicJson(await verifyPublicPackage(url, prefix, Number(criteria)));
  } catch (error) {
    const message = error instanceof Error ? error.message : "Package preflight failed.";
    if (message.includes("fetch failed") || message.includes("timeout")) {
      console.error("DeliveryOS v2 package upstream error", error);
      return publicJson({ error: "The public evidence source is temporarily unavailable." }, 503);
    }
    return publicJson({ error: message }, 422);
  }
}

export const OPTIONS = publicOptions;
