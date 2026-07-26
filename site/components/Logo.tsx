import { cn } from "@/lib/cn";
import { EMPRESA } from "@/lib/empresa";

/** Marca do TI-Escolar: monograma "TI" + wordmark. */
export function Logo({
  className,
  invert = false,
}: {
  className?: string;
  /** Em fundo escuro, o texto vira branco. */
  invert?: boolean;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <span
        className={cn(
          "flex h-9 w-9 flex-none items-center justify-center rounded-md text-[0.8rem] font-extrabold tracking-tight",
          invert ? "bg-white text-brand-700" : "bg-brand-600 text-white",
        )}
        aria-hidden
      >
        TI
      </span>
      <span
        className={cn(
          "text-[1.05rem] font-extrabold tracking-tight",
          invert ? "text-white" : "text-n-900",
        )}
      >
        {EMPRESA.nome}
      </span>
    </span>
  );
}
