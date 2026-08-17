"""Implementações em memória das portas, para testar os casos de uso sem BD/rede."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.domain.entities import (
    Aluno,
    NumeroBloqueado,
    AvisoTemporizado,
    Broadcast,
    Contato,
    Conversa,
    Documento,
    FonteConhecimento,
    Grupo,
    MessageQuota,
    MessageTemplate,
    LeituraRecado,
    Professor,
    PromptTenant,
    Recado,
    RespostaLLM,
    RespostaRapida,
    ResultadoBusca,
    Sala,
    SolicitacaoImpressao,
    StatusImpressao,
    StatusTemplate,
    TemplateNaWaba,
    TemplateRemoto,
    TrechoConhecimento,
    TurnoConversa,
    Waba,
)
from app.infrastructure.llm.fake_provider import FakeEmbedder


def _fatiar(itens: list, pagina: int | None, por_pagina: int | None) -> list:
    """Recorte de página dos fakes — espelha o OFFSET/LIMIT dos repositórios SQL."""
    if pagina is None or por_pagina is None:
        return itens
    inicio = max(0, (pagina - 1) * por_pagina)
    return itens[inicio : inicio + por_pagina]


class FakeVectorStore:
    def __init__(self) -> None:
        self._itens: list[tuple[TrechoConhecimento, list[float]]] = []

    async def indexar(self, trecho: TrechoConhecimento, embedding: list[float]) -> None:
        self._itens.append((trecho, embedding))

    async def buscar(self, *, tenant_id, embedding, k=4) -> list[ResultadoBusca]:
        def cos(a, b):
            return sum(x * y for x, y in zip(a, b))

        candidatos = [
            (t, cos(embedding, e)) for t, e in self._itens if t.tenant_id == tenant_id
        ]
        candidatos.sort(key=lambda x: x[1], reverse=True)
        return [ResultadoBusca(trecho=t, score=s) for t, s in candidatos[:k]]

    async def remover_por_fonte(self, *, tenant_id, fonte_id) -> int:
        antes = len(self._itens)
        self._itens = [
            (t, e)
            for t, e in self._itens
            if not (t.tenant_id == tenant_id and t.fonte_id == fonte_id)
        ]
        return antes - len(self._itens)


class FakeFonteConhecimentoRepo:
    def __init__(self) -> None:
        self.fontes: dict[uuid.UUID, "FonteConhecimento"] = {}

    async def criar(self, fonte):
        self.fontes[fonte.id] = fonte
        return fonte

    async def obter(self, *, tenant_id, fonte_id):
        f = self.fontes.get(fonte_id)
        return f if f and f.tenant_id == tenant_id else None

    async def listar(self, *, tenant_id):
        return [f for f in self.fontes.values() if f.tenant_id == tenant_id]

    async def atualizar(self, fonte):
        atual = self.fontes.get(fonte.id)
        if atual is None or atual.tenant_id != fonte.tenant_id:
            raise ValueError("Documento não encontrado para o tenant.")
        self.fontes[fonte.id] = fonte
        return fonte

    async def remover(self, *, tenant_id, fonte_id):
        f = self.fontes.get(fonte_id)
        if f is None or f.tenant_id != tenant_id:
            return False
        del self.fontes[fonte_id]
        return True


class FakeAvisoTemporizadoRepo:
    def __init__(self) -> None:
        self.avisos: dict[uuid.UUID, "AvisoTemporizado"] = {}

    async def criar(self, aviso):
        self.avisos[aviso.id] = aviso
        return aviso

    async def obter(self, *, tenant_id, aviso_id):
        a = self.avisos.get(aviso_id)
        return a if a and a.tenant_id == tenant_id else None

    async def listar(self, *, tenant_id):
        return sorted(
            [a for a in self.avisos.values() if a.tenant_id == tenant_id],
            key=lambda a: a.criado_em,
            reverse=True,
        )

    async def vigente(self, *, tenant_id):
        for a in await self.listar(tenant_id=tenant_id):
            if a.vigente_em():
                return a
        return None

    async def atualizar(self, aviso):
        self.avisos[aviso.id] = aviso
        return aviso

    async def remover(self, *, tenant_id, aviso_id):
        a = self.avisos.get(aviso_id)
        if a is None or a.tenant_id != tenant_id:
            return False
        del self.avisos[aviso_id]
        return True


class FakeRespostaRapidaRepo:
    def __init__(self) -> None:
        self.respostas: dict[uuid.UUID, "RespostaRapida"] = {}

    async def criar(self, resposta):
        self.respostas[resposta.id] = resposta
        return resposta

    async def obter(self, *, tenant_id, resposta_id):
        r = self.respostas.get(resposta_id)
        return r if r and r.tenant_id == tenant_id else None

    async def por_chave(self, *, tenant_id, chave):
        return next(
            (
                r
                for r in self.respostas.values()
                if r.tenant_id == tenant_id and r.chave == chave
            ),
            None,
        )

    async def listar(self, *, tenant_id):
        return [r for r in self.respostas.values() if r.tenant_id == tenant_id]

    async def atualizar(self, resposta):
        self.respostas[resposta.id] = resposta
        return resposta

    async def remover(self, *, tenant_id, resposta_id):
        r = self.respostas.get(resposta_id)
        if r is None or r.tenant_id != tenant_id:
            return False
        del self.respostas[resposta_id]
        return True


class FakePromptTenantRepo:
    def __init__(self) -> None:
        self.prompts: dict[uuid.UUID, "PromptTenant"] = {}

    async def obter(self, *, tenant_id):
        return self.prompts.get(tenant_id)

    async def salvar(self, *, tenant_id, conteudo):
        from app.domain.entities import PromptTenant

        prompt = PromptTenant(tenant_id=tenant_id, conteudo=conteudo)
        self.prompts[tenant_id] = prompt
        return prompt


class FakeLLM:
    def __init__(self, respostas: list[RespostaLLM] | None = None) -> None:
        self.ultimo_sistema = ""
        # Roteiro determinístico para ``gerar_com_ferramentas`` (uma RespostaLLM por iteração).
        self._respostas = list(respostas or [])
        self.turnos_recebidos: list[list[TurnoConversa]] = []

    async def gerar(self, *, sistema: str, mensagens: list[dict[str, str]]) -> str:
        self.ultimo_sistema = sistema
        pergunta = next((m["content"] for m in reversed(mensagens) if m["role"] == "user"), "")
        return f"resposta para: {pergunta}"

    async def gerar_com_ferramentas(
        self, *, sistema: str, turnos: list[TurnoConversa], ferramentas
    ) -> RespostaLLM:
        self.ultimo_sistema = sistema
        self.turnos_recebidos.append(list(turnos))
        if self._respostas:
            return self._respostas.pop(0)
        # Sem roteiro: responde direto, sem ferramentas.
        ultimo = next((t.texto for t in reversed(turnos) if t.papel == "user" and t.texto), "")
        return RespostaLLM(texto=f"resposta para: {ultimo}")


class FakeConversaRepo:
    """Espelha a **sessão** do repositório SQL: uma conversa viva por contato, encerrada
    ao passar da janela ou por chamada explícita."""

    def __init__(self, janela_horas: int = 24) -> None:
        self.mensagens: dict[uuid.UUID, list[dict]] = {}
        # Todas as sessões, na ordem em que nasceram (inclusive as encerradas).
        self.sessoes: list[Conversa] = []
        self.janela_horas = janela_horas
        # Relógio injetável, para o teste andar no tempo sem dormir.
        self.agora: datetime | None = None

    def _agora(self) -> datetime:
        return self.agora or datetime.now(timezone.utc)

    @property
    def conversas(self) -> dict[tuple, Conversa]:
        """Compatibilidade com os testes antigos: a sessão viva por (tenant, contato)."""
        return {
            (c.tenant_id, c.contato): c for c in self.sessoes if c.encerrada_em is None
        }

    async def obter_ou_criar(self, *, tenant_id, contato) -> Conversa:
        agora = self._agora()
        viva = next(
            (
                c
                for c in reversed(self.sessoes)
                if c.tenant_id == tenant_id and c.contato == contato and not c.encerrada
            ),
            None,
        )
        if viva is not None:
            if not viva.vencida_em(agora, janela_horas=self.janela_horas):
                return viva
            viva.encerrada_em = agora

        nova = Conversa(
            tenant_id=tenant_id, contato=contato, criado_em=agora, ultima_mensagem_em=agora
        )
        self.sessoes.append(nova)
        self.mensagens[nova.id] = []
        return nova

    async def encerrar(self, *, conversa_id) -> None:
        for c in self.sessoes:
            if c.id == conversa_id and c.encerrada_em is None:
                c.encerrada_em = self._agora()

    async def adicionar_mensagem(
        self, *, conversa_id, autor, texto, fontes=None, autor_nome=""
    ) -> None:
        # Renova a janela da sessão, como o repositório SQL.
        for c in self.sessoes:
            if c.id == conversa_id:
                c.ultima_mensagem_em = self._agora()
        self.mensagens.setdefault(conversa_id, []).append(
            {
                "autor": autor,
                "texto": texto,
                "fontes": fontes or [],
                "autor_nome": autor_nome,
            }
        )

    async def historico(self, *, conversa_id, limite=20) -> list[dict[str, str]]:
        msgs = self.mensagens.get(conversa_id, [])[-limite:]
        # Como no repositório real: a fala da secretaria é da escola, não do responsável.
        return [
            {
                "role": "assistant" if m["autor"] in ("bot", "atendente") else "user",
                "content": m["texto"],
            }
            for m in msgs
        ]


class FakeDocumentSource:
    def __init__(self, documentos: list[Documento] | None = None) -> None:
        self._docs = documentos or []

    async def buscar_documentos(self, *, tenant_id, contato, consulta) -> list[Documento]:
        return [d for d in self._docs if d.tenant_id == tenant_id]


class FakeChannel:
    def __init__(self, *, falhar_em: set[str] | None = None) -> None:
        self.enviados: list[tuple[str, str]] = []
        # Os parâmetros de cada envio por template, na ordem — é o que a Meta valida
        # contra o corpo aprovado, e o que o disparo a grupo montava errado.
        self.parametros_enviados: list[list[str]] = []
        self._falhar_em = falhar_em or set()

    async def enviar_texto(self, *, contato, texto, remetente=None) -> str:
        self.remetente = remetente
        self.enviados.append((contato, "texto"))
        return "x"

    async def enviar_template(self, *, contato, template, parametros, remetente=None) -> str:
        if contato in self._falhar_em:
            raise RuntimeError("falha simulada")
        self.remetente = remetente
        self.enviados.append((contato, "template"))
        self.parametros_enviados.append(list(parametros))
        return f"wamid:{contato}"

    async def enviar_documento(self, *, contato, documento, remetente=None) -> str:
        self.enviados.append((contato, "documento"))
        return "x"


class FakeQuota:
    """Espelha a contagem real: janela de 24h corridas, por **contato distinto**.

    O teto é compartilhado por todos os tenants — é o que a Meta faz no portfólio, e é
    justamente o comportamento que o fake anterior (um contador por tenant) escondia.
    """

    def __init__(self, *, limite_diario: int, portfolios: dict | None = None) -> None:
        self._limite = limite_diario
        # Portfólio de cada escola. Ausente = ``""``, que é o balde de quem ainda não tem
        # conta do WhatsApp — por padrão todas caem nele e **dividem o teto**, que é o
        # comportamento real da Meta desde out/2025.
        self._portfolios = portfolios or {}
        # (portfólio, contato, instante) de cada conversa iniciada.
        self.envios: list[tuple[str, str, datetime]] = []

    def _pf(self, tenant_id) -> str:
        return self._portfolios.get(tenant_id, "")

    async def cota(self, tenant_id) -> MessageQuota:
        pf = self._pf(tenant_id)
        corte = datetime.now(timezone.utc) - timedelta(hours=24)
        na_janela = [(c, q) for p, c, q in self.envios if p == pf and q > corte]
        return MessageQuota(
            tenant_id=tenant_id,
            limite_diario=self._limite,
            enviados=len({c for c, _ in na_janela}),
            proxima_liberacao=(
                min(q for _, q in na_janela) + timedelta(hours=24) if na_janela else None
            ),
        )

    async def registrar_envio(self, tenant_id, contato: str) -> None:
        self.envios.append((self._pf(tenant_id), contato, datetime.now(timezone.utc)))


class FakeRateLimiter:
    def __init__(self) -> None:
        self.chamadas = 0

    async def aguardar_vaga(self) -> None:
        self.chamadas += 1


class FakeBroadcastRepo:
    def __init__(self) -> None:
        self.salvos: dict[uuid.UUID, Broadcast] = {}

    async def salvar(self, broadcast: Broadcast) -> None:
        self.salvos[broadcast.id] = broadcast

    async def obter(self, broadcast_id) -> Broadcast | None:
        return self.salvos.get(broadcast_id)

    async def listar(self, *, tenant_id, pagina=None, por_pagina=None):
        itens = [b for b in self.salvos.values() if b.tenant_id == tenant_id]
        return _fatiar(itens, pagina, por_pagina)

    async def contar(self, *, tenant_id):
        return len([b for b in self.salvos.values() if b.tenant_id == tenant_id])

    async def registrar_status(self, *, mensagem_id_externo, status) -> bool:
        from app.domain.entities import _now

        atualizou = False
        for b in self.salvos.values():
            for d in b.destinatarios:
                if d.mensagem_id_externo == mensagem_id_externo:
                    d.status = status
                    d.atualizado_em = _now()
                    atualizou = True
        return atualizou


class FakeTemplateRepo:
    """Guarda vários templates e respeita o escopo global (``tenant_id`` nulo)."""

    def __init__(self, template: MessageTemplate | None = None) -> None:
        self.templates: list[MessageTemplate] = [template] if template else []

    def _visiveis(self, tenant_id) -> list[MessageTemplate]:
        return [t for t in self.templates if t.visivel_para(tenant_id)]

    async def obter(self, *, tenant_id, template_id) -> MessageTemplate | None:
        for t in self._visiveis(tenant_id):
            if t.id == template_id:
                return t
        return None

    async def por_nome(self, *, tenant_id, nome) -> MessageTemplate | None:
        candidatos = [t for t in self._visiveis(tenant_id) if t.nome == nome]
        # O da própria escola tem precedência sobre o global de mesmo nome.
        candidatos.sort(key=lambda t: t.global_)
        return candidatos[0] if candidatos else None

    async def listar(self, *, tenant_id) -> list[MessageTemplate]:
        return sorted(self._visiveis(tenant_id), key=lambda t: t.nome)

    async def listar_todos(self) -> list[MessageTemplate]:
        return list(self.templates)

    async def por_meta_id(self, meta_template_id) -> MessageTemplate | None:
        if not meta_template_id:
            return None
        # O id da Meta é emitido por conta, então mora na entrada, não no template.
        return next(
            (
                t
                for t in self.templates
                if any(w.meta_template_id == meta_template_id for w in t.wabas)
            ),
            None,
        )

    async def por_nome_e_idioma(self, *, nome, idioma) -> MessageTemplate | None:
        return next(
            (t for t in self.templates if t.nome == nome and t.idioma == idioma), None
        )

    async def salvar(self, template: MessageTemplate) -> MessageTemplate:
        for i, existente in enumerate(self.templates):
            if existente.id == template.id:
                self.templates[i] = template
                return template
        self.templates.append(template)
        return template

    async def remover(self, template_id) -> bool:
        antes = len(self.templates)
        self.templates = [t for t in self.templates if t.id != template_id]
        return len(self.templates) < antes


class FakeCatalogoTemplates:
    """Meta de mentira: registra as submissões e devolve o status que o teste mandar."""

    def __init__(
        self,
        *,
        status: StatusTemplate = StatusTemplate.PENDENTE,
        remotos: list[TemplateRemoto] | None = None,
        erro: Exception | None = None,
    ) -> None:
        self.submetidos: list[MessageTemplate] = []
        self.contas_submetidas: list[str] = []
        self.removidos: list[str] = []
        # id na Meta -> nome. `None` confirma qualquer id; um dicionário deixa o teste
        # dizer quais existem de verdade do lado de lá.
        self.contas_conhecidas: dict[str, str] | None = None
        self._status = status
        self._remotos = remotos or []
        self._erro = erro

    async def submeter(
        self, template: MessageTemplate, *, meta_waba_id: str = ""
    ) -> TemplateRemoto:
        if self._erro:
            raise self._erro
        self.submetidos.append(template)
        self.contas_submetidas.append(meta_waba_id)
        return TemplateRemoto(
            nome=template.nome,
            idioma=template.idioma,
            status=self._status,
            categoria=template.categoria,
            meta_template_id=f"meta-{len(self.submetidos)}",
        )

    async def listar(self, *, meta_waba_id: str = "") -> list[TemplateRemoto]:
        if self._erro:
            raise self._erro
        return list(self._remotos)

    async def remover(self, *, nome: str, meta_waba_id: str = "") -> bool:
        if self._erro:
            raise self._erro
        self.removidos.append(nome)
        return True

    async def descrever(self, *, meta_waba_id: str) -> str | None:
        """Confirma o id na "Meta". ``contas_conhecidas=None`` = confirma qualquer um."""
        if self.contas_conhecidas is None:
            return "Conta confirmada"
        return self.contas_conhecidas.get(meta_waba_id)


class FakeAuditLogRepo:
    def __init__(self) -> None:
        self.registros: list = []

    async def registrar(self, registro):
        self.registros.append(registro)
        return registro

    async def listar(self, *, tenant_id, limite: int = 200, pagina=None, por_pagina=None):
        registros = [r for r in self.registros if r.tenant_id == tenant_id]
        registros.sort(key=lambda r: r.criado_em, reverse=True)
        if pagina is not None and por_pagina is not None:
            return _fatiar(registros, pagina, por_pagina)
        return registros[:limite]

    async def contar(self, *, tenant_id):
        return len([r for r in self.registros if r.tenant_id == tenant_id])


def fake_embedder() -> FakeEmbedder:
    # Dimensão pequena nos testes para velocidade.
    return FakeEmbedder(dimensao=64)


class FakeGrupoRepo:
    def __init__(self) -> None:
        self.grupos: dict[uuid.UUID, "Grupo"] = {}

    async def criar(self, grupo):
        self.grupos[grupo.id] = grupo
        return grupo

    async def obter(self, *, tenant_id, grupo_id):
        g = self.grupos.get(grupo_id)
        return g if g and g.tenant_id == tenant_id else None

    async def listar(self, *, tenant_id):
        return [g for g in self.grupos.values() if g.tenant_id == tenant_id]

    async def adicionar_contato(self, *, tenant_id, grupo_id, nome, telefone):
        from app.domain.entities import Contato

        g = self.grupos[grupo_id]
        contato = Contato(tenant_id=tenant_id, nome=nome, telefone=telefone)
        g.membros.append(contato)
        return contato

    async def membros(self, *, tenant_id, grupo_id):
        g = await self.obter(tenant_id=tenant_id, grupo_id=grupo_id)
        return list(g.membros) if g else []


class FakeContatoRepo:
    def __init__(self) -> None:
        self.contatos: dict[uuid.UUID, "Contato"] = {}

    async def criar(self, contato):
        self.contatos[contato.id] = contato
        return contato

    async def obter(self, *, tenant_id, contato_id):
        c = self.contatos.get(contato_id)
        return c if c and c.tenant_id == tenant_id else None

    async def por_telefone(self, *, tenant_id, telefone):
        return next(
            (
                c
                for c in self.contatos.values()
                if c.tenant_id == tenant_id and c.telefone == telefone
            ),
            None,
        )

    async def por_cpf(self, *, tenant_id, cpf):
        if not cpf:
            return None
        return next(
            (
                c
                for c in self.contatos.values()
                if c.tenant_id == tenant_id and c.cpf == cpf
            ),
            None,
        )

    async def por_telefones(self, *, tenant_id, telefones):
        alvo = {t for t in telefones if t}
        return {
            c.telefone: c
            for c in self.contatos.values()
            if c.tenant_id == tenant_id and c.telefone in alvo
        }

    async def listar(self, *, tenant_id, pagina=None, por_pagina=None):
        itens = [c for c in self.contatos.values() if c.tenant_id == tenant_id]
        return _fatiar(itens, pagina, por_pagina)

    async def contar(self, *, tenant_id):
        return len([c for c in self.contatos.values() if c.tenant_id == tenant_id])

    async def atualizar(self, contato):
        self.contatos[contato.id] = contato
        return contato

    async def remover(self, *, tenant_id, contato_id):
        c = self.contatos.get(contato_id)
        if c is None or c.tenant_id != tenant_id:
            return False
        del self.contatos[contato_id]
        return True


class FakeMuralRepo:
    def __init__(self) -> None:
        self.recados: dict[uuid.UUID, "Recado"] = {}
        self._leituras: list["LeituraRecado"] = []

    async def criar(self, recado):
        self.recados[recado.id] = recado
        return recado

    async def obter(self, *, tenant_id, recado_id):
        r = self.recados.get(recado_id)
        return r if r and r.tenant_id == tenant_id else None

    async def listar(self, *, tenant_id):
        itens = [r for r in self.recados.values() if r.tenant_id == tenant_id]
        itens.sort(key=lambda r: r.criado_em, reverse=True)
        return itens

    async def remover(self, *, tenant_id, recado_id):
        r = self.recados.get(recado_id)
        if r is None or r.tenant_id != tenant_id:
            return False
        del self.recados[recado_id]
        self._leituras = [x for x in self._leituras if x.recado_id != recado_id]
        return True

    async def marcar_leitura(self, *, tenant_id, recado_id, professor_id):
        for x in self._leituras:
            if x.recado_id == recado_id and x.professor_id == professor_id:
                return x
        leitura = LeituraRecado(recado_id=recado_id, professor_id=professor_id)
        self._leituras.append(leitura)
        return leitura

    async def leituras(self, *, recado_id):
        return [x for x in self._leituras if x.recado_id == recado_id]

    async def leituras_do_professor(self, *, tenant_id, professor_id):
        recados_do_tenant = {
            r.id for r in self.recados.values() if r.tenant_id == tenant_id
        }
        return [
            x
            for x in self._leituras
            if x.professor_id == professor_id and x.recado_id in recados_do_tenant
        ]


class FakeSolicitacaoImpressaoRepo:
    def __init__(self) -> None:
        self.solicitacoes: dict[uuid.UUID, "SolicitacaoImpressao"] = {}

    async def criar(self, solicitacao):
        self.solicitacoes[solicitacao.id] = solicitacao
        return solicitacao

    async def obter(self, *, tenant_id, solicitacao_id):
        s = self.solicitacoes.get(solicitacao_id)
        return s if s and s.tenant_id == tenant_id else None

    async def listar(self, *, tenant_id, status=None):
        itens = [
            s
            for s in self.solicitacoes.values()
            if s.tenant_id == tenant_id and (status is None or s.status == status)
        ]
        itens.sort(key=lambda s: s.criado_em, reverse=True)
        return itens

    async def atualizar(self, solicitacao):
        self.solicitacoes[solicitacao.id] = solicitacao
        return solicitacao

    async def por_media_id(self, *, tenant_id, media_id):
        if not media_id:
            return None
        return next(
            (
                s
                for s in self.solicitacoes.values()
                if s.tenant_id == tenant_id and s.media_id == media_id
            ),
            None,
        )

    async def consumo_do_professor(self, *, tenant_id, professor_id, competencia):
        return sum(
            s.copias
            for s in self.solicitacoes.values()
            if s.tenant_id == tenant_id
            and s.professor_id == professor_id
            and s.status != StatusImpressao.CANCELADA
            and s.criado_em.strftime("%Y-%m") == competencia
        )

    async def remover(self, *, tenant_id, solicitacao_id):
        s = self.solicitacoes.get(solicitacao_id)
        if s is None or s.tenant_id != tenant_id:
            return False
        del self.solicitacoes[solicitacao_id]
        return True


class FakeProfessorRepo:
    def __init__(self) -> None:
        self.professores: dict[uuid.UUID, "Professor"] = {}

    async def criar(self, professor):
        self.professores[professor.id] = professor
        return professor

    async def obter(self, *, tenant_id, professor_id):
        p = self.professores.get(professor_id)
        return p if p and p.tenant_id == tenant_id else None

    async def por_telefone(self, *, tenant_id, telefone):
        return next(
            (
                p
                for p in self.professores.values()
                if p.tenant_id == tenant_id and p.telefone == telefone
            ),
            None,
        )

    async def por_cpf(self, *, tenant_id, cpf):
        if not cpf:
            return None
        return next(
            (
                p
                for p in self.professores.values()
                if p.tenant_id == tenant_id and p.cpf == cpf
            ),
            None,
        )

    async def listar(self, *, tenant_id, apenas_eventuais=False):
        itens = [p for p in self.professores.values() if p.tenant_id == tenant_id]
        if apenas_eventuais:
            itens = [p for p in itens if not p.titular and p.telefone and p.ativo]
        return sorted(itens, key=lambda p: p.nome)

    async def atualizar(self, professor):
        self.professores[professor.id] = professor
        return professor

    async def remover(self, *, tenant_id, professor_id):
        p = self.professores.get(professor_id)
        if p is None or p.tenant_id != tenant_id:
            return False
        del self.professores[professor_id]
        return True


class FakeSalaRepo:
    def __init__(self) -> None:
        self.salas: dict[uuid.UUID, "Sala"] = {}
        # Resolve pais pelo id (compartilhado com o FakeContatoRepo nos testes).
        self.contatos: FakeContatoRepo | None = None
        # Deriva os responsáveis da turma a partir dos alunos, como o repositório SQL.
        self.alunos: "FakeAlunoRepo | None" = None
        # Resolve o nome do professor ao atribuí-lo a uma série (compartilhado nos testes).
        self.professores: FakeProfessorRepo | None = None

    async def criar(self, sala):
        self.salas[sala.id] = sala
        return sala

    async def obter(self, *, tenant_id, sala_id):
        s = self.salas.get(sala_id)
        return s if s and s.tenant_id == tenant_id else None

    async def listar(self, *, tenant_id):
        return [s for s in self.salas.values() if s.tenant_id == tenant_id]

    async def atualizar(self, sala):
        atual = await self.obter(tenant_id=sala.tenant_id, sala_id=sala.id)
        if atual is None:
            raise ValueError("Sala não encontrada para o tenant.")
        self.salas[sala.id] = sala
        return sala

    async def remover(self, *, tenant_id, sala_id):
        s = await self.obter(tenant_id=tenant_id, sala_id=sala_id)
        if s is None:
            return False
        del self.salas[sala_id]
        return True

    async def pais(self, *, tenant_id, sala_id):
        """Derivado dos alunos ativos, como o repositório SQL.

        `self.alunos` é ligado pelos testes que precisam da derivação; sem ele o fake cai
        no que estiver em `sala.pais`, que é o que os testes de turma montam à mão.
        """
        s = await self.obter(tenant_id=tenant_id, sala_id=sala_id)
        if s is None:
            raise ValueError("Sala não encontrada para o tenant.")
        if self.alunos is None:
            return list(s.pais)
        derivados: list = []
        vistos: set = set()
        for aluno in self.alunos.alunos.values():
            if aluno.tenant_id != tenant_id or aluno.sala_id != sala_id or not aluno.ativo:
                continue
            for contato in aluno.responsaveis:
                if contato.id in vistos:
                    continue
                vistos.add(contato.id)
                derivados.append(contato)
        return sorted(derivados, key=lambda c: c.nome)

    async def definir_professor(self, *, tenant_id, sala_id, professor_id):
        s = await self.obter(tenant_id=tenant_id, sala_id=sala_id)
        if s is None:
            raise ValueError("Sala não encontrada para o tenant.")
        if professor_id is None:
            s.professor_id = None
            s.professor_nome = ""
            return s
        professor = self.professores.professores.get(professor_id) if self.professores else None
        if professor is None or professor.tenant_id != tenant_id:
            raise ValueError("Professor não encontrado para o tenant.")
        s.professor_id = professor.id
        s.professor_nome = professor.nome
        return s


class FakeAlunoRepo:
    def __init__(self) -> None:
        self.alunos: dict[uuid.UUID, "Aluno"] = {}
        # Resolve responsáveis pelo id ao vincular (compartilhado com o FakeContatoRepo).
        self.contatos: FakeContatoRepo | None = None

    async def criar(self, aluno):
        self.alunos[aluno.id] = aluno
        return aluno

    async def obter(self, *, tenant_id, aluno_id):
        a = self.alunos.get(aluno_id)
        return a if a and a.tenant_id == tenant_id else None

    async def listar(
        self,
        *,
        tenant_id,
        sala_id=None,
        apenas_ativos=None,
        q="",
        pagina=None,
        por_pagina=None,
    ):
        return _fatiar(
            self._filtrar(tenant_id, sala_id, apenas_ativos, q), pagina, por_pagina
        )

    async def contar(self, *, tenant_id, sala_id=None, apenas_ativos=None, q=""):
        return len(self._filtrar(tenant_id, sala_id, apenas_ativos, q))

    def _filtrar(self, tenant_id, sala_id, apenas_ativos, q=""):
        termo = (q or "").strip().casefold()
        return [
            a
            for a in self.alunos.values()
            if a.tenant_id == tenant_id
            and (sala_id is None or a.sala_id == sala_id)
            and (apenas_ativos is None or a.ativo is apenas_ativos)
            and (
                not termo
                or termo in a.nome.casefold()
                or termo in (a.matricula or "").casefold()
            )
        ]

    async def atualizar(self, aluno):
        self.alunos[aluno.id] = aluno
        return aluno

    async def remover(self, *, tenant_id, aluno_id):
        a = self.alunos.get(aluno_id)
        if a is None or a.tenant_id != tenant_id:
            return False
        del self.alunos[aluno_id]
        return True

    async def vincular_responsavel(self, *, tenant_id, aluno_id, contato_id):
        a = await self.obter(tenant_id=tenant_id, aluno_id=aluno_id)
        if a is None:
            raise ValueError("Aluno não encontrado para o tenant.")
        contato = self.contatos.contatos.get(contato_id) if self.contatos else None
        if contato is None or contato.tenant_id != tenant_id:
            raise ValueError("Responsável não encontrado para o tenant.")
        if all(c.id != contato_id for c in a.responsaveis):
            a.responsaveis.append(contato)

    async def desvincular_responsavel(self, *, tenant_id, aluno_id, contato_id):
        a = await self.obter(tenant_id=tenant_id, aluno_id=aluno_id)
        if a is None:
            raise ValueError("Aluno não encontrado para o tenant.")
        a.responsaveis = [c for c in a.responsaveis if c.id != contato_id]


# --------------------------------------------------------------------------- #
# Onda 2 — comunicação interna, mediação pai↔professor e cota de impressão
# --------------------------------------------------------------------------- #
class FakeSolicitacaoInternaRepo:
    def __init__(self) -> None:
        self.solicitacoes: dict[uuid.UUID, object] = {}

    async def criar(self, solicitacao):
        self.solicitacoes[solicitacao.id] = solicitacao
        return solicitacao

    async def obter(self, *, tenant_id, solicitacao_id):
        s = self.solicitacoes.get(solicitacao_id)
        return s if s and s.tenant_id == tenant_id else None

    async def listar(self, *, tenant_id, categoria=None, status=None, professor_id=None):
        itens = [
            s
            for s in self.solicitacoes.values()
            if s.tenant_id == tenant_id
            and (categoria is None or s.categoria.value == categoria)
            and (status is None or s.status == status)
            and (professor_id is None or s.professor_id == professor_id)
        ]
        itens.sort(key=lambda s: s.criado_em, reverse=True)
        return itens

    async def atualizar(self, solicitacao):
        self.solicitacoes[solicitacao.id] = solicitacao
        return solicitacao

    async def remover(self, *, tenant_id, solicitacao_id):
        s = self.solicitacoes.get(solicitacao_id)
        if s is None or s.tenant_id != tenant_id:
            return False
        del self.solicitacoes[solicitacao_id]
        return True


class FakeMediacaoRepo:
    def __init__(self) -> None:
        self.mensagens: list = []

    async def registrar(self, mensagem):
        self.mensagens.append(mensagem)
        return mensagem

    async def conversa(self, *, tenant_id, professor_id, contato_telefone):
        itens = [
            m
            for m in self.mensagens
            if m.tenant_id == tenant_id
            and m.professor_id == professor_id
            and m.contato_telefone == contato_telefone
        ]
        itens.sort(key=lambda m: m.criado_em)
        return itens

    async def interlocutores(self, *, tenant_id, professor_id):
        itens = [
            m
            for m in self.mensagens
            if m.tenant_id == tenant_id and m.professor_id == professor_id
        ]
        itens.sort(key=lambda m: m.criado_em)
        return itens


class FakeCotaImpressaoRepo:
    def __init__(self) -> None:
        self.cotas: dict[tuple, object] = {}

    async def definir(self, cota):
        self.cotas[(cota.tenant_id, cota.professor_id)] = cota
        return cota

    async def por_professor(self, *, tenant_id, professor_id):
        return self.cotas.get((tenant_id, professor_id))

    async def listar(self, *, tenant_id):
        return [c for c in self.cotas.values() if c.tenant_id == tenant_id]

    async def remover(self, *, tenant_id, professor_id):
        chave = (tenant_id, professor_id)
        if chave not in self.cotas:
            return False
        del self.cotas[chave]
        return True


class FakeTenantRepo:
    """Fake mínimo de TenantRepository para resolver o número de WhatsApp da escola."""

    def __init__(self, tenants=None) -> None:
        self.tenants: dict[uuid.UUID, object] = {t.id: t for t in (tenants or [])}

    async def obter(self, tenant_id):
        return self.tenants.get(tenant_id)


# --------------------------------------------------------------------------- #
# Onda 3 — falta/eventual (I1), ficha de matrícula (D1/D2/D3), matrícula (E1)
# --------------------------------------------------------------------------- #
class FakeAvisoFaltaRepo:
    def __init__(self) -> None:
        self.avisos: dict[uuid.UUID, object] = {}

    async def criar(self, aviso):
        self.avisos[aviso.id] = aviso
        return aviso

    async def obter(self, *, tenant_id, aviso_id):
        a = self.avisos.get(aviso_id)
        return a if a and a.tenant_id == tenant_id else None

    async def listar(self, *, tenant_id, status=None):
        itens = [
            a
            for a in self.avisos.values()
            if a.tenant_id == tenant_id and (status is None or a.status == status)
        ]
        itens.sort(key=lambda a: a.criado_em, reverse=True)
        return itens

    async def atualizar(self, aviso):
        if aviso.id not in self.avisos:
            raise ValueError("Aviso de falta não encontrado para o tenant.")
        self.avisos[aviso.id] = aviso
        return aviso

    async def remover(self, *, tenant_id, aviso_id):
        a = self.avisos.get(aviso_id)
        if a is None or a.tenant_id != tenant_id:
            return False
        del self.avisos[aviso_id]
        return True


class FakeFichaMatriculaRepo:
    def __init__(self) -> None:
        self.fichas: dict[tuple, object] = {}

    async def salvar(self, ficha):
        chave = (ficha.tenant_id, ficha.aluno_id)
        existente = self.fichas.get(chave)
        if existente is not None:
            ficha.id = existente.id
            ficha.criado_em = existente.criado_em
        self.fichas[chave] = ficha
        return ficha

    async def por_aluno(self, *, tenant_id, aluno_id):
        return self.fichas.get((tenant_id, aluno_id))

    async def remover(self, *, tenant_id, aluno_id):
        chave = (tenant_id, aluno_id)
        if chave not in self.fichas:
            return False
        del self.fichas[chave]
        return True


class FakeSolicitacaoMatriculaRepo:
    def __init__(self) -> None:
        self.solicitacoes: dict[uuid.UUID, object] = {}

    async def criar(self, solicitacao):
        self.solicitacoes[solicitacao.id] = solicitacao
        return solicitacao

    async def obter(self, *, tenant_id, solicitacao_id):
        s = self.solicitacoes.get(solicitacao_id)
        return s if s and s.tenant_id == tenant_id else None

    async def por_telefone(self, *, tenant_id, telefone):
        abertas = [
            s
            for s in self.solicitacoes.values()
            if s.tenant_id == tenant_id
            and s.contato_telefone == telefone
            and s.status.value not in ("concluida", "cancelada")
        ]
        abertas.sort(key=lambda s: s.criado_em, reverse=True)
        return abertas[0] if abertas else None

    async def listar(self, *, tenant_id, status=None):
        itens = [
            s
            for s in self.solicitacoes.values()
            if s.tenant_id == tenant_id and (status is None or s.status == status)
        ]
        itens.sort(key=lambda s: s.criado_em, reverse=True)
        return itens

    async def atualizar(self, solicitacao):
        if solicitacao.id not in self.solicitacoes:
            raise ValueError("Solicitação de matrícula não encontrada para o tenant.")
        self.solicitacoes[solicitacao.id] = solicitacao
        return solicitacao


class FakeConversaExportRepo:
    """Fake de ConversaRepository focado na exportação (§H1): conversas + mensagens."""

    def __init__(self) -> None:
        self.conversas: dict[uuid.UUID, object] = {}
        self._mensagens: dict[uuid.UUID, list] = {}

    def registrar_conversa(self, conversa, mensagens) -> None:
        self.conversas[conversa.id] = conversa
        self._mensagens[conversa.id] = list(mensagens)

    async def obter_conversa(self, *, tenant_id, conversa_id):
        c = self.conversas.get(conversa_id)
        return c if c and c.tenant_id == tenant_id else None

    async def mensagens(self, *, conversa_id):
        return list(self._mensagens.get(conversa_id, []))


class FakeAtendimentoHumanoRepo:
    """Fila de atendimento humano (§6j) em memória."""

    def __init__(self) -> None:
        self.itens: dict[uuid.UUID, object] = {}

    async def criar(self, atendimento):
        self.itens[atendimento.id] = atendimento
        return atendimento

    async def obter(self, *, tenant_id, atendimento_id):
        item = self.itens.get(atendimento_id)
        return item if item and item.tenant_id == tenant_id else None

    async def em_aberto_por_conversa(self, *, conversa_id):
        vivos = [
            a
            for a in self.itens.values()
            if a.conversa_id == conversa_id
            and a.status.value in ("oferecido", "aberto", "em_atendimento")
        ]
        vivos.sort(key=lambda a: a.criado_em, reverse=True)
        return vivos[0] if vivos else None

    def _filtrados(self, *, tenant_id, status, atendente_id):
        itens = [a for a in self.itens.values() if a.tenant_id == tenant_id]
        if status:
            alvo = {s.value for s in status}
            itens = [a for a in itens if a.status.value in alvo]
        if atendente_id is not None:
            itens = [a for a in itens if a.atendente_id == atendente_id]
        itens.sort(key=lambda a: a.criado_em)
        return itens

    async def listar(
        self, *, tenant_id, status=None, atendente_id=None, pagina=None, por_pagina=None
    ):
        itens = self._filtrados(
            tenant_id=tenant_id, status=status, atendente_id=atendente_id
        )
        if pagina is not None and por_pagina is not None:
            inicio = (pagina - 1) * por_pagina
            return itens[inicio : inicio + por_pagina]
        return itens

    async def contar(self, *, tenant_id, status=None, atendente_id=None):
        return len(
            self._filtrados(tenant_id=tenant_id, status=status, atendente_id=atendente_id)
        )

    async def atualizar(self, atendimento):
        if atendimento.id not in self.itens:
            raise ValueError("Atendimento não encontrado.")
        self.itens[atendimento.id] = atendimento
        return atendimento


class FakeDocumentoRecebidoRepo:
    """Metadados dos arquivos recebidos (§6k), em memória."""

    def __init__(self) -> None:
        self.itens: dict[uuid.UUID, object] = {}

    async def criar(self, documento):
        self.itens[documento.id] = documento
        return documento

    async def descartados_por_numero(self, *, tenant_id, desde, minimo):
        from app.domain.entities import StatusDocumento, SugestaoBloqueio

        por_numero: dict[str, list] = {}
        for d in self.itens.values():
            if (
                d.tenant_id == tenant_id
                and d.status is StatusDocumento.DESCARTADO
                and d.criado_em >= desde
            ):
                por_numero.setdefault(d.contato, []).append(d)
        return [
            SugestaoBloqueio(
                telefone=tel,
                descartados=len(ds),
                contato_nome=next((d.contato_nome for d in ds if d.contato_nome), ""),
                ultimo_em=max(d.criado_em for d in ds),
            )
            for tel, ds in por_numero.items()
            if len(ds) >= minimo
        ]

    async def obter(self, *, tenant_id, documento_id):
        d = self.itens.get(documento_id)
        return d if d and d.tenant_id == tenant_id else None

    async def por_media_id(self, *, tenant_id, media_id):
        if not media_id:
            return None
        return next(
            (
                d
                for d in self.itens.values()
                if d.tenant_id == tenant_id and d.media_id == media_id
            ),
            None,
        )

    def _filtrados(self, *, tenant_id, categoria, status, aluno_id):
        itens = [d for d in self.itens.values() if d.tenant_id == tenant_id]
        if categoria is not None:
            itens = [d for d in itens if d.categoria is categoria]
        if status is not None:
            itens = [d for d in itens if d.status is status]
        if aluno_id is not None:
            itens = [d for d in itens if d.aluno_id == aluno_id]
        itens.sort(key=lambda d: d.criado_em, reverse=True)
        return itens

    async def listar(
        self,
        *,
        tenant_id,
        categoria=None,
        status=None,
        aluno_id=None,
        pagina=None,
        por_pagina=None,
    ):
        itens = self._filtrados(
            tenant_id=tenant_id, categoria=categoria, status=status, aluno_id=aluno_id
        )
        return _fatiar(itens, pagina, por_pagina)

    async def contar(self, *, tenant_id, categoria=None, status=None, aluno_id=None):
        return len(
            self._filtrados(
                tenant_id=tenant_id, categoria=categoria, status=status, aluno_id=aluno_id
            )
        )

    async def atualizar(self, documento):
        self.itens[documento.id] = documento
        return documento

    async def expirados(self, *, limite=500):
        agora = datetime.now(timezone.utc)
        vencidos = [d for d in self.itens.values() if d.expira_em and d.expira_em <= agora]
        vencidos.sort(key=lambda d: d.expira_em)
        return vencidos[:limite]

    async def remover(self, *, tenant_id, documento_id):
        d = self.itens.get(documento_id)
        if d is None or d.tenant_id != tenant_id:
            return False
        del self.itens[documento_id]
        return True


class FakeFonteMidia:
    """Devolve um ``ArquivoBaixado`` roteirizado por ``media_id``."""

    def __init__(self, arquivos: dict[str, object] | None = None) -> None:
        self.arquivos = dict(arquivos or {})
        self.baixados: list[str] = []

    async def baixar(self, media_id: str):
        self.baixados.append(media_id)
        return self.arquivos.get(media_id)


class FakeNumeroBloqueadoRepo:
    """Números com envio de mídia recusado (§4.5)."""

    def __init__(self) -> None:
        self.bloqueios: dict[tuple, "NumeroBloqueado"] = {}

    async def bloquear(self, bloqueio):
        self.bloqueios[(bloqueio.tenant_id, bloqueio.telefone)] = bloqueio
        return bloqueio

    async def desbloquear(self, *, tenant_id, telefone):
        return self.bloqueios.pop((tenant_id, telefone), None) is not None

    async def bloqueado(self, *, tenant_id, telefone):
        return (tenant_id, telefone) in self.bloqueios

    async def listar(self, *, tenant_id):
        return [b for (t, _), b in self.bloqueios.items() if t == tenant_id]


class FakeWabaRepo:
    """Contas do WhatsApp Business. Por padrão, uma só — o cenário de hoje."""

    def __init__(self, wabas: list[Waba] | None = None) -> None:
        self.wabas = list(wabas) if wabas is not None else [waba_padrao()]

    async def listar(self, *, apenas_ativas: bool = False) -> list[Waba]:
        return [w for w in self.wabas if w.ativo or not apenas_ativas]

    async def obter(self, waba_id) -> Waba | None:
        return next((w for w in self.wabas if w.id == waba_id), None)

    async def por_meta_id(self, meta_waba_id) -> Waba | None:
        if not meta_waba_id:
            return None
        return next((w for w in self.wabas if w.meta_waba_id == meta_waba_id), None)

    async def salvar(self, waba: Waba) -> Waba:
        for i, existente in enumerate(self.wabas):
            if existente.id == waba.id:
                self.wabas[i] = waba
                return waba
        self.wabas.append(waba)
        return waba

    async def remover(self, waba_id) -> bool:
        antes = len(self.wabas)
        self.wabas = [w for w in self.wabas if w.id != waba_id]
        return len(self.wabas) != antes

    async def total_escolas(self) -> dict:
        return {}


WABA_PADRAO_ID = uuid.UUID("00000000-0000-0000-0000-00000000fa01")


def waba_padrao() -> Waba:
    return Waba(id=WABA_PADRAO_ID, meta_waba_id="900900900", nome="WABA principal")


def template_aprovado(template: MessageTemplate, *, waba_id=WABA_PADRAO_ID) -> MessageTemplate:
    """Marca o template como aprovado **naquela conta** — o estado que libera o disparo."""
    template.wabas = [TemplateNaWaba(waba_id=waba_id, status=StatusTemplate.APROVADO)]
    return template
