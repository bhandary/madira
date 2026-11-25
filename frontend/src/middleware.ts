import { NextResponse, type NextRequest } from "next/server";
import { CSRF_BLOCKED, csrfBlock } from "@/lib/csrf";

export function middleware(request: NextRequest) {
  const forwardedHost = request.headers.get("x-forwarded-host");
  const host = (forwardedHost || request.headers.get("host") || "").split(",")[0].trim();
  const proto = (request.headers.get("x-forwarded-proto") || request.nextUrl.protocol.replace(":", "")).split(",")[0].trim();
  const requestHost = host && proto ? `${proto}://${host}` : "";
  const reason = csrfBlock(request, requestHost);
  if (!reason) return NextResponse.next();
  console.warn("csrf rejected method=%s path=%s reason=%s", request.method, request.nextUrl.pathname, reason);
  return NextResponse.json({ detail: CSRF_BLOCKED }, { status: 403 });
}

export const config = {
  matcher: ["/madira-api/:path*", "/api/copilotkit", "/api/copilotkit/:path*"],
};
