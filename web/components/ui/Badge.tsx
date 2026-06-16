import type { ReactNode } from "react";
import { cn } from "./cn";

type Tone = "neutral" | "brand" | "success" | "warning" | "danger";

const TONES: Record<Tone, string> = {
  neutral: "bg-n-100 text-n-600",
  brand: "bg-brand-50 text-brand-700 border border-brand-200",
  success: "bg-success-soft text-success",
  warning: "bg-accent-soft text-[#92600a]",
  danger: "bg-danger-soft text-danger",
};

const DOT: Partial<Record<Tone, string>> = {
  success: "bg-success",
  warning: "bg-accent",
};

export function Badge({
  tone = "neutral",
  dot = false,
  children,
  className,
}: {
  tone?: Tone;
  dot?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold",
        TONES[tone],
        className,
      )}
    >
      {dot && <span className={cn("h-1.5 w-1.5 rounded-full", DOT[tone] ?? "bg-current")} />}
      {children}
    </span>
  );
}
