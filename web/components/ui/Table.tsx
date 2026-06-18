import type { HTMLAttributes, ThHTMLAttributes, TdHTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

/**
 * Wrapper que dá a borda/raio externos. Use <Table> dentro.
 * No mobile rola horizontalmente (`overflow-x-auto`) para a tabela não
 * estourar a largura da tela nem quebrar o layout.
 */
export function TableWrap({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("overflow-x-auto rounded-md border border-n-100", className)}>{children}</div>
  );
}

export function Table({ className, children, ...rest }: HTMLAttributes<HTMLTableElement>) {
  return (
    <table className={cn("w-full min-w-[420px] border-collapse", className)} {...rest}>
      {children}
    </table>
  );
}

export function Th({ className, children, ...rest }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "bg-n-50 px-3.5 py-2.5 text-left text-[10.5px] font-bold uppercase tracking-wider text-n-400",
        className,
      )}
      {...rest}
    >
      {children}
    </th>
  );
}

export function Td({ className, children, ...rest }: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={cn("px-3.5 py-3 text-[13px] text-n-900", className)} {...rest}>
      {children}
    </td>
  );
}

/** Linha com borda superior e hover. */
export function Tr({ className, children, ...rest }: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr className={cn("border-t border-n-100 first:border-t-0 hover:bg-n-50", className)} {...rest}>
      {children}
    </tr>
  );
}
