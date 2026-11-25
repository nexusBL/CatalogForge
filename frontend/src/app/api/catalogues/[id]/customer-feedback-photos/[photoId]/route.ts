const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function GET(request: Request, context: { params: Promise<{ id: string; photoId: string }> }) {
  const { id, photoId } = await context.params;
  try {
    const cookie = request.headers.get("cookie") || "";
    const query = new URL(request.url).searchParams.toString();
    const response = await fetch(
      `${API_URL}/catalogues/${encodeURIComponent(id)}/customer-feedback-photos/${encodeURIComponent(photoId)}${query ? `?${query}` : ""}`,
      { method: "GET", headers: { cookie } },
    );
    const buffer = await response.arrayBuffer();
    return new Response(buffer, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") || "application/octet-stream" },
    });
  } catch {
    return Response.json({ detail: "The CatalogForge API is unavailable." }, { status: 503 });
  }
}
