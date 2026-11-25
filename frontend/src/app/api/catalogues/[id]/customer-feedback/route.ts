const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  try {
    const cookie = request.headers.get("cookie") || "";
    const query = new URL(request.url).searchParams.toString();
    const contentType = request.headers.get("Content-Type") || "";
    const headers: Record<string, string> = { cookie };
    let body: ArrayBuffer | string | undefined;
    if (contentType.includes("multipart/form-data")) {
      headers["Content-Type"] = contentType;
      body = await request.arrayBuffer();
    } else {
      body = await request.text();
      if (body) {
        headers["Content-Type"] = contentType || "application/json";
      }
    }
    const response = await fetch(
      `${API_URL}/catalogues/${encodeURIComponent(id)}/customer-feedback${query ? `?${query}` : ""}`,
      { method: "POST", headers, body },
    );
    const text = await response.text();
    return new Response(text, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") || "application/json" },
    });
  } catch {
    return Response.json({ detail: "The CatalogForge API is unavailable." }, { status: 503 });
  }
}
