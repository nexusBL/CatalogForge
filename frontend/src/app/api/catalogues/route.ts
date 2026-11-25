import { NextResponse } from "next/server";

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function GET(request: Request) {
  const cookie = request.headers.get("cookie") || "";
  const query = new URL(request.url).searchParams.toString();
  try {
    const response = await fetch(`${API_URL}/catalogues${query ? `?${query}` : ""}`, {
      headers: { cookie },
    });
    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") || "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "The CatalogForge API is unavailable." }, { status: 503 });
  }
}
