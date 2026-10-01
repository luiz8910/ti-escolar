"""Simulador local do WhatsApp — **só em desenvolvimento**.

Com o canal em ``demo`` tudo o que "seria enviado" ao WhatsApp fica na memória do
``DemoMessageChannel``, sem que ninguém veja. Esta rota mostra essas mensagens numa tela de
conversa e deixa escrever **como se fosse o responsável**: a mensagem vira um evento no
formato do webhook da Meta e passa pelo mesmo ``ProcessarInboundMeta`` da produção
(professor, mídia, atendimento humano, limite de taxa, LLM).

**Por que só em desenvolvimento.** O demo em Next.js que existia até 10/ago foi removido
por ser a única superfície sem login que gravava conversa e consumia LLM (§1). Esta rota
também não tem login — e por isso só é registrada quando ``APP_ENV`` é de desenvolvimento
**e** o canal efetivo é o demo (``simulador_habilitado``). O homolog também está em
``demo``, mas não é ambiente de desenvolvimento, e lá esta rota não existe.

**Roteamento.** A escola do simulador não precisa ter ``phone_number_id``: o evento chega
com ``simulador:<tenant_id>``, e só a busca de escola desta rota sabe resolvê-lo. O
webhook de verdade continua usando a busca normal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.entities import Tenant
from app.infrastructure.channel.demo_channel import DemoMessageChannel
from app.infrastructure.db.repositories_admin import (
    SqlContatoRepository,
    SqlProfessorRepository,
    SqlTenantRepository,
)
from app.infrastructure.factories import canal_efetivo, criar_canal
from app.interfaces.deps import (
    get_session,
    get_settings_dep,
    montar_processar_inbound_meta,
)

router = APIRouter(prefix="/api/dev/whatsapp", tags=["simulador (dev)"])

PREFIXO_SIMULADOR = "simulador:"


def simulador_habilitado(settings: Settings) -> bool:
    """A rota existe? Só na máquina do dev e com o canal demo **de fato** em uso."""
    return settings.ambiente_desenvolvimento and canal_efetivo(settings) == "demo"


class EscolasDoSimulador:
    """Resolve ``simulador:<tenant_id>`` para a escola; o resto vai ao repositório real."""

    def __init__(self, tenants: SqlTenantRepository) -> None:
        self._tenants = tenants

    async def por_meta_phone_number_id(self, phone_number_id: str) -> Tenant | None:
        if phone_number_id.startswith(PREFIXO_SIMULADOR):
            try:
                tenant_id = uuid.UUID(phone_number_id.removeprefix(PREFIXO_SIMULADOR))
            except ValueError:
                return None
            return await self._tenants.obter(tenant_id)
        return await self._tenants.por_meta_phone_number_id(phone_number_id)

    def __getattr__(self, nome: str) -> Any:
        return getattr(self._tenants, nome)


@dataclass
class MensagemRecebida:
    """O que o "responsável" escreveu — o canal demo só guarda o que sai."""

    contato: str
    conteudo: str
    tenant_id: uuid.UUID
    em: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# Memória do processo, como a do canal demo: o ``--reload`` do compose zera as duas juntas.
_recebidas: list[MensagemRecebida] = []


def _canal_demo(settings: Settings) -> DemoMessageChannel:
    canal = criar_canal(settings)
    if not isinstance(canal, DemoMessageChannel):  # pragma: no cover - barrado no registro
        raise HTTPException(status.HTTP_409_CONFLICT, "O canal em uso não é o demo.")
    return canal


def _e164(telefone: str) -> str:
    digitos = "".join(c for c in telefone if c.isdigit())
    return f"+{digitos}" if digitos else ""


class EnviarComoResponsavel(BaseModel):
    tenant_id: uuid.UUID
    telefone: str = Field(min_length=8, max_length=30)
    texto: str = Field(min_length=1, max_length=4096)
    nome: str = Field(default="Responsável (simulador)", max_length=100)


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def pagina() -> HTMLResponse:
    return HTMLResponse(_PAGINA)


@router.get("/escolas")
async def escolas(session: AsyncSession = Depends(get_session)) -> list[dict]:
    return [
        {"id": str(t.id), "nome": t.nome, "slug": t.slug}
        for t in await SqlTenantRepository(session).listar()
    ]


@router.get("/escolas/{tenant_id}/contatos")
async def contatos(
    tenant_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    """Quem dá para "ser" no simulador: responsáveis e professores com telefone."""
    responsaveis = await SqlContatoRepository(session).listar(tenant_id=tenant_id)
    professores = await SqlProfessorRepository(session).listar(tenant_id=tenant_id)
    return [
        {"nome": c.nome, "telefone": c.telefone, "papel": "responsável"}
        for c in responsaveis
        if c.telefone
    ] + [
        {"nome": p.nome, "telefone": p.telefone, "papel": "professor"}
        for p in professores
        if p.telefone
    ]


@router.get("/mensagens")
async def mensagens(settings: Settings = Depends(get_settings_dep)) -> list[dict]:
    """A linha do tempo inteira: o que a escola mandou e o que o responsável escreveu."""
    saidas = [
        {
            "direcao": "escola",
            "contato": e.contato,
            "tipo": e.tipo,
            "conteudo": e.conteudo,
            "em": e.em.isoformat(),
        }
        for e in _canal_demo(settings).enviados
    ]
    entradas = [
        {
            "direcao": "responsavel",
            "contato": r.contato,
            "tipo": "texto",
            "conteudo": r.conteudo,
            "em": r.em.isoformat(),
        }
        for r in _recebidas
    ]
    return sorted(saidas + entradas, key=lambda m: m["em"])


@router.post("/mensagens")
async def enviar_como_responsavel(
    corpo: EnviarComoResponsavel,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> dict:
    tenants = SqlTenantRepository(session)
    if await tenants.obter(corpo.tenant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Escola não encontrada.")
    telefone = _e164(corpo.telefone)
    if not telefone:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Telefone inválido.")

    _recebidas.append(
        MensagemRecebida(contato=telefone, conteudo=corpo.texto, tenant_id=corpo.tenant_id)
    )
    # O mesmo envelope que a Meta manda ao webhook, com o `from` sem o "+".
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "simulador",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "phone_number_id": f"{PREFIXO_SIMULADOR}{corpo.tenant_id}"
                            },
                            "contacts": [{"profile": {"name": corpo.nome}, "wa_id": telefone[1:]}],
                            "messages": [
                                {
                                    "from": telefone[1:],
                                    "id": f"wamid.simulador.{uuid.uuid4().hex}",
                                    "timestamp": str(int(datetime.now().timestamp())),
                                    "type": "text",
                                    "text": {"body": corpo.texto},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    inbound = montar_processar_inbound_meta(
        session=session, settings=settings, tenants=EscolasDoSimulador(tenants)
    )
    resultado = await inbound.executar(payload=payload)
    return {
        "recebidas": resultado.recebidas,
        "respondidas": resultado.respondidas,
        "silenciadas": resultado.silenciadas,
        "limitadas": resultado.limitadas,
        "ignoradas": resultado.ignoradas,
    }


@router.delete("/mensagens", status_code=status.HTTP_204_NO_CONTENT)
async def limpar(settings: Settings = Depends(get_settings_dep)) -> None:
    _canal_demo(settings).enviados.clear()
    _recebidas.clear()


_PAGINA = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Simulador WhatsApp</title>
<style>
  :root {
    --fundo: #eae6df; --painel: #ffffff; --borda: #d1d7db; --texto: #111b21;
    --suave: #667781; --topo: #008069; --topo-texto: #ffffff; --chat: #efeae2;
    --minha: #d9fdd3; --dela: #ffffff; --ativo: #f0f2f5; --aviso: #fff3c4;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --fundo: #0c1317; --painel: #111b21; --borda: #2a3942; --texto: #e9edef;
      --suave: #8696a0; --topo: #202c33; --topo-texto: #e9edef; --chat: #0b141a;
      --minha: #005c4b; --dela: #202c33; --ativo: #2a3942; --aviso: #3b3417;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; font: 14px/1.4 system-ui, sans-serif; background: var(--fundo);
         color: var(--texto); height: 100vh; display: flex; flex-direction: column; }
  .faixa { background: var(--aviso); padding: 6px 16px; font-size: 12px; }
  .app { flex: 1; display: grid; grid-template-columns: 340px 1fr; min-height: 0; }
  aside { background: var(--painel); border-right: 1px solid var(--borda);
          display: flex; flex-direction: column; min-height: 0; }
  header { background: var(--topo); color: var(--topo-texto); padding: 12px 16px;
           display: flex; gap: 8px; align-items: center; min-height: 56px; }
  header h1 { font-size: 16px; margin: 0; flex: 1; }
  .form { padding: 12px 16px; display: grid; gap: 8px; border-bottom: 1px solid var(--borda); }
  select, input, button { font: inherit; color: inherit; }
  select, input { width: 100%; padding: 8px 10px; border: 1px solid var(--borda);
                  border-radius: 8px; background: var(--painel); }
  button { border: 0; border-radius: 8px; padding: 8px 12px; cursor: pointer;
           background: var(--topo); color: var(--topo-texto); }
  button.leve { background: transparent; color: inherit; border: 1px solid currentColor; }
  .lista { overflow-y: auto; flex: 1; }
  .conv { padding: 12px 16px; border-bottom: 1px solid var(--borda); cursor: pointer; }
  .conv:hover, .conv.ativa { background: var(--ativo); }
  .conv b { display: block; }
  .conv small { color: var(--suave); display: block; white-space: nowrap;
                overflow: hidden; text-overflow: ellipsis; }
  main { display: flex; flex-direction: column; min-height: 0; background: var(--chat); }
  .msgs { flex: 1; overflow-y: auto; padding: 16px 6%; display: flex;
          flex-direction: column; gap: 4px; }
  .bolha { max-width: 65%; padding: 6px 9px 8px; border-radius: 8px; white-space: pre-wrap;
           word-wrap: break-word; box-shadow: 0 1px .5px rgba(0,0,0,.13); background: var(--dela);
           align-self: flex-start; }
  .bolha.minha { background: var(--minha); align-self: flex-end; }
  .bolha .meta { font-size: 11px; color: var(--suave); text-align: right; margin-top: 2px; }
  .etiqueta { font-size: 11px; color: var(--suave); text-transform: uppercase; }
  .vazio { margin: auto; color: var(--suave); text-align: center; padding: 16px; }
  form.enviar { display: flex; gap: 8px; padding: 10px 16px; background: var(--ativo); }
  .digitando { font-size: 12px; color: var(--suave); padding: 0 16px 6px; min-height: 18px;
               background: var(--ativo); }
  @media (max-width: 720px) {
    .app { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
    aside { max-height: 45vh; border-right: 0; border-bottom: 1px solid var(--borda); }
    .bolha { max-width: 85%; }
  }
</style>
</head>
<body>
<div class="faixa">Simulador local — nada sai para o WhatsApp. As mensagens ficam na memória
do back-end e somem quando ele reinicia. Responder aqui consome a LLM configurada.</div>
<div class="app">
  <aside>
    <header><h1>Conversas</h1>
      <button class="leve" id="limpar" title="Apagar todas as mensagens">Limpar</button></header>
    <div class="form">
      <select id="escola" aria-label="Escola"></select>
      <select id="contato" aria-label="Contato cadastrado"></select>
      <input id="telefone" placeholder="ou digite um telefone: +5515999990000">
      <button id="abrir">Abrir conversa</button>
    </div>
    <div class="lista" id="lista"></div>
  </aside>
  <main>
    <header><h1 id="titulo">Selecione uma conversa</h1></header>
    <div class="msgs" id="msgs"><div class="vazio">As mensagens enviadas pela escola
      (avisos, disparos, respostas do assistente) aparecem aqui.</div></div>
    <div class="digitando" id="status"></div>
    <form class="enviar" id="form">
      <input id="texto" placeholder="Escreva como o responsável..." autocomplete="off" disabled>
      <button id="botao" disabled>Enviar</button>
    </form>
  </main>
</div>
<script>
const base = location.pathname.replace(/\\/$/, "");
const $ = (id) => document.getElementById(id);
let mensagens = [], atual = null, contatos = [];

async function api(caminho, opcoes) {
  const r = await fetch(base + caminho, opcoes);
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.status === 204 ? null : r.json();
}
const hora = (iso) => new Date(iso).toLocaleTimeString("pt-BR", {hour: "2-digit", minute: "2-digit"});
const nomeDe = (tel) => (contatos.find((c) => c.telefone === tel) || {}).nome || tel;

async function carregarEscolas() {
  const escolas = await api("/escolas");
  $("escola").innerHTML = escolas.map((e) => `<option value="${e.id}">${e.nome}</option>`).join("");
  await carregarContatos();
}
async function carregarContatos() {
  if (!$("escola").value) return;
  contatos = await api(`/escolas/${$("escola").value}/contatos`);
  $("contato").innerHTML = '<option value="">Escolher contato cadastrado...</option>' +
    contatos.map((c) => `<option value="${c.telefone}">${c.nome} (${c.papel}) ${c.telefone}</option>`).join("");
  desenhar();
}
function abrir(tel) {
  atual = tel;
  $("titulo").textContent = nomeDe(tel) + (nomeDe(tel) !== tel ? "  " + tel : "");
  $("texto").disabled = $("botao").disabled = false;
  $("texto").focus();
  desenhar();
}
function desenhar() {
  const porContato = new Map();
  for (const m of mensagens) porContato.set(m.contato, m);
  if (atual && !porContato.has(atual)) porContato.set(atual, null);
  const itens = [...porContato.entries()].sort((a, b) => (b[1]?.em || "~").localeCompare(a[1]?.em || "~"));
  $("lista").innerHTML = itens.length ? itens.map(([tel, ult]) => `
    <div class="conv ${tel === atual ? "ativa" : ""}" data-tel="${tel}">
      <b>${esc(nomeDe(tel))}</b><small>${ult ? esc(ult.conteudo) : "nova conversa"}</small></div>`).join("")
    : '<div class="vazio">Nenhuma conversa ainda.</div>';
  for (const el of document.querySelectorAll(".conv")) el.onclick = () => abrir(el.dataset.tel);
  if (!atual) return;
  const da = mensagens.filter((m) => m.contato === atual);
  $("msgs").innerHTML = da.length ? da.map((m) => `
    <div class="bolha ${m.direcao === "responsavel" ? "minha" : ""}">
      ${m.tipo !== "texto" ? `<div class="etiqueta">${m.tipo}</div>` : ""}${esc(m.conteudo)}
      <div class="meta">${hora(m.em)}</div></div>`).join("")
    : '<div class="vazio">Sem mensagens com este número.</div>';
  $("msgs").scrollTop = $("msgs").scrollHeight;
}
function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

async function atualizar() {
  try {
    const novas = await api("/mensagens");
    if (JSON.stringify(novas) !== JSON.stringify(mensagens)) { mensagens = novas; desenhar(); }
  } catch (e) { $("status").textContent = "Back-end indisponível: " + e.message; }
}

$("escola").onchange = carregarContatos;
$("contato").onchange = () => { if ($("contato").value) abrir($("contato").value); };
$("abrir").onclick = () => {
  const tel = "+" + $("telefone").value.replace(/\\D/g, "");
  if (tel.length > 9) abrir(tel);
};
$("limpar").onclick = async () => { await api("/mensagens", {method: "DELETE"}); mensagens = []; desenhar(); };
$("form").onsubmit = async (ev) => {
  ev.preventDefault();
  const texto = $("texto").value.trim();
  if (!texto || !atual) return;
  $("texto").value = "";
  $("status").textContent = "Aguardando a escola...";
  try {
    const r = await api("/mensagens", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({tenant_id: $("escola").value, telefone: atual, texto, nome: nomeDe(atual)})});
    $("status").textContent = r.limitadas ? "Recusada pelo limite de taxa."
      : r.silenciadas ? "Sem resposta automática (conversa com a secretaria)." : "";
  } catch (e) { $("status").textContent = "Erro: " + e.message; }
  atualizar();
};

carregarEscolas().catch((e) => { $("status").textContent = "Erro: " + e.message; });
atualizar();
setInterval(atualizar, 1500);
</script>
</body>
</html>
"""
