"""Casos de uso do canal pai ↔ professor mediado (§A3).

O professor **não expõe o número pessoal**: quando responde, a mensagem sai pelo número
da própria escola (``Tenant.whatsapp_numero`` como ``remetente`` do ``MessageChannel``)
e fica registrada. As mensagens do responsável entram pelo mesmo canal e aparecem no
painel do professor. Sem framework/ORM/SDK.
"""

from __future__ import annotations

from uuid import UUID

from app.domain.entities import (
    DirecaoMensagem,
    InterlocutorMediado,
    MensagemMediada,
)
from app.domain.ports import (
    ContatoRepository,
    MediacaoRepository,
    MessageChannel,
    ProfessorRepository,
    TenantRepository,
)


class EnviarMensagemAoResponsavel:
    """O professor envia uma mensagem a um responsável, roteada pela escola.

    A saída usa o número da escola como ``remetente`` (o professor não é exposto). Se a
    escola não tem número próprio, cai no padrão do canal (``remetente=None``).
    """

    def __init__(
        self,
        *,
        mediacao: MediacaoRepository,
        professores: ProfessorRepository,
        canal: MessageChannel,
        tenants: TenantRepository | None = None,
        contatos: ContatoRepository | None = None,
    ) -> None:
        self._mediacao = mediacao
        self._professores = professores
        self._canal = canal
        self._tenants = tenants
        self._contatos = contatos

    async def executar(
        self,
        *,
        tenant_id: UUID,
        professor_id: UUID,
        contato_telefone: str,
        corpo: str,
    ) -> MensagemMediada:
        corpo = corpo.strip()
        contato_telefone = contato_telefone.strip()
        if not contato_telefone:
            raise ValueError("Informe o telefone (WhatsApp) do responsável.")
        if not corpo:
            raise ValueError("Informe o conteúdo da mensagem.")

        professor = await self._professores.obter(
            tenant_id=tenant_id, professor_id=professor_id
        )
        if professor is None:
            raise ValueError("Professor não encontrado para o tenant.")

        remetente: str | None = None
        if self._tenants is not None:
            tenant = await self._tenants.obter(tenant_id)
            if tenant is not None and tenant.whatsapp_numero.strip():
                remetente = tenant.whatsapp_numero.strip()

        contato_nome = ""
        if self._contatos is not None:
            contato = await self._contatos.por_telefone(
                tenant_id=tenant_id, telefone=contato_telefone
            )
            if contato is not None:
                contato_nome = contato.nome

        await self._canal.enviar_texto(
            contato=contato_telefone, texto=corpo, remetente=remetente
        )
        return await self._mediacao.registrar(
            MensagemMediada(
                tenant_id=tenant_id,
                professor_id=professor_id,
                contato_telefone=contato_telefone,
                contato_nome=contato_nome,
                professor_nome=professor.nome,
                direcao=DirecaoMensagem.PROFESSOR_PARA_RESPONSAVEL,
                corpo=corpo,
            )
        )


class RegistrarMensagemDoResponsavel:
    """Registra uma mensagem recebida de um responsável, direcionada a um professor.

    Ponto de entrada para o inbound roteado (webhook/secretaria) alimentar o painel do
    professor. Valida que o professor pertence ao tenant.
    """

    def __init__(
        self,
        *,
        mediacao: MediacaoRepository,
        professores: ProfessorRepository,
        contatos: ContatoRepository | None = None,
    ) -> None:
        self._mediacao = mediacao
        self._professores = professores
        self._contatos = contatos

    async def executar(
        self,
        *,
        tenant_id: UUID,
        professor_id: UUID,
        contato_telefone: str,
        corpo: str,
        contato_nome: str = "",
    ) -> MensagemMediada:
        corpo = corpo.strip()
        contato_telefone = contato_telefone.strip()
        if not contato_telefone:
            raise ValueError("Informe o telefone (WhatsApp) do responsável.")
        if not corpo:
            raise ValueError("Informe o conteúdo da mensagem.")

        professor = await self._professores.obter(
            tenant_id=tenant_id, professor_id=professor_id
        )
        if professor is None:
            raise ValueError("Professor não encontrado para o tenant.")

        nome = contato_nome.strip()
        if not nome and self._contatos is not None:
            contato = await self._contatos.por_telefone(
                tenant_id=tenant_id, telefone=contato_telefone
            )
            if contato is not None:
                nome = contato.nome

        return await self._mediacao.registrar(
            MensagemMediada(
                tenant_id=tenant_id,
                professor_id=professor_id,
                contato_telefone=contato_telefone,
                contato_nome=nome,
                professor_nome=professor.nome,
                direcao=DirecaoMensagem.RESPONSAVEL_PARA_PROFESSOR,
                corpo=corpo,
            )
        )


class ListarConversaMediada:
    """Mensagens trocadas entre um professor e um responsável (thread, cronológica)."""

    def __init__(self, *, mediacao: MediacaoRepository) -> None:
        self._mediacao = mediacao

    async def executar(
        self, *, tenant_id: UUID, professor_id: UUID, contato_telefone: str
    ) -> list[MensagemMediada]:
        return await self._mediacao.conversa(
            tenant_id=tenant_id,
            professor_id=professor_id,
            contato_telefone=contato_telefone.strip(),
        )


class ListarInterlocutoresDoProfessor:
    """Responsáveis com quem o professor conversou, resumidos (para a caixa de entrada)."""

    def __init__(self, *, mediacao: MediacaoRepository) -> None:
        self._mediacao = mediacao

    async def executar(
        self, *, tenant_id: UUID, professor_id: UUID
    ) -> list[InterlocutorMediado]:
        mensagens = await self._mediacao.interlocutores(
            tenant_id=tenant_id, professor_id=professor_id
        )
        # As mensagens vêm em ordem cronológica; agrega por telefone do responsável.
        resumo: dict[str, InterlocutorMediado] = {}
        for m in mensagens:
            atual = resumo.get(m.contato_telefone)
            if atual is None:
                resumo[m.contato_telefone] = InterlocutorMediado(
                    contato_telefone=m.contato_telefone,
                    contato_nome=m.contato_nome,
                    total_mensagens=1,
                    ultima_em=m.criado_em,
                    ultima_previa=m.corpo[:120],
                )
            else:
                atual.total_mensagens += 1
                atual.ultima_em = m.criado_em
                atual.ultima_previa = m.corpo[:120]
                if m.contato_nome:
                    atual.contato_nome = m.contato_nome
        # Mais recentes primeiro.
        return sorted(
            resumo.values(),
            key=lambda i: i.ultima_em or i.contato_telefone,
            reverse=True,
        )
