"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { loginRequest } from "@/lib/api/auth";
import { safeNextPath } from "@/lib/auth/redirects";
import { loginSchema, type LoginValues } from "@/lib/forms/schemas";
import { mapApiErrorToForm } from "@/lib/forms/server-errors";
import { queryKeys } from "@/lib/query/keys";
import { Field, FormError } from "./Field";

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema), defaultValues: { email: "", password: "" } });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      const user = await loginRequest(values);
      queryClient.setQueryData(queryKeys.me, user);                       // the rest of the app has the user immediately
      router.replace(safeNextPath(searchParams.get("next")));             // never trust ?next= blindly
    } catch (error) {
      const problems = mapApiErrorToForm(error, ["email", "password"]);
      for (const { field, message } of problems.fieldErrors) setError(field as keyof LoginValues, { type: "server", message });
      setFormError(problems.formError);
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate>
      <h1>Log in</h1>
      <FormError message={formError} />
      <Field label="Email" type="email" autoComplete="email" inputMode="email" error={errors.email?.message} {...register("email")} />
      <Field label="Password" type="password" autoComplete="current-password" error={errors.password?.message} {...register("password")} />
      <button type="submit" disabled={isSubmitting}>{isSubmitting ? "Logging in..." : "Log in"}</button>
    </form>
  );
}
