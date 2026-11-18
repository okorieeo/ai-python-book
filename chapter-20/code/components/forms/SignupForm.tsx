"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { createApiClient } from "@/lib/api/client";
import { createEndpoints } from "@/lib/api/endpoints";
import { signupSchema, type SignupValues } from "@/lib/forms/schemas";
import { mapApiErrorToForm } from "@/lib/forms/server-errors";
import { Field, FormError } from "./Field";

const endpoints = createEndpoints(createApiClient());
const FIELDS = ["name", "email", "password"] as const;

export function SignupForm() {
  const [formError, setFormError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const {
    register,
    handleSubmit,
    setError,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm<SignupValues>({ resolver: zodResolver(signupSchema), defaultValues: { name: "", email: "", password: "", confirmPassword: "" } });

  const onSubmit = handleSubmit(async ({ name, email, password }) => {
    setFormError(null);
    try {
      await endpoints.register({ name, email, password });               // confirmPassword is a UI-only field: never sent
      setDone(true);
    } catch (error) {
      const problems = mapApiErrorToForm(error, FIELDS);
      for (const { field, message } of problems.fieldErrors) setError(field as (typeof FIELDS)[number], { type: "server", message });
      setFormError(problems.formError);
    }
  });

  if (done) {
    return (
      <div role="status">
        <h1>Check your email</h1>
        <p>We sent a verification link to {getValues("email")}. Open it to activate your account, then log in.</p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      <h1>Create your account</h1>
      <FormError message={formError} />
      <Field label="Name" autoComplete="name" error={errors.name?.message} {...register("name")} />
      <Field label="Email" type="email" autoComplete="email" inputMode="email" error={errors.email?.message} {...register("email")} />
      <Field label="Password" type="password" autoComplete="new-password" hint="At least 8 characters." error={errors.password?.message} {...register("password")} />
      <Field label="Confirm password" type="password" autoComplete="new-password" error={errors.confirmPassword?.message} {...register("confirmPassword")} />
      <button type="submit" disabled={isSubmitting}>{isSubmitting ? "Creating account..." : "Create account"}</button>
    </form>
  );
}
