const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function proxyCatalogue(request: Request, id: string, suffix: string, method = "GET") {
  const cookie = request.headers.get("cookie") || "";
  const query = new URL(request.url).searchParams.toString();
  const response = await fetch(
    `${API_URL}/catalogues/${encodeURIComponent(id)}/${suffix}${query ? `?${query}` : ""}`,
    { method, headers: { cookie } },
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
    return await proxyCatalogue(request, id, "grade-explanation");
  } catch {
    return Response.json({ detail: "The CatalogForge API is unavailable." }, { status: 503 });
  }
}
