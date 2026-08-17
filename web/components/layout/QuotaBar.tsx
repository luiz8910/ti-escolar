import { Card } from "../ui/Card";

/**
 * Barra de cota da Meta. Vira vermelho ao atingir o limite.
 *
 * Mostra **quando a próxima vaga volta**, não a data de hoje. O limite da Meta corre numa
 * janela de 24 horas: a capacidade é devolvida aos poucos, conforme cada envio completa o
 * prazo. A legenda anterior era a data corrente, o que dava a entender uma virada à
 * meia-noite que não existe — quem esperasse por ela esperaria pela hora errada.
 */
function formatarLiberacao(iso: string | null): string {
  if (!iso) return "Janela de 24h — cota inteira disponível";
  const quando = new Date(iso);
  if (Number.isNaN(quando.getTime())) return "Janela de 24h";
  const hora = quando.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  return `Próxima vaga em ${hora}`;
}

export function QuotaBar({
  enviados,
  limite,
  proximaLiberacao,
}: {
  enviados: number;
  limite: number; // < 0 = ilimitado
  proximaLiberacao: string | null;
}) {
  const ilimitado = limite < 0;
  const pct = ilimitado || limite === 0 ? 0 : Math.min(100, Math.round((enviados / limite) * 100));
  const restante = ilimitado ? Infinity : Math.max(0, limite - enviados);
  const cheio = !ilimitado && pct >= 100;

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-[34px] w-[34px] items-center justify-center rounded-[10px] bg-accent-soft">
            <svg width={18} height={18} viewBox="0 0 24 24" fill="none">
              <path
                d="M4 13l5-9 5 9M4 13l8 7 8-7-5-9"
                stroke="#b07206"
                strokeWidth={1.6}
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div>
            <div className="text-sm font-bold text-n-900">Cota de mensagens (Meta)</div>
            <div className="text-xs text-n-400">{formatarLiberacao(proximaLiberacao)}</div>
          </div>
        </div>
        <div className="text-right">
          <span className="text-[22px] font-extrabold tracking-tight text-n-900">{enviados}</span>
          <span className="text-[13px] font-semibold text-n-400">
            {" "}
            / {ilimitado ? "∞" : limite}
          </span>
        </div>
      </div>

      <div className="h-2.5 w-full overflow-hidden rounded-full bg-n-100">
        <div
          className={cnPct(cheio)}
          style={{ width: `${ilimitado ? 100 : pct}%` }}
        />
      </div>

      <p className="mt-2.5 text-[12.5px] text-n-500">
        {enviados} enviados · {ilimitado ? "ilimitado" : `limite ${limite}`} ·{" "}
        <b className="text-n-700">{ilimitado ? "∞" : restante} restantes</b> hoje.
      </p>
    </Card>
  );
}

function cnPct(cheio: boolean) {
  return cheio
    ? "h-full rounded-full bg-danger"
    : "h-full rounded-full bg-gradient-to-r from-brand-500 to-brand-600";
}
