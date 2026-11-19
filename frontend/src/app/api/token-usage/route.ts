import { NextRequest, NextResponse } from "next/server";
import { createTextProxyResponse, fetchBackend } from "@/server/backend-api";
import { getServerSession } from "@/server/session";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const session = await getServerSession();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const days = searchParams.get("days") || "30";

  const upstream = await fetchBackend(`/token-usage/summary?days=${encodeURIComponent(days)}`, {
    method: "GET",
    userId: session.user.id,
    cache: "no-store",
  });

  return createTextProxyResponse(upstream);
}
