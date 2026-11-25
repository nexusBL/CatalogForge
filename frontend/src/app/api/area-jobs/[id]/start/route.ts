import { NextResponse } from "next/server";

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const cookie = request.headers.get("cookie") || "";
  try {
    const response = await fetch(`${API_URL}/area-jobs/${encodeURIComponent(id)}/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json", cookie },
      cache: "no-store",
      body: await request.text(),
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
