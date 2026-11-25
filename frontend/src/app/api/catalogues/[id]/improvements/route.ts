const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function proxy(request: Request, id: string, method: string) {
  const cookie = request.headers.get("cookie") || "";
  const query = new URL(request.url).searchParams.toString();
  const body = method === "GET" ? undefined : await request.text();
  const headers: Record<string, string> = { cookie };
  if (body) {
    headers["Content-Type"] = request.headers.get("Content-Type") || "application/json";
  }
  const response = await fetch(
    `${API_URL}/catalogues/${encodeURIComponent(id)}/improvements${query ? `?${query}` : ""}`,
    { method, headers, body },
  );
  const text = await response.text();
  return new Response(text, {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") || "application/json" },
  });
}

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  try {
    return await proxy(request, id, "GET");
  } catch {
    return Response.json({ detail: "The CatalogForge API is unavailable." }, { status: 503 });
  }
}

export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  try {
    return await proxy(request, id, "POST");
  } catch {
    return Response.json({ detail: "The CatalogForge API is unavailable." }, { status: 503 });
  }
}
