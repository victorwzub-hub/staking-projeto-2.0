import type { InputHTMLAttributes, SelectHTMLAttributes } from "react";

export function FormField({
  label,
  hint,
  error,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string }) {
  const id = props.id ?? props.name;
  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-error` : null]
    .filter(Boolean)
    .join(" ");
  return (
    <label className="field" htmlFor={id}>
      <span>{label}</span>
      <input
        id={id}
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy || undefined}
        {...props}
      />
      {hint ? <small id={`${id}-hint`}>{hint}</small> : null}
      {error ? (
        <small className="field-error" id={`${id}-error`}>
          {error}
        </small>
      ) : null}
    </label>
  );
}

export function SelectField({
  label,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string; children: React.ReactNode }) {
  const id = props.id ?? props.name;
  return (
    <label className="field" htmlFor={id}>
      <span>{label}</span>
      <select id={id} {...props}>
        {children}
      </select>
    </label>
  );
}
