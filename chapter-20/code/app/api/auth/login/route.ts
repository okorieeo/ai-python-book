import { handleLogin } from "@/lib/bff/auth-handlers";
import { bffConfig } from "@/lib/bff/env";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  return handleLogin(request, bffConfig());
}
