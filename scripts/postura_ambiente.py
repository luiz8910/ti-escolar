#!/usr/bin/env python3
"""Confere, de fora e sem credencial, a postura de proteção de dados de um ambiente no ar.

Roda a cada deploy (ver ``.github/workflows/lgpd.yml``). É o complemento **determinístico**
da auditoria LGPD: o agente ``lgpd-auditor`` audita o *código* no pull request, e o código é
o mesmo em todo ambiente — o que muda entre homolog e produção é a **configuração**, e é
exatamente ela que este script mede, no ambiente real, depois do deploy.

**Caixa-preta de propósito.** Nenhuma verificação aqui usa token de admin. Guardar
credencial de super admin num secret do CI criaria um caminho novo para a base inteira —
todas as escolas, todas as fichas de matrícula — e seria um risco maior do que o que o
script pretende cobrir. Tudo abaixo é observável por qualquer cliente HTTP; a diferença é
que aqui alguém olha.

Uso:
    python scripts/postura_ambiente.py https://api.exemplo.com [--estrito] [--json saida.json]

Saída: relatório legível em stdout. Código de saída 1 se houver falha **e** ``--estrito``;
sem ``--estrito`` o script relata e sai 0 (modo observação, para não travar a esteira antes
de a postura estar ajustada).
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Callable

TIMEOUT = 20
# Origem que não pertence a ninguém: se o ambiente devolver Access-Control-Allow-Origin
# para ela, o CORS está aberto na prática, com curinga ou ecoando a origem recebida.
ORIGEM_FORJADA = "https://origem-nao-autorizada.invalid"
# Credenciais de exemplo versionadas no `.env.example`. Se elas autenticam no ambiente,
# o seed de demonstração rodou ali com senha pública — e quem leu o repositório entra.
CRED_EXEMPLO = [
    ("admin@tiescolar.test", "troque-esta-senha"),
    ("admin@escola-demo.test", "escola123"),
]


@dataclass
class Resultado:
    """Uma verificação e o que ela encontrou no ambiente."""

    nome: str
    ok: bool
    detalhe: str
    risco: str = ""  # o que acontece se estiver errado; vazio quando ok
    erro_interno: bool = False  # a checagem não pôde ser feita (rede, timeout)


@dataclass
class Resposta:
    status: int
    corpo: bytes
    cabecalhos: dict[str, str] = field(default_factory=dict)

    @property
    def texto(self) -> str:
        return self.corpo.decode("utf-8", errors="replace")


def _requisitar(
    url: str,
    *,
    metodo: str = "GET",
    corpo: bytes | None = None,
    cabecalhos: dict[str, str] | None = None,
) -> Resposta:
    """Requisição HTTP que trata 4xx/5xx como resposta, não como exceção.

    Quase toda checagem aqui **espera** um 401/403 — tratar isso como erro faria o script
    reprovar justamente os ambientes corretos.
    """
    req = urllib.request.Request(url, data=corpo, method=metodo)
    for chave, valor in (cabecalhos or {}).items():
        req.add_header(chave, valor)
    contexto = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=contexto) as resp:
            return Resposta(resp.status, resp.read(), dict(resp.headers))
    except urllib.error.HTTPError as exc:
        return Resposta(exc.code, exc.read(), dict(exc.headers))


def checar_vivo(base: str) -> Resultado:
    try:
        r = _requisitar(f"{base}/health")
    except Exception as exc:  # noqa: BLE001 — sem ambiente, nada mais faz sentido
        return Resultado(
            "Ambiente responde",
            False,
            f"{type(exc).__name__}: {exc}",
            "Sem resposta em /health, as demais verificações não têm o que medir.",
            erro_interno=True,
        )
    ok = r.status == 200
    return Resultado(
        "Ambiente responde",
        ok,
        f"GET /health → {r.status}",
        "" if ok else "O serviço não está no ar ou o deploy falhou.",
    )


def checar_verify_token_default(base: str) -> Resultado:
    """O handshake do webhook não pode aceitar o token de exemplo ``changeme``.

    Com o default, qualquer um reassina o webhook da Meta para um endpoint próprio e passa
    a receber as conversas dos responsáveis (§9e.2 do CLAUDE.md).
    """
    url = (
        f"{base}/api/webhook/meta"
        "?hub.mode=subscribe&hub.verify_token=changeme&hub.challenge=sonda"
    )
    r = _requisitar(url)
    aceitou = r.status == 200 and "sonda" in r.texto
    return Resultado(
        "META_WEBHOOK_VERIFY_TOKEN não é o default",
        not aceitou,
        f"GET handshake com 'changeme' → {r.status}",
        "O token de verificação continua 'changeme': o webhook pode ser reassinado por "
        "terceiro, que passa a receber as mensagens dos responsáveis."
        if aceitou
        else "",
    )


def checar_assinatura_webhook(base: str) -> Resultado:
    """POST sem ``X-Hub-Signature-256`` tem de ser recusado com 403.

    Sem isso dá para forjar status de entrega (mascarando de ``delivered`` um aviso que não
    chegou) e injetar mensagens em nome de qualquer telefone, consumindo cota de LLM.
    """
    payload = json.dumps({"entry": [], "object": "whatsapp_business_account"}).encode()
    r = _requisitar(
        f"{base}/api/webhook/meta",
        metodo="POST",
        corpo=payload,
        cabecalhos={"Content-Type": "application/json"},
    )
    ok = r.status == 403
    return Resultado(
        "Webhook exige X-Hub-Signature-256",
        ok,
        f"POST sem assinatura → {r.status} (esperado 403)",
        "META_VALIDATE_SIGNATURE está desligado: qualquer um forja status de entrega e "
        "mensagens inbound em nome de qualquer telefone."
        if not ok
        else "",
    )


def checar_cors(base: str) -> Resultado:
    r = _requisitar(
        f"{base}/api/admin/escolas",
        metodo="OPTIONS",
        cabecalhos={
            "Origin": ORIGEM_FORJADA,
            "Access-Control-Request-Method": "GET",
        },
    )
    permitido = {k.lower(): v for k, v in r.cabecalhos.items()}.get(
        "access-control-allow-origin", ""
    )
    aberto = permitido in ("*", ORIGEM_FORJADA)
    return Resultado(
        "CORS restrito ao próprio domínio",
        not aberto,
        f"Access-Control-Allow-Origin para origem forjada → {permitido or '(ausente)'}",
        "Qualquer site pode chamar a API pelo navegador da vítima."
        if aberto
        else "",
    )


def checar_rota_admin_fechada(base: str) -> Resultado:
    r = _requisitar(f"{base}/api/admin/escolas")
    ok = r.status in (401, 403)
    return Resultado(
        "Rota administrativa exige autenticação",
        ok,
        f"GET /api/admin/escolas sem token → {r.status} (esperado 401/403)",
        "Listagem de escolas acessível sem token — dado de todas as escolas exposto."
        if not ok
        else "",
    )


def checar_credenciais_de_exemplo(base: str) -> Resultado:
    """As senhas versionadas no `.env.example` não podem autenticar no ambiente."""
    entrou: list[str] = []
    for email, senha in CRED_EXEMPLO:
        r = _requisitar(
            f"{base}/api/admin/login",
            metodo="POST",
            corpo=json.dumps({"email": email, "senha": senha}).encode(),
            cabecalhos={"Content-Type": "application/json"},
        )
        if r.status == 200 and "access_token" in r.texto:
            entrou.append(email)
    return Resultado(
        "Credenciais de exemplo não autenticam",
        not entrou,
        f"tentativas: {len(CRED_EXEMPLO)}; autenticaram: {entrou or 'nenhuma'}",
        "Senha publicada no repositório dá acesso ao painel deste ambiente. "
        "Se houver dado real aqui, é incidente de segurança (art. 46-48 da LGPD)."
        if entrou
        else "",
    )


VERIFICACOES: list[Callable[[str], Resultado]] = [
    checar_vivo,
    checar_verify_token_default,
    checar_assinatura_webhook,
    checar_cors,
    checar_rota_admin_fechada,
    checar_credenciais_de_exemplo,
]


def executar(base: str) -> list[Resultado]:
    base = base.rstrip("/")
    resultados = [checar_vivo(base)]
    if resultados[0].erro_interno:
        # Ambiente fora do ar: seguir mediria a rede, não a postura.
        return resultados
    for verificacao in VERIFICACOES[1:]:
        try:
            resultados.append(verificacao(base))
        except Exception as exc:  # noqa: BLE001 — uma checagem quebrada não cala as outras
            resultados.append(
                Resultado(
                    verificacao.__name__,
                    False,
                    f"{type(exc).__name__}: {exc}",
                    "A verificação não pôde ser concluída.",
                    erro_interno=True,
                )
            )
    return resultados


def relatar(ambiente: str, base: str, resultados: list[Resultado]) -> str:
    linhas = [f"# Postura do ambiente — {ambiente}", "", f"`{base}`", ""]
    for r in resultados:
        marca = "✅" if r.ok else ("⚠️" if r.erro_interno else "❌")
        linhas.append(f"{marca} **{r.nome}** — {r.detalhe}")
        if r.risco:
            linhas.append(f"   ↳ {r.risco}")
    falhas = [r for r in resultados if not r.ok]
    linhas += ["", f"**{len(resultados) - len(falhas)}/{len(resultados)} conformes.**"]
    return "\n".join(linhas)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="URL raiz da API (ex.: https://api.exemplo.com)")
    parser.add_argument("--ambiente", default="homolog", help="Rótulo do ambiente")
    parser.add_argument(
        "--estrito",
        action="store_true",
        help="Sai com código 1 se alguma verificação falhar (use em produção)",
    )
    parser.add_argument("--json", dest="json_saida", help="Grava o resultado bruto em JSON")
    args = parser.parse_args()

    resultados = executar(args.base_url)
    print(relatar(args.ambiente, args.base_url, resultados))

    if args.json_saida:
        with open(args.json_saida, "w", encoding="utf-8") as arq:
            json.dump([asdict(r) for r in resultados], arq, ensure_ascii=False, indent=2)

    falhou = any(not r.ok for r in resultados)
    if falhou and not args.estrito:
        print("\n(modo observação: falhas relatadas, sem reprovar o job)")
    return 1 if (falhou and args.estrito) else 0


if __name__ == "__main__":
    sys.exit(main())
