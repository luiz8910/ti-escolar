"""Implementações em memória das portas, para testar os casos de uso sem BD/rede."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.domain.entities import (
    Aluno,
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
    TrechoConhecimento,
    TurnoConversa,
)
from app.infrastructure.llm.fake_provider import FakeEmbedder


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
    def __init__(self) -> None:
        self.mensagens: dict[uuid.UUID, list[dict]] = {}
        self.conversas: dict[tuple, Conversa] = {}

    async def obter_ou_criar(self, *, tenant_id, contato) -> Conversa:
        chave = (tenant_id, contato)
        if chave not in self.conversas:
            c = Conversa(tenant_id=tenant_id, contato=contato)
            self.conversas[chave] = c
            self.mensagens[c.id] = []
        return self.conversas[chave]

    async def adicionar_mensagem(self, *, conversa_id, autor, texto, fontes=None) -> None:
        self.mensagens.setdefault(conversa_id, []).append(
            {"autor": autor, "texto": texto, "fontes": fontes or []}
        )

    async def historico(self, *, conversa_id, limite=20) -> list[dict[str, str]]:
        msgs = self.mensagens.get(conversa_id, [])[-limite:]
        return [
            {"role": "assistant" if m["autor"] == "bot" else "user", "content": m["texto"]}
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
        return f"wamid:{contato}"

    async def enviar_documento(self, *, contato, documento, remetente=None) -> str:
        self.enviados.append((contato, "documento"))
        return "x"


class FakeQuota:
    def __init__(self, *, limite_diario: int) -> None:
        self._quotas: dict[uuid.UUID, MessageQuota] = {}
        self._limite = limite_diario

    def _q(self, tenant_id) -> MessageQuota:
        if tenant_id not in self._quotas:
            self._quotas[tenant_id] = MessageQuota(
                tenant_id=tenant_id,
                limite_diario=self._limite,
                dia=datetime.now(timezone.utc).date().isoformat(),
            )
        return self._quotas[tenant_id]

    async def cota_do_dia(self, tenant_id) -> MessageQuota:
        return self._q(tenant_id)

    async def consumir(self, tenant_id, quantidade) -> MessageQuota:
        q = self._q(tenant_id)
        q.enviados += quantidade
        return q


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

    async def listar(self, *, tenant_id):
        return [b for b in self.salvos.values() if b.tenant_id == tenant_id]

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
    def __init__(self, template: MessageTemplate | None = None) -> None:
        self._template = template

    async def obter(self, *, tenant_id, template_id) -> MessageTemplate | None:
        if self._template and self._template.tenant_id == tenant_id:
            return self._template
        return None


class FakeAuditLogRepo:
    def __init__(self) -> None:
        self.registros: list = []

    async def registrar(self, registro):
        self.registros.append(registro)
        return registro

    async def listar(self, *, tenant_id, limite: int = 200):
        registros = [r for r in self.registros if r.tenant_id == tenant_id]
        registros.sort(key=lambda r: r.criado_em, reverse=True)
        return registros[:limite]


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

    async def listar(self, *, tenant_id):
        return [c for c in self.contatos.values() if c.tenant_id == tenant_id]

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

    async def listar(self, *, tenant_id):
        return [p for p in self.professores.values() if p.tenant_id == tenant_id]

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
        # Resolve pais pelo id para o vínculo (compartilhado com o FakeContatoRepo nos testes).
        self.contatos: FakeContatoRepo | None = None
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

    async def atualizar(self, *, tenant_id, sala_id, nome, descricao):
        s = await self.obter(tenant_id=tenant_id, sala_id=sala_id)
        if s is None:
            raise ValueError("Sala não encontrada para o tenant.")
        s.nome = nome
        s.descricao = descricao
        return s

    async def remover(self, *, tenant_id, sala_id):
        s = await self.obter(tenant_id=tenant_id, sala_id=sala_id)
        if s is None:
            return False
        del self.salas[sala_id]
        return True

    async def vincular_pai(self, *, tenant_id, sala_id, contato_id):
        s = await self.obter(tenant_id=tenant_id, sala_id=sala_id)
        if s is None:
            raise ValueError("Sala não encontrada para o tenant.")
        contato = self.contatos.contatos.get(contato_id) if self.contatos else None
        if contato is None or contato.tenant_id != tenant_id:
            raise ValueError("Pai/responsável não encontrado para o tenant.")
        if all(c.id != contato_id for c in s.pais):
            s.pais.append(contato)

    async def desvincular_pai(self, *, tenant_id, sala_id, contato_id):
        s = await self.obter(tenant_id=tenant_id, sala_id=sala_id)
        if s is None:
            raise ValueError("Sala não encontrada para o tenant.")
        s.pais = [c for c in s.pais if c.id != contato_id]

    async def pais(self, *, tenant_id, sala_id):
        s = await self.obter(tenant_id=tenant_id, sala_id=sala_id)
        if s is None:
            raise ValueError("Sala não encontrada para o tenant.")
        return list(s.pais)

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

    async def listar(self, *, tenant_id, sala_id=None):
        return [
            a
            for a in self.alunos.values()
            if a.tenant_id == tenant_id and (sala_id is None or a.sala_id == sala_id)
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
