// Next.js 16 renamed "middleware" to "proxy". On Next.js 15 or older, name this file middleware.ts and export `middleware`.
// This is only an OPTIMISTIC check (is there a session cookie?) to send people to the right page quickly.
// The real security is the backend, which validates the token on every API call.
import { NextResponse, type NextRequest } from "next/server";
import { decideRedirect } from "@/lib/auth/redirects";
import { ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/bff/cookies";

export function proxy(request: NextRequest) {
  const hasSession = request.cookies.has(REFRESH_COOKIE) || request.cookies.has(ACCESS_COOKIE);
  const target = decideRedirect(request.nextUrl.pathname, request.nextUrl.search, hasSession);
  if (target) return NextResponse.redirect(new URL(target, request.url));
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],     // pages only: API routes handle their own auth
};
