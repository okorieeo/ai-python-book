import { handleLogout } from "@/lib/bff/auth-handlers";
import { bffConfig } from "@/lib/bff/env";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  return handleLogout(request, bffConfig());
}
 app/api/v1/[...path]/route.ts
import { forwardToBackend } from "@/lib/bff/gateway";
import { bffConfig } from "@/lib/bff/env";

export const dynamic = "force-dynamic";

type Context = { params: Promise<{ path: string[] }> };     // in Next.js 15 and later, params is a Promise

async function handler(request: Request, context: Context) {
  const { path } = await context.params;
  return forwardToBackend(request, path, bffConfig());
}

export { handler as GET, handler as POST, handler as PUT, handler as PATCH, handler as DELETE };
