/**
 * Alerta sonoro do painel — dois toques curtos, sintetizados na hora.
 *
 * **Por que Web Audio e não um arquivo.** Um mp3 seria mais um asset para servir, e a
 * diferença que importa é outra: aqui o som nasce com o envelope que a gente escolheu
 * (ataque suave, cauda curta, ganho baixo). Alerta estridente numa secretaria que atende
 * o dia inteiro acaba mudo — a pessoa desliga o som do computador, e aí *nenhum* aviso
 * chega, que é o oposto do pedido.
 *
 * **Por que dá para desligar.** Mesmo motivo: um som que não se desliga no produto é
 * desligado no sistema operacional. A preferência mora no `localStorage`, por navegador —
 * é uma escolha de quem está sentado ali, não da escola.
 *
 * O navegador só deixa tocar áudio depois de alguma interação do usuário. No painel isso
 * está garantido (ninguém chega à fila sem clicar no login), mas o `resume()` cobre a aba
 * que foi restaurada suspensa, e qualquer falha é engolida: som é acessório, não pode
 * derrubar a tela de atendimento.
 */

const CHAVE = "atendimentos:som";

/** Um único contexto por aba: cada `new AudioContext()` consome um recurso do navegador. */
let contexto: AudioContext | null = null;

export function alertaSonoroLigado(): boolean {
  if (typeof window === "undefined") return true;
  return window.localStorage.getItem(CHAVE) !== "off";
}

export function definirAlertaSonoro(ligado: boolean) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(CHAVE, ligado ? "on" : "off");
}

/** Dois toques curtos e discretos. Silencioso (sem erro) se o navegador não deixar. */
export function tocarAlertaSuave(volume = 0.05) {
  if (typeof window === "undefined" || !alertaSonoroLigado()) return;
  try {
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return;

    contexto ??= new Ctor();
    if (contexto.state === "suspended") void contexto.resume();

    // Duas senoides em intervalo de quarta justa: soa como aviso, não como alarme.
    for (const [hertz, atraso] of [
      [587.33, 0],
      [783.99, 0.1],
    ] as const) {
      const inicio = contexto.currentTime + atraso;
      const oscilador = contexto.createOscillator();
      const ganho = contexto.createGain();

      oscilador.type = "sine";
      oscilador.frequency.value = hertz;

      // Ataque e queda em rampa: um ganho ligado/desligado no talo estala.
      ganho.gain.setValueAtTime(0.0001, inicio);
      ganho.gain.exponentialRampToValueAtTime(volume, inicio + 0.02);
      ganho.gain.exponentialRampToValueAtTime(0.0001, inicio + 0.22);

      oscilador.connect(ganho).connect(contexto.destination);
      oscilador.start(inicio);
      oscilador.stop(inicio + 0.24);
    }
  } catch {
    // Autoplay bloqueado, contexto fechado, navegador sem Web Audio: seguimos calados.
  }
}
