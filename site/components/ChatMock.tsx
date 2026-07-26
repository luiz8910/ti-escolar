import { FileIcon, WhatsAppIcon } from "@/components/icons";

type Bolha = {
  de: "pai" | "escola";
  texto: string;
  hora: string;
  /** Documento anexado à resposta (boletim, declaração, calendário…). */
  anexo?: string;
  /** Fonte citada pelo RAG, como o assistente faz de verdade. */
  fonte?: string;
};

const CONVERSA: Bolha[] = [
  {
    de: "pai",
    texto: "Boa tarde! Preciso da declaração de matrícula do meu filho.",
    hora: "14:02",
  },
  {
    de: "escola",
    texto:
      "Boa tarde! Claro. A declaração de matrícula do Pedro está anexada abaixo. Qualquer outra dúvida, estou à disposição.",
    hora: "14:02",
    anexo: "declaracao-matricula.pdf",
  },
  {
    de: "pai",
    texto: "Obrigado! E que horas é a reunião de pais?",
    hora: "14:03",
  },
  {
    de: "escola",
    texto:
      "A reunião de pais do 5º ano será na quinta-feira, dia 6, às 19h, no pátio coberto.",
    hora: "14:03",
    fonte: "Circular 12/2026",
  },
];

/**
 * Simulação da conversa no WhatsApp exibida no hero.
 * É ilustrativa — some para leitores de tela, que já recebem a mesma
 * informação no texto do hero.
 */
export function ChatMock() {
  return (
    <div
      aria-hidden
      className="w-full max-w-[380px] overflow-hidden rounded-xl border border-n-200 bg-white shadow-lg"
    >
      {/* Cabeçalho no verde do WhatsApp */}
      <div className="flex items-center gap-3 bg-wa-header px-4 py-3 text-white">
        <div className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-white/20 text-[0.7rem] font-extrabold">
          EM
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">Escola Municipal</p>
          <p className="text-[0.7rem] text-white/80">online</p>
        </div>
        <WhatsAppIcon size={18} />
      </div>

      {/* Corpo da conversa */}
      <div className="wa-wallpaper space-y-2 px-3 py-4">
        {CONVERSA.map((b, i) => (
          <div
            key={i}
            className={`flex ${b.de === "pai" ? "justify-start" : "justify-end"}`}
          >
            <div
              className={`max-w-[86%] rounded-lg px-3 py-2 text-[0.8rem] leading-snug shadow-sm ${
                b.de === "pai" ? "bg-wa-in text-n-800" : "bg-wa-out text-n-900"
              }`}
            >
              <p>{b.texto}</p>

              {b.anexo && (
                <div className="mt-2 flex items-center gap-2 rounded-md bg-black/5 px-2.5 py-2">
                  <FileIcon size={16} className="flex-none text-n-600" />
                  <span className="truncate text-[0.72rem] font-medium text-n-700">
                    {b.anexo}
                  </span>
                </div>
              )}

              {b.fonte && (
                <p className="mt-1.5 text-[0.68rem] text-n-500">Fonte: {b.fonte}</p>
              )}

              <p className="mt-1 text-right text-[0.62rem] text-n-400">{b.hora}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
