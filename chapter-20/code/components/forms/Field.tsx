import { useId, type InputHTMLAttributes, type Ref } from "react";

type FieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "id"> & {
  label: string;
  error?: string;
  hint?: string;
  ref?: Ref<HTMLInputElement>; // React 19: ref is an ordinary prop, so React Hook Form's register() just works
};

/** A labelled input with accessible hint and error wiring. Use it for every form field. */
export function Field({ label, error, hint, ref, ...inputProps }: FieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} ref={ref} aria-invalid={error ? true : undefined} aria-describedby={describedBy} {...inputProps} />
      {hint ? <p id={hintId} className="field-hint">{hint}</p> : null}
      {error ? <p id={errorId} role="alert" className="field-error">{error}</p> : null}
    </div>
  );
}

/** A message that applies to the whole form (for example "Incorrect email or password."). */
export function FormError({ message }: { message: string | null }) {
  return message ? <p role="alert" className="form-error">{message}</p> : null;
}
