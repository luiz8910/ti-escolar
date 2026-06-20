import { Badge } from "@/components/ui/Badge";
import type { Licenca } from "@/lib/admin";

// Badge de licenciamento: cancelamento/bloqueio (prioritários), expiração e plano.
export function LicencaBadge({ licenca }: { licenca: Licenca }) {
  if (licenca.status === "cancelado") {
    return (
      <span title={licenca.motivo_cancelamento}>
        <Badge tone="neutral">Cancelada</Badge>
      </span>
    );
  }
  if (licenca.status === "bloqueado") {
    return (
      <span title={licenca.motivo_bloqueio}>
        <Badge tone="danger">Bloqueada</Badge>
      </span>
    );
  }
  const d = licenca.dias_para_expirar;
  if (licenca.licenca_expirada) {
    return <Badge tone="danger">Licença expirada</Badge>;
  }
  if (d !== null && d <= 30) {
    return (
      <Badge tone="warning" dot>
        Vence em {d} dia(s)
      </Badge>
    );
  }
  if (d !== null) {
    return (
      <Badge tone="success" dot>
        {licenca.plano === "anual" ? "Anual" : "Mensal"} · {d} dia(s)
      </Badge>
    );
  }
  return <Badge tone="neutral">{licenca.plano === "anual" ? "Anual" : "Mensal"}</Badge>;
}
