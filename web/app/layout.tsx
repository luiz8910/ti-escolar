import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TI-Escolar — Demo WhatsApp",
  description: "Demo do chatbot escolar simulando a interface do WhatsApp",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR">
      <body className="bg-wa-panel">{children}</body>
    </html>
  );
}
