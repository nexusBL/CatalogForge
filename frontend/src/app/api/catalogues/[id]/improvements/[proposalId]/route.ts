const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function GET(request: Request, context: { params: Promise<{ id: string; proposalId: string }> }) {
  const { id, proposalId } = await context.params;
  try {
    const cookie = request.headers.get("cookie") || "";
    const query = new URL(request.url).searchParams.toString();
    const response = await fetch(
      `${API_URL}/catalogues/${encodeURIComponent(id)}/improvements/${encodeURIComponent(proposalId)}${query ? `?${query}` : ""}`,
      { method: "GET", headers: { cookie } },
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
