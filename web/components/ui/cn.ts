/** Junta classes condicionalmente (clsx mínimo, sem dependência). */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
