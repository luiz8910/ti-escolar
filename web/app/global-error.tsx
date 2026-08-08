"use client";

/**
 * Último recurso: erro no próprio `layout.tsx` raiz, que o `error.tsx` não alcança.
 *
 * Por rodar acima do layout, precisa renderizar `<html>` e `<body>` por conta própria —
 * e não pode depender de nada do app (nem do Tailwind, que é carregado pelo layout que
 * acabou de falhar). Daí o estilo inline.
 */

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="pt-BR">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "system-ui, -apple-system, sans-serif",
          background: "#fafafa",
          color: "#171717",
          padding: "24px",
          textAlign: "center",
        }}
      >
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 800, margin: 0 }}>
            O sistema não conseguiu iniciar
          </h1>
          <p style={{ fontSize: 14, color: "#666", maxWidth: 420, margin: "10px auto 0" }}>
            Recarregue a página. Se o problema continuar, informe o código abaixo ao
            suporte.
          </p>
          {error.digest && (
            <p
              style={{
                marginTop: 16,
                fontFamily: "ui-monospace, monospace",
                fontSize: 12,
                color: "#555",
                background: "#f0f0f0",
                display: "inline-block",
                padding: "8px 12px",
                borderRadius: 8,
              }}
            >
              código: {error.digest}
            </p>
          )}
          <div style={{ marginTop: 22 }}>
            <button
              onClick={reset}
              style={{
                background: "#2563eb",
                color: "#fff",
                border: 0,
                borderRadius: 10,
                padding: "10px 18px",
                fontSize: 13,
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              Recarregar
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
