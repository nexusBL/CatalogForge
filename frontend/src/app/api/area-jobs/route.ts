import { NextResponse } from "next/server";

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function proxy(request: Request, path: string, method = request.method) {
  const cookie = request.headers.get("cookie") || "";
  const query = new URL(request.url).searchParams.toString();
  const url = `${API_URL}${path}${query ? `?${query}` : ""}`;
  try {
    const init: RequestInit = { method, headers: { cookie }, cache: "no-store" };
    if (method !== "GET" && method !== "HEAD") {
      init.headers = { ...init.headers, "Content-Type": "application/json" };
      init.body = await request.text();
    }
    const response = await fetch(url, init);
    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") || "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "The CatalogForge API is unavailable." }, { status: 503 });
  }
}

export async function GET(request: Request) {
  return proxy(request, "/area-jobs");
}

export async function POST(request: Request) {
  return proxy(request, "/area-jobs");
}
