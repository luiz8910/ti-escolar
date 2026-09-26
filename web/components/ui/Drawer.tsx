"use client";

import { useEffect, type ReactNode } from "react";
import { cn } from "./cn";
import { CloseIcon } from "./icons";

/**
 * Painel lateral: o irmão do `Modal` para formulários longos.
 *
 * Mesmo contrato do modal (controlado, fecha no Esc e no overlay, trava o scroll), mas
 * ocupa a altura toda à direita — o formulário de escola tem três blocos e, num modal
 * centrado, o "Salvar" ficava sempre abaixo da dobra. Aqui cabeçalho e rodapé são fixos
 * e só o miolo rola.
 */
export function Drawer({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  className,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-n-900/40" onClick={onClose} />
      <aside
        className={cn(
          "absolute inset-y-0 right-0 flex w-full max-w-[560px] flex-col bg-white shadow-lg",
          className,
        )}
      >
        <div className="flex flex-none items-start justify-between gap-4 border-b border-n-100 px-7 py-[22px]">
          <div className="flex flex-col gap-1">
            <h2 className="text-xl font-bold text-n-900">{title}</h2>
            {description && <p className="text-[13px] text-n-500">{description}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar"
            className="flex h-9 w-9 flex-none items-center justify-center rounded-md text-n-600 hover:bg-n-100"
          >
            <CloseIcon size={18} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-7 py-6">{children}</div>
        {footer && (
          <div className="flex flex-none justify-end gap-2.5 border-t border-n-100 bg-white px-7 py-4">
            {footer}
          </div>
        )}
      </aside>
    </div>
  );
}
