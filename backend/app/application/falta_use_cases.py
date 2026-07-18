"""Casos de uso do aviso de falta de professor e chamada de eventual (§I1).

O professor avisa a falta pelo sistema; a secretaria dispara o pedido de **substituto
(eventual)** para uma lista de candidatos e registra quem confirmou. Centraliza e
registra o que hoje é planilha + print manual de grupo. Sem framework/ORM/SDK.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from app.domain.entities import AvisoFalta, StatusFalta, _now
from app.domain.ports import (
    AvisoFaltaRepository,
    MessageChannel,
    ProfessorRepository,
    TenantRepository,
)


class RegistrarFaltaProfessor:
    """Registra a falta de um professor num dia (abre o aviso, ainda sem eventual)."""

    def __init__(
        self,
        *,
        faltas: AvisoFaltaRepository,
        professores: ProfessorRepository | None = None,
    ) -> None:
        self._faltas = faltas
        self._professores = professores

    async def executar(
        self,
        *,
        tenant_id: UUID,
        data: str,
        motivo: str = "",
        professor_id: UUID | None = None,
        professor_nome: str = "",
    ) -> AvisoFalta:
        data = (data or "").strip()
        if not data:
            raise ValueError("Informe a data da falta (YYYY-MM-DD).")

        nome = professor_nome.strip()
        if professor_id is not None and self._professores is not None:
            professor = await self._professores.obter(
                tenant_id=tenant_id, professor_id=professor_id
            )
            if professor is None:
                raise ValueError("Professor não encontrado para o tenant.")
            nome = professor.nome

        return await self._faltas.criar(
            AvisoFalta(
                tenant_id=tenant_id,
                data=data,
                motivo=motivo.strip(),
                professor_id=professor_id,
                professor_nome=nome,
            )
        )


class ListarFaltas:
    """Lista os avisos de falta do tenant (opcionalmente por status)."""

    def __init__(self, *, faltas: AvisoFaltaRepository) -> None:
        self._faltas = faltas

    async def executar(
        self, *, tenant_id: UUID, status: StatusFalta | None = None
    ) -> list[AvisoFalta]:
        return await self._faltas.listar(tenant_id=tenant_id, status=status)


class ChamarEventual:
    """Dispara o pedido de eventual (substituto) para uma lista de candidatos.

    Notifica cada telefone pelo ``MessageChannel`` (a partir do número da escola, se
    houver) e registra os telefones chamados no aviso. A falta segue **aberta** até a
    confirmação de um eventual (``ConfirmarEventual``).
    """

    def __init__(
        self,
        *,
        faltas: AvisoFaltaRepository,
        canal: MessageChannel,
        tenants: TenantRepository | None = None,
    ) -> None:
        self._faltas = faltas
        self._canal = canal
        self._tenants = tenants

    async def executar(
        self,
        *,
        tenant_id: UUID,
        aviso_id: UUID,
        telefones: Sequence[str],
        mensagem: str = "",
    ) -> AvisoFalta:
        alvos = [t.strip() for t in telefones if t and t.strip()]
        if not alvos:
            raise ValueError("Informe ao menos um telefone de eventual para chamar.")

        aviso = await self._faltas.obter(tenant_id=tenant_id, aviso_id=aviso_id)
        if aviso is None:
            raise ValueError("Aviso de falta não encontrado para o tenant.")
        if aviso.status == StatusFalta.CANCELADA:
            raise ValueError("Não é possível chamar eventual para uma falta cancelada.")

        remetente: str | None = None
        if self._tenants is not None:
            tenant = await self._tenants.obter(tenant_id)
            if tenant is not None and tenant.whatsapp_numero.strip():
                remetente = tenant.whatsapp_numero.strip()

        texto = mensagem.strip() or self._mensagem_padrao(aviso)
        for telefone in alvos:
            await self._canal.enviar_texto(
                contato=telefone, texto=texto, remetente=remetente
            )
            if telefone not in aviso.eventuais_chamados:
                aviso.eventuais_chamados.append(telefone)

        aviso.atualizado_em = _now()
        return await self._faltas.atualizar(aviso)

    @staticmethod
    def _mensagem_padrao(aviso: AvisoFalta) -> str:
        prof = f" ({aviso.professor_nome})" if aviso.professor_nome else ""
        return (
            f"Olá! Precisamos de um professor eventual para o dia {aviso.data}"
            f"{prof}. Você tem disponibilidade? Por favor, responda à secretaria."
        )


class ConfirmarEventual:
    """Marca a falta como **coberta** por um eventual confirmado."""

    def __init__(self, *, faltas: AvisoFaltaRepository) -> None:
        self._faltas = faltas

    async def executar(
        self,
        *,
        tenant_id: UUID,
        aviso_id: UUID,
        eventual_nome: str,
        eventual_telefone: str = "",
    ) -> AvisoFalta:
        nome = (eventual_nome or "").strip()
        if not nome:
            raise ValueError("Informe o nome do eventual que vai cobrir a falta.")

        aviso = await self._faltas.obter(tenant_id=tenant_id, aviso_id=aviso_id)
        if aviso is None:
            raise ValueError("Aviso de falta não encontrado para o tenant.")
        if aviso.status == StatusFalta.CANCELADA:
            raise ValueError("Não é possível cobrir uma falta cancelada.")

        aviso.eventual_nome = nome
        aviso.eventual_telefone = (eventual_telefone or "").strip()
        aviso.status = StatusFalta.COBERTA
        aviso.atualizado_em = _now()
        return await self._faltas.atualizar(aviso)


class CancelarFalta:
    """Cancela um aviso de falta (o professor compareceu, etc.)."""

    def __init__(self, *, faltas: AvisoFaltaRepository) -> None:
        self._faltas = faltas

    async def executar(self, *, tenant_id: UUID, aviso_id: UUID) -> AvisoFalta:
        aviso = await self._faltas.obter(tenant_id=tenant_id, aviso_id=aviso_id)
        if aviso is None:
            raise ValueError("Aviso de falta não encontrado para o tenant.")
        aviso.status = StatusFalta.CANCELADA
        aviso.atualizado_em = _now()
        return await self._faltas.atualizar(aviso)
