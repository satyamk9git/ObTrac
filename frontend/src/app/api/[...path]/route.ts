import { NextRequest, NextResponse } from "next/server";

// Proxies /api/v1/* to the real backend, injecting the Authorization header
// server-side when OBTRAC_API_KEY is set (server-only env var — Next.js
// never bundles it into client JS, so the browser never sees the key).
//
// This replaces next.config.js's `rewrites()`-based proxy (removed) and
// the old src/middleware.ts (removed) — Next's external-destination rewrite
// proxy has an internal ~30s timeout that isn't exposed as a config option,
// which killed slow AI-calling endpoints (AI Insights, prompt merge,
// ground-truth generation) with a raw "socket hang up" / ECONNRESET before
// the backend's genuinely-valid response ever arrived. A plain fetch() in
// a route handler has no such cap — we set an explicit generous one instead
// so a truly-stuck backend still fails visibly rather than hanging forever.

const BACKEND_INTERNAL_URL = process.env.BACKEND_INTERNAL_URL || "http://localhost:8100";
const PROXY_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes — comfortably covers slow LLM calls

async function proxy(request: NextRequest): Promise<Response> {
  const path = request.nextUrl.pathname; // e.g. "/api/v1/explain/project-metrics"
  const target = `${BACKEND_INTERNAL_URL}${path}${request.nextUrl.search}`;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");
  const apiKey = process.env.OBTRAC_API_KEY;
  if (apiKey) {
    headers.set("Authorization", `Bearer ${apiKey}`);
  }

  const hasBody = !["GET", "HEAD"].includes(request.method);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROXY_TIMEOUT_MS);

  try {
    const backendResponse = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      signal: controller.signal,
      // @ts-expect-error - duplex is required by undici for streaming bodies but not yet in the TS lib types
      duplex: hasBody ? "half" : undefined,
    });

    const responseHeaders = new Headers(backendResponse.headers);
    responseHeaders.delete("content-encoding"); // avoid double-decoding
    responseHeaders.delete("transfer-encoding");

    const body = await backendResponse.arrayBuffer();
    return new NextResponse(body, {
      status: backendResponse.status,
      headers: responseHeaders,
    });
  } catch (e: any) {
    const message = e?.name === "AbortError" ? "Backend request timed out" : e?.message || "Proxy error";
    return NextResponse.json({ error: "ProxyError", message }, { status: 502 });
  } finally {
    clearTimeout(timer);
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const PATCH = proxy;
