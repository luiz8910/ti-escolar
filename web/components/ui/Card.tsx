import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

/** Cartão branco padrão: borda sutil, raio lg, sombra sm. */
export function Card({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-lg border border-n-200 bg-white p-5 shadow-sm", className)}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  count,
  action,
}: {
  title: ReactNode;
  count?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <h3 className="text-sm font-bold text-n-900">
        {title}
        {count != null && <span className="ml-1.5 font-semibold text-n-400">· {count}</span>}
      </h3>
      {action}
    </div>
  );
}
