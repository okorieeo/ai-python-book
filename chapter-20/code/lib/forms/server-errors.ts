import { ApiError, messageForError } from "../api/errors";

export type FieldProblem = { field: string; message: string };
export type FormProblems = { fieldErrors: FieldProblem[]; formError: string | null };

/**
 * Turn a failed API call into messages for a form: errors that belong to a field go next to that field;
 * everything else becomes one message at the top of the form.
 */
export function mapApiErrorToForm(error: unknown, fields: readonly string[]): FormProblems {
  if (!(error instanceof ApiError)) return { fieldErrors: [], formError: messageForError(error) };
  if (error.code !== "validation_error") return { fieldErrors: [], formError: messageForError(error) };

  const fieldErrors: FieldProblem[] = [];
  const other: string[] = [];
  for (const [key, messages] of Object.entries(error.details)) {
    if (fields.includes(key)) fieldErrors.push({ field: key, message: messages.join(" ") });
    else other.push(...messages);
  }
  if (fieldErrors.length === 0 && other.length === 0) return { fieldErrors, formError: messageForError(error) };
  return { fieldErrors, formError: other.length > 0 ? other.join(" ") : null };
}
