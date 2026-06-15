"use client";

import { useEffect, useRef, useState } from "react";
import { enviarMensagem, MensagemSaida } from "@/lib/api";

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
    <main className="relative flex min-h-screen items-center justify-center bg-wa-panel p-0 sm:p-6">
      <a
        href="/admin"
        className="absolute right-4 top-4 rounded-lg bg-wa-header px-3 py-1.5 text-xs font-medium text-white shadow hover:opacity-90"
      >
        Painel admin →
      </a>
      <div className="flex h-screen w-full max-w-md flex-col overflow-hidden bg-white shadow-xl sm:h-[85vh] sm:rounded-lg">
        {/* Cabeçalho */}
        <header className="flex items-center gap-3 bg-wa-header px-4 py-3 text-white">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/20 text-lg">
            🎓
          </div>
          <div className="leading-tight">
            <div className="font-semibold">Escola Demonstração</div>
            <div className="text-xs text-white/80">assistente virtual • online</div>
          </div>
        </header>

        {/* Mensagens */}
        <div className="wa-wallpaper flex-1 space-y-2 overflow-y-auto px-3 py-4">
          {mensagens.map((m, i) => (
            <div
              key={i}
              className={`flex ${m.autor === "usuario" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-3 py-2 text-sm shadow ${
                  m.autor === "usuario" ? "bg-wa-out" : "bg-white"
                }`}
              >
                <p className="whitespace-pre-wrap text-gray-800">{m.texto}</p>

                {m.documentos && m.documentos.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {m.documentos.map((d, j) => (
                      <a
                        key={j}
                        href={d.url}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center gap-2 rounded bg-gray-100 px-2 py-1 text-xs text-gray-700 hover:bg-gray-200"
                      >
                        📄 {d.nome}
                      </a>
                    ))}
                  </div>
                )}

                {m.fontes && m.fontes.length > 0 && (
                  <div className="mt-1 text-[10px] text-gray-400">
                    Fontes: {m.fontes.join(", ")}
                  </div>
                )}

                <div className="mt-1 text-right text-[10px] text-gray-400">{m.hora}</div>
              </div>
            </div>
          ))}

          {carregando && (
            <div className="flex justify-start">
              <div className="rounded-lg bg-white px-3 py-2 text-sm text-gray-400 shadow">
                digitando…
              </div>
            </div>
          )}
          <div ref={fimRef} />
        </div>

        {/* Sugestões */}
        <div className="flex flex-wrap gap-2 border-t bg-wa-panel px-3 py-2">
          {SUGESTOES.map((s) => (
            <button
              key={s}
              onClick={() => enviar(s)}
              disabled={carregando}
              className="rounded-full border border-gray-300 bg-white px-3 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50"
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
          className="flex items-center gap-2 bg-wa-panel px-3 py-3"
        >
          <input
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Mensagem"
            className="flex-1 rounded-full border-none px-4 py-2 text-sm outline-none"
          />
          <button
            type="submit"
            disabled={carregando}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-wa-header text-white disabled:opacity-50"
            aria-label="Enviar"
          >
            ➤
          </button>
        </form>
      </div>
    </main>
  );
}
