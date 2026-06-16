"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { cn } from "./cn";
import { CheckIcon, CloseIcon } from "./icons";

type ToastTone = "success" | "danger" | "info";
interface ToastItem {
  id: number;
  tone: ToastTone;
  title: string;
  description?: string;
}

const ToastCtx = createContext<{
  toast: (t: Omit<ToastItem, "id">) => void;
} | null>(null);

/** Envolva o app (ou o layout admin) com <ToastProvider>. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const toast = useCallback((t: Omit<ToastItem, "id">) => {
    const id = Date.now() + Math.random();
    setItems((cur) => [...cur, { ...t, id }]);
    setTimeout(() => setItems((cur) => cur.filter((i) => i.id !== id)), 4500);
  }, []);

  const dismiss = (id: number) => setItems((cur) => cur.filter((i) => i.id !== id));

  return (
    <ToastCtx.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-5 right-5 z-[60] flex w-[340px] max-w-[calc(100vw-2rem)] flex-col gap-2.5">
        {items.map((t) => (
          <Toast key={t.id} {...t} onClose={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast precisa estar dentro de <ToastProvider>");
  return ctx.toast;
}

const ACCENT: Record<ToastTone, string> = {
  success: "border-l-success",
  danger: "border-l-danger",
  info: "border-l-brand-600",
};
const ICON_BG: Record<ToastTone, string> = {
  success: "bg-success-soft text-success",
  danger: "bg-danger-soft text-danger",
  info: "bg-brand-50 text-brand-600",
};

function Toast({
  tone,
  title,
  description,
  onClose,
}: ToastItem & { onClose: () => void }) {
  return (
    <div
      role="status"
      className={cn(
        "flex items-center gap-3 rounded-md border border-n-200 border-l-[3px] bg-white px-3.5 py-3 shadow-lg",
        ACCENT[tone],
      )}
    >
      <div className={cn("flex h-[30px] w-[30px] flex-none items-center justify-center rounded-md", ICON_BG[tone])}>
        {tone === "danger" ? <CloseIcon size={16} /> : <CheckIcon size={16} />}
      </div>
      <div className="flex-1">
        <div className="text-[13px] font-bold text-n-900">{title}</div>
        {description && <div className="text-xs text-n-500">{description}</div>}
      </div>
      <button onClick={onClose} aria-label="Fechar" className="text-n-400 hover:text-n-600">
        <CloseIcon size={16} />
      </button>
    </div>
  );
}
