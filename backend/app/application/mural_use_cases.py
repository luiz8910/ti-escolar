"""Casos de uso do mural do professor (§A1): recados da secretaria + confirmação de
leitura, e a autenticação do professor.

A camada de aplicação orquestra ``MuralRepository`` e ``ProfessorRepository`` (e o
``MessageChannel`` para re-notificar quem não leu). O hash de senha usa o utilitário
stdlib de ``infrastructure.security`` (mesmo padrão de ``AutenticarUsuario``).
"""

from __future__ import annotations

from uuid import UUID

from app.domain.entities import (
    Professor,
    Recado,
    RecadoDoProfessor,
    RecadoResumo,
    StatusLeituraRecado,
)
from app.domain.ports import MessageChannel, MuralRepository, ProfessorRepository
from app.infrastructure.security import verificar_senha


# --------------------------------------------------------------------------- #
# Autenticação do professor
# --------------------------------------------------------------------------- #
class AutenticarProfessor:
    """Valida telefone + senha do professor (login próprio do mural)."""

    def __init__(self, *, professores: ProfessorRepository) -> None:
        self._professores = professores

    async def executar(
        self, *, tenant_id: UUID, telefone: str, senha: str
    ) -> Professor | None:
        professor = await self._professores.por_telefone(
            tenant_id=tenant_id, telefone=telefone
        )
        if professor is None or not professor.senha_hash:
            return None
        if not verificar_senha(senha, professor.senha_hash):
            return None
        return professor


# --------------------------------------------------------------------------- #
# Publicação e gestão de recados (secretaria)
# --------------------------------------------------------------------------- #
class PublicarRecado:
    def __init__(self, *, mural: MuralRepository) -> None:
        self._mural = mural

    async def executar(
        self,
        *,
        tenant_id: UUID,
        titulo: str,
        corpo: str,
        autor_id: str = "",
        autor_nome: str = "",
    ) -> Recado:
        titulo = titulo.strip()
        corpo = corpo.strip()
        if not titulo:
            raise ValueError("O recado precisa de um título.")
        if not corpo:
            raise ValueError("O recado precisa de um corpo.")
        return await self._mural.criar(
            Recado(
                tenant_id=tenant_id,
                titulo=titulo,
                corpo=corpo,
                autor_id=autor_id,
                autor_nome=autor_nome,
            )
        )


class ListarRecados:
    """Lista os recados do tenant com os contadores de leitura (visão da secretaria)."""

    def __init__(
        self, *, mural: MuralRepository, professores: ProfessorRepository
    ) -> None:
        self._mural = mural
        self._professores = professores

    async def executar(self, *, tenant_id: UUID) -> list[RecadoResumo]:
        recados = await self._mural.listar(tenant_id=tenant_id)
        total_professores = len(await self._professores.listar(tenant_id=tenant_id))
        resumos: list[RecadoResumo] = []
        for recado in recados:
            leituras = await self._mural.leituras(recado_id=recado.id)
            resumos.append(
                RecadoResumo(
                    recado=recado,
                    total_professores=total_professores,
                    total_lidos=len(leituras),
                )
            )
        return resumos


class ObterStatusLeitura:
    """Detalha, para um recado, quem já leu (com data) e quem ainda não leu."""

    def __init__(
        self, *, mural: MuralRepository, professores: ProfessorRepository
    ) -> None:
        self._mural = mural
        self._professores = professores

    async def executar(
        self, *, tenant_id: UUID, recado_id: UUID
    ) -> StatusLeituraRecado:
        recado = await self._mural.obter(tenant_id=tenant_id, recado_id=recado_id)
        if recado is None:
            raise ValueError("Recado não encontrado para o tenant.")
        professores = await self._professores.listar(tenant_id=tenant_id)
        leituras = {
            leitura.professor_id: leitura.lido_em
            for leitura in await self._mural.leituras(recado_id=recado_id)
        }
        lidos: list[tuple[Professor, object]] = []
        nao_lidos: list[Professor] = []
        for professor in professores:
            if professor.id in leituras:
                lidos.append((professor, leituras[professor.id]))
            else:
                nao_lidos.append(professor)
        return StatusLeituraRecado(recado=recado, lidos=lidos, nao_lidos=nao_lidos)


class RemoverRecado:
    def __init__(self, *, mural: MuralRepository) -> None:
        self._mural = mural

    async def executar(self, *, tenant_id: UUID, recado_id: UUID) -> bool:
        return await self._mural.remover(tenant_id=tenant_id, recado_id=recado_id)


class ReNotificarRecadoNaoLido:
    """Re-notifica (WhatsApp) os professores que ainda não confirmaram a leitura.

    Envia um texto livre pelo ``MessageChannel`` ao telefone de cada professor que não
    leu o recado. Professores sem telefone são ignorados. Retorna quantos foram avisados.
    """

    def __init__(
        self,
        *,
        mural: MuralRepository,
        professores: ProfessorRepository,
        canal: MessageChannel,
    ) -> None:
        self._mural = mural
        self._professores = professores
        self._canal = canal

    async def executar(self, *, tenant_id: UUID, recado_id: UUID) -> int:
        status = await ObterStatusLeitura(
            mural=self._mural, professores=self._professores
        ).executar(tenant_id=tenant_id, recado_id=recado_id)
        texto = (
            f"🔔 Lembrete da secretaria: você ainda não confirmou a leitura do recado "
            f'"{status.recado.titulo}". Acesse o mural do professor para visualizar.'
        )
        avisados = 0
        for professor in status.nao_lidos:
            if not professor.telefone.strip():
                continue
            await self._canal.enviar_texto(contato=professor.telefone, texto=texto)
            avisados += 1
        return avisados


# --------------------------------------------------------------------------- #
# Visão do professor: seus recados + confirmação de leitura
# --------------------------------------------------------------------------- #
class ListarRecadosDoProfessor:
    """Recados do tenant na visão de um professor, com o seu status de leitura."""

    def __init__(self, *, mural: MuralRepository) -> None:
        self._mural = mural

    async def executar(
        self, *, tenant_id: UUID, professor_id: UUID
    ) -> list[RecadoDoProfessor]:
        recados = await self._mural.listar(tenant_id=tenant_id)
        lidos = {
            leitura.recado_id: leitura.lido_em
            for leitura in await self._mural.leituras_do_professor(
                tenant_id=tenant_id, professor_id=professor_id
            )
        }
        return [
            RecadoDoProfessor(
                recado=recado,
                lido=recado.id in lidos,
                lido_em=lidos.get(recado.id),
            )
            for recado in recados
        ]


class ConfirmarLeituraRecado:
    """O professor confirma ("tica") a leitura de um recado."""

    def __init__(self, *, mural: MuralRepository) -> None:
        self._mural = mural

    async def executar(
        self, *, tenant_id: UUID, recado_id: UUID, professor_id: UUID
    ) -> None:
        recado = await self._mural.obter(tenant_id=tenant_id, recado_id=recado_id)
        if recado is None:
            raise ValueError("Recado não encontrado para o tenant.")
        await self._mural.marcar_leitura(
            tenant_id=tenant_id, recado_id=recado_id, professor_id=professor_id
        )
