import { NextResponse } from "next/server";

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function POST(request: Request) {
  const cookie = request.headers.get("cookie") || "";
  let body: string;
  try {
    body = await request.text();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  try {
    const response = await fetch(`${API_URL}/catalog/create`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        cookie,
      },
      cache: "no-store",
      body,
    });
    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") || "application/json" },
    });
  } catch {
    return NextResponse.json(
      { detail: "The CatalogForge API is unavailable." },
      { status: 503 },
    );
  }
}
