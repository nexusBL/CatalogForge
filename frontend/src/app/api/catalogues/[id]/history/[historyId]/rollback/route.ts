const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function POST(request: Request, context: { params: Promise<{ id: string; historyId: string }> }) {
  const { id, historyId } = await context.params;
  const cookie = request.headers.get("cookie") || "";
  const query = new URL(request.url).searchParams.toString();
  try {
    const response = await fetch(
      `${API_URL}/catalogues/${encodeURIComponent(id)}/history/${encodeURIComponent(historyId)}/rollback${query ? `?${query}` : ""}`,
      {
        method: "POST",
        headers: { cookie, "Content-Type": request.headers.get("Content-Type") || "application/json" },
        body: await request.text(),
      },
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
