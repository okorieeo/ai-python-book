import { api, unwrap } from "@/lib/api/client";
import { setAccessToken } from "./session";
import type { LoginValues } from "./schemas";

export async function login(values: LoginValues) {
  const result = await unwrap(api.POST("/api/v1/auth/login/", { body: values }));
  setAccessToken(result.access);
  return result.user;
}
