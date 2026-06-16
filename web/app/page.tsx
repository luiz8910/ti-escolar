"use client";

import { useEffect, useRef, useState } from "react";
import { enviarMensagem, MensagemSaida } from "@/lib/api";
import { FileIcon } from "@/components/ui/icons";

interface Bolha {
  autor: "usuario" | "bot";
  texto: string;
  fontes?: string[];
  documentos?: { nome: string; url: string }[];
  hora: string;
}

const SUGESTOES = [
  "Qual o horário de funcionamento?",
  "Como justifico uma falta?",
  "Quero a segunda via do boletim",
  "Quando é a reunião de pais?",
];

function agora() {
  return new Date().toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function Page() {
  // Contato fixo simulando um número de WhatsApp (E.164).
  const contato = "+5511999990000";
  // Mensagem inicial sem horário no SSR: o horário é local (cliente) e seria
  // diferente do servidor (UTC), causando mismatch de hidratação. Preenchido no mount.
  const [mensagens, setMensagens] = useState<Bolha[]>([
    {
      autor: "bot",
      texto:
        "Olá! 👋 Sou o assistente virtual da Escola Demonstração. Como posso ajudar?",
      hora: "",
    },
  ]);
  const [texto, setTexto] = useState("");
  const [carregando, setCarregando] = useState(false);
  const fimRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Só no cliente: define o horário da saudação inicial.
    setMensagens((m) =>
      m.map((b, i) => (i === 0 && !b.hora ? { ...b, hora: agora() } : b))
    );
  }, []);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens, carregando]);

  async function enviar(conteudo: string) {
    const limpo = conteudo.trim();
    if (!limpo || carregando) return;
    setTexto("");
    setMensagens((m) => [...m, { autor: "usuario", texto: limpo, hora: agora() }]);
    setCarregando(true);
    try {
      const resp: MensagemSaida = await enviarMensagem(contato, limpo);
      setMensagens((m) => [
        ...m,
        {
          autor: "bot",
          texto: resp.texto,
          fontes: resp.fontes,
          documentos: resp.documentos,
          hora: agora(),
        },
      ]);
    } catch {
      setMensagens((m) => [
        ...m,
        {
          autor: "bot",
          texto:
            "Desculpe, tive um problema para responder agora. Tente novamente em instantes.",
          hora: agora(),
        },
      ]);
    } finally {
      setCarregando(false);
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center bg-wa-panel p-0 font-sans sm:p-6">
      <a
        href="/admin"
        className="absolute right-4 top-4 rounded-lg bg-wa-header px-3.5 py-2 text-xs font-semibold text-white shadow-md transition-opacity hover:opacity-90"
      >
        Painel admin →
      </a>

      <div className="flex h-screen w-full max-w-md flex-col overflow-hidden bg-white shadow-lg sm:h-[85vh] sm:rounded-xl">
        {/* Cabeçalho */}
        <header className="flex items-center gap-3 bg-wa-header px-4 py-3 text-white">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/20 text-lg">
            🎓
          </div>
          <div className="leading-tight">
            <div className="font-semibold">Escola Demonstração</div>
            <div className="flex items-center gap-1.5 text-xs text-white/80">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-300" />
              assistente virtual • online
            </div>
          </div>
        </header>

        {/* Mensagens */}
        <div className="wa-wallpaper flex-1 space-y-2.5 overflow-y-auto px-3.5 py-4">
          {mensagens.map((m, i) => (
            <div
              key={i}
              className={`flex ${m.autor === "usuario" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[82%] px-3 py-2 text-sm shadow-sm ${
                  m.autor === "usuario"
                    ? "rounded-2xl rounded-tr-sm bg-wa-out"
                    : "rounded-2xl rounded-tl-sm bg-wa-in"
                }`}
              >
                <p className="whitespace-pre-wrap leading-relaxed text-gray-800">{m.texto}</p>

                {m.documentos && m.documentos.length > 0 && (
                  <div className="mt-2 space-y-1.5">
                    {m.documentos.map((d, j) => (
                      <a
                        key={j}
                        href={d.url}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center gap-2 rounded-lg border border-black/5 bg-black/[0.04] px-2.5 py-2 text-xs font-medium text-gray-700 transition-colors hover:bg-black/[0.07]"
                      >
                        <span className="flex h-7 w-7 flex-none items-center justify-center rounded-md bg-wa-header/10 text-wa-header">
                          <FileIcon size={15} />
                        </span>
                        <span className="truncate">{d.nome}</span>
                      </a>
                    ))}
                  </div>
                )}

                {m.fontes && m.fontes.length > 0 && (
                  <div className="mt-1.5 border-t border-black/[0.06] pt-1 text-[10px] text-gray-400">
                    Fontes: {m.fontes.join(", ")}
                  </div>
                )}

                <div className="mt-1 text-right text-[10px] text-gray-400">{m.hora}</div>
              </div>
            </div>
          ))}

          {carregando && (
            <div className="flex justify-start">
              <div className="flex items-center gap-1 rounded-2xl rounded-tl-sm bg-wa-in px-3.5 py-3 shadow-sm">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.3s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.15s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400" />
              </div>
            </div>
          )}
          <div ref={fimRef} />
        </div>

        {/* Sugestões */}
        <div className="flex flex-wrap gap-2 border-t border-black/5 bg-wa-panel px-3.5 py-2.5">
          {SUGESTOES.map((s) => (
            <button
              key={s}
              onClick={() => enviar(s)}
              disabled={carregando}
              className="rounded-full border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:border-wa-header hover:text-wa-header disabled:opacity-50"
            >
              {s}
            </button>
          ))}
        </div>

        {/* Caixa de envio */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            enviar(texto);
          }}
          className="flex items-center gap-2 bg-wa-panel px-3.5 py-3"
        >
          <input
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Mensagem"
            className="flex-1 rounded-full border-none bg-white px-4 py-2.5 text-sm text-gray-800 shadow-sm outline-none placeholder:text-gray-400"
          />
          <button
            type="submit"
            disabled={carregando}
            className="flex h-10 w-10 flex-none items-center justify-center rounded-full bg-wa-header text-white shadow-md transition-opacity hover:opacity-90 disabled:opacity-50"
            aria-label="Enviar"
          >
            ➤
          </button>
        </form>
      </div>
    </main>
  );
}
