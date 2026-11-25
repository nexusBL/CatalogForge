import { NextResponse } from "next/server";

const AUTH_URL = process.env.AUTH_URL || process.env.NEXT_PUBLIC_AUTH_URL || "http://localhost:3001";

async function proxy(request: Request) {
  const incoming = new URL(request.url);
  const target = `${AUTH_URL}${incoming.pathname}${incoming.search}`;
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (lower === "host" || lower === "connection") {
      return;
    }
    headers.set(key, value);
  });
  headers.set("x-forwarded-host", incoming.host);
  headers.set("x-forwarded-proto", incoming.protocol.replace(":", ""));
  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
    cache: "no-store",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }
  init.signal = AbortSignal.timeout(8_000);
  let response: Response;
  try {
    response = await fetch(target, init);
  } catch {
    return NextResponse.json(
      { message: "Auth service is unavailable. Please try again." },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }
  const outbound = new Headers();
  response.headers.forEach((value, key) => {
    if (key.toLowerCase() === "set-cookie") {
      return;
    }
    outbound.append(key, value);
  });
  const setCookies =
    typeof response.headers.getSetCookie === "function" ? response.headers.getSetCookie() : [];
  for (const cookie of setCookies) {
    outbound.append("set-cookie", cookie);
  }
  outbound.set("cache-control", "no-store");
  return new NextResponse(response.body, {
    status: response.status,
    headers: outbound,
  });
}

export function GET(request: Request) {
  return proxy(request);
}

export function POST(request: Request) {
  return proxy(request);
}

export function PUT(request: Request) {
  return proxy(request);
}

export function PATCH(request: Request) {
  return proxy(request);
}

export function DELETE(request: Request) {
  return proxy(request);
}
