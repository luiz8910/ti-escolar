import type { ReactNode } from "react";

/** Estado vazio com ícone, texto e ação opcional. */
export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-lg border-[1.5px] border-dashed border-n-300 px-5 py-8 text-center">
      {icon && (
        <div className="mx-auto mb-3.5 flex h-12 w-12 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
          {icon}
        </div>
      )}
      <div className="mb-1 text-sm font-bold text-n-900">{title}</div>
      {description && (
        <p className="mx-auto mb-4 max-w-[280px] text-[12.5px] leading-relaxed text-n-500">
          {description}
        </p>
      )}
      {action}
    </div>
  );
}
