import { forwardRef } from "react";
import type { InputHTMLAttributes, TextareaHTMLAttributes, SelectHTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";
import { ChevronDownIcon } from "./icons";

const CONTROL =
  "w-full font-sans text-sm text-n-900 bg-white px-[13px] py-2.5 rounded-lg border border-n-300 " +
  "outline-none transition-colors placeholder:text-n-400 " +
  "focus:border-brand-500 focus:ring-[3px] focus:ring-brand-500/20 " +
  "aria-[invalid=true]:border-danger aria-[invalid=true]:ring-danger/15";

/* ---------- Field wrapper (label + erro) ---------------------------------- */
export function Field({
  label,
  htmlFor,
  error,
  hint,
  children,
}: {
  label?: string;
  htmlFor?: string;
  error?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={htmlFor} className="text-xs font-semibold text-n-600">
          {label}
        </label>
      )}
      {children}
      {error ? (
        <p className="text-[11.5px] text-danger">{error}</p>
      ) : hint ? (
        <p className="text-[11.5px] text-n-400">{hint}</p>
      ) : null}
    </div>
  );
}

/* ---------- Input --------------------------------------------------------- */
export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
  mono?: boolean;
}
export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, invalid, mono, ...rest }, ref) => (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(CONTROL, mono && "font-mono text-[13px]", className)}
      {...rest}
    />
  ),
);
Input.displayName = "Input";

/* ---------- Textarea ------------------------------------------------------ */
export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, invalid, ...rest }, ref) => (
    <textarea
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(CONTROL, "resize-y leading-relaxed", className)}
      {...rest}
    />
  ),
);
Textarea.displayName = "Textarea";

/* ---------- Select (com chevron) ------------------------------------------ */
export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean;
}
export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, invalid, children, ...rest }, ref) => (
    <div className="relative">
      <select
        ref={ref}
        aria-invalid={invalid || undefined}
        className={cn(CONTROL, "appearance-none pr-9 text-n-700", className)}
        {...rest}
      >
        {children}
      </select>
      <ChevronDownIcon
        size={16}
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-n-400"
      />
    </div>
  ),
);
Select.displayName = "Select";
