import { Card } from "../ui/Card";

/**
 * Barra de cota diária (tier Meta). Mantém a mesma informação da versão atual,
 * apenas com a casca nova. Vira vermelho ao atingir o limite.
 */
export function QuotaBar({
  enviados,
  limite,
  dia,
}: {
  enviados: number;
  limite: number; // < 0 = ilimitado
  dia: string;
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
            <div className="text-sm font-bold text-n-900">Cota diária de mensagens (Meta)</div>
            <div className="text-xs text-n-400">{dia}</div>
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
