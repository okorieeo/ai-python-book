"use client";

import { useId, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError, friendlyMessage } from "@/lib/api/errors";
import { loginSchema, type LoginValues } from "@/lib/auth/schemas";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Props = {
  onLogin: (values: LoginValues) => Promise<unknown>;
  onSuccess?: () => void;
};

export function LoginForm({ onLogin, onSuccess }: Props) {
  const id = useId();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema), defaultValues: { email: "", password: "" } });

  async function submit(values: LoginValues) {
    setFormError(null);
    try {
      await onLogin(values);
      onSuccess?.();
    } catch (error) {
      if (error instanceof ApiError && error.status === 400) {
        // Field-level messages from the server land on the matching inputs.
        for (const [name, messages] of Object.entries(error.fields)) {
          if (name === "email" || name === "password") {
            setError(name, { message: messages[0] ?? "Invalid value" });
          }
        }
        if (Object.keys(error.fields).length > 0) return;
      }
      // 401 is deliberately uniform: never say which of the two was wrong (17.11).
      setFormError(
        error instanceof ApiError && error.status === 401
          ? "The email or password is incorrect."
          : friendlyMessage(error),
      );
    }
  }

  const emailId = `${id}-email`;
  const passwordId = `${id}-password`;

  return (
    <form onSubmit={handleSubmit(submit)} noValidate className="flex w-full max-w-sm flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={emailId}>Email</Label>
        <Input
          id={emailId}
          type="email"
          autoComplete="email"
          aria-invalid={errors.email ? true : undefined}
          aria-describedby={errors.email ? `${emailId}-error` : undefined}
          {...register("email")}
        />
        {errors.email && (
          <p id={`${emailId}-error`} className="text-sm text-danger">
            {errors.email.message}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor={passwordId}>Password</Label>
        <Input
          id={passwordId}
          type="password"
          autoComplete="current-password"
          aria-invalid={errors.password ? true : undefined}
          aria-describedby={errors.password ? `${passwordId}-error` : undefined}
          {...register("password")}
        />
        {errors.password && (
          <p id={`${passwordId}-error`} className="text-sm text-danger">
            {errors.password.message}
          </p>
        )}
      </div>

      {formError && (
        <p role="alert" className="text-sm text-danger">
          {formError}
        </p>
      )}

      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
