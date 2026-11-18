"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { newIdempotencyKey } from "@/lib/api/query-string";
import { conversationSchema, type ConversationValues } from "@/lib/forms/schemas";
import { mapApiErrorToForm } from "@/lib/forms/server-errors";
import { useCreateConversation } from "@/lib/query/hooks";
import { Field, FormError } from "./Field";

export function NewConversationForm() {
  const mutation = useCreateConversation();
  const [formError, setFormError] = useState<string | null>(null);
  // The same title keeps the same key, so retrying after a network failure cannot create a duplicate.
  const keyRef = useRef<{ title: string; key: string }>({ title: "", key: newIdempotencyKey() });

  const { register, handleSubmit, reset, setError, formState: { errors } } = useForm<ConversationValues>({
    resolver: zodResolver(conversationSchema),
    defaultValues: { title: "" },
  });

  const onSubmit = handleSubmit(async ({ title }) => {
    setFormError(null);
    if (keyRef.current.title !== title) keyRef.current = { title, key: newIdempotencyKey() };
    try {
      await mutation.mutateAsync({ title, idempotencyKey: keyRef.current.key });
      keyRef.current = { title: "", key: newIdempotencyKey() };
      reset();                                                            // clear the box only after SUCCESS
    } catch (error) {
      const problems = mapApiErrorToForm(error, ["title"]);
      for (const { field, message } of problems.fieldErrors) setError(field as "title", { type: "server", message });
      setFormError(problems.formError);                                   // the typed text stays so the user can retry
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate>
      <FormError message={formError} />
      <Field label="New conversation" placeholder="What do you want to talk about?" error={errors.title?.message} {...register("title")} />
      <button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Creating..." : "Create"}</button>
    </form>
  );
}
