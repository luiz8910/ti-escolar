"use client";

import { useEffect, type ReactNode } from "react";
import { cn } from "./cn";
import { Button } from "./Button";
import { CloseIcon } from "./icons";

/**
 * Modal acessível: trava o scroll, fecha no Esc e no clique do overlay.
 * Controlado: passe `open` e `onClose`.
 */
export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  className,
}: {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="absolute inset-0 bg-n-900/30" onClick={onClose} />
      <div
        className={cn(
          "relative w-full max-w-md rounded-lg bg-white p-[22px] shadow-lg",
          className,
        )}
      >
        {title && (
          <div className="mb-1.5 flex items-start justify-between">
            <h4 className="text-base font-bold text-n-900">{title}</h4>
            <button
              onClick={onClose}
              aria-label="Fechar"
              className="mt-0.5 text-n-400 hover:text-n-600"
            >
              <CloseIcon size={16} />
            </button>
          </div>
        )}
        <div className="text-[13px] leading-relaxed text-n-500">{children}</div>
        {footer && <div className="mt-[18px] flex justify-end gap-2.5">{footer}</div>}
      </div>
    </div>
  );
}

/** Exemplo de confirmação destrutiva. */
export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = "Excluir",
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmLabel?: string;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancelar
          </Button>
          <Button variant="danger" size="sm" onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {message}
    </Modal>
  );
}
