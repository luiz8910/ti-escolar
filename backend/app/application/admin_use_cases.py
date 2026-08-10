"""Casos de uso de administração: usuários, grupos e disparo direcionado a grupo."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.use_cases import EnviarBroadcast, ResultadoBroadcast
from app.domain.entities import (
    Broadcast,
    DestinatarioBroadcast,
    Grupo,
    Papel,
    Usuario,
)
from app.domain.ports import GrupoRepository, UsuarioRepository
from app.infrastructure.security import hash_senha, verificar_senha


# --------------------------------------------------------------------------- #
# Usuários (super admin / tenant admin)
# --------------------------------------------------------------------------- #
class CriarUsuario:
    """Cria um usuário administrativo.

    Regra: apenas um super admin pode criar outro super admin ou admins de qualquer
    tenant. Um admin de tenant só cria usuários dentro do seu próprio tenant.
    """

    def __init__(self, *, usuarios: UsuarioRepository) -> None:
        self._usuarios = usuarios

    async def executar(
        self,
        *,
        criador: Usuario,
        nome: str,
        email: str,
        senha: str,
        papel: Papel,
        tenant_id: UUID | None,
    ) -> Usuario:
        if papel == Papel.SUPER_ADMIN and not criador.eh_super_admin:
            raise PermissionError("Apenas o super admin pode criar outro super admin.")
        if not criador.eh_super_admin and tenant_id != criador.tenant_id:
            raise PermissionError("Admin de tenant só pode criar usuários do próprio tenant.")
        if papel == Papel.TENANT_ADMIN and tenant_id is None:
            raise ValueError("Admin de tenant exige tenant_id.")

        if await self._usuarios.por_email(email):
            raise ValueError("Já existe um usuário com este e-mail.")

        usuario = Usuario(
            nome=nome,
            email=email.lower(),
            senha_hash=hash_senha(senha),
            papel=papel,
            tenant_id=None if papel == Papel.SUPER_ADMIN else tenant_id,
        )
        return await self._usuarios.criar(usuario)


class AtualizarUsuario:
    """Edita um usuário administrativo: nome, senha e situação (ativo/inativo).

    Não mexe em ``papel`` nem em ``tenant_id``: mudar o papel de alguém é criar outro
    tipo de conta, e permitir isso na tela de edição abriria a porta para um admin de
    escola se promover a super admin. Para trocar de papel, cria-se um usuário novo.

    ``ativo=False`` é a forma de **desligar** uma funcionária: a sessão dela cai na
    requisição seguinte (``usuario_autenticado`` revalida no banco), mas o histórico do
    que ela respondeu aos responsáveis permanece.
    """

    def __init__(self, *, usuarios: UsuarioRepository) -> None:
        self._usuarios = usuarios

    async def executar(
        self,
        *,
        editor: Usuario,
        usuario_id: UUID,
        nome: str | None = None,
        senha: str | None = None,
        ativo: bool | None = None,
    ) -> Usuario:
        alvo = await self._usuarios.obter(usuario_id)
        if alvo is None:
            raise ValueError("Usuário não encontrado.")
        if not editor.eh_super_admin:
            if alvo.eh_super_admin or alvo.tenant_id != editor.tenant_id:
                raise PermissionError("Você só pode editar usuários da própria escola.")

        if nome is not None:
            nome = nome.strip()
            if not nome:
                raise ValueError("O nome do usuário é obrigatório.")
            alvo.nome = nome
        if senha:
            alvo.senha_hash = hash_senha(senha)
        if ativo is not None:
            # Desativar a si mesmo derruba a própria sessão e, no caso de um super admin
            # sozinho, tranca a plataforma inteira para fora.
            if not ativo and alvo.id == editor.id:
                raise ValueError("Você não pode desativar a própria conta.")
            alvo.ativo = ativo

        return await self._usuarios.atualizar(alvo)


class AutenticarUsuario:
    def __init__(self, *, usuarios: UsuarioRepository) -> None:
        self._usuarios = usuarios

    async def executar(self, *, email: str, senha: str) -> Usuario | None:
        usuario = await self._usuarios.por_email(email)
        if usuario is None or not usuario.ativo:
            return None
        if not verificar_senha(senha, usuario.senha_hash):
            return None
        return usuario


# --------------------------------------------------------------------------- #
# Grupos e contatos
# --------------------------------------------------------------------------- #
class CriarGrupo:
    def __init__(self, *, grupos: GrupoRepository) -> None:
        self._grupos = grupos

    async def executar(self, *, tenant_id: UUID, nome: str, descricao: str = "") -> Grupo:
        return await self._grupos.criar(Grupo(tenant_id=tenant_id, nome=nome, descricao=descricao))


class AdicionarContatoAoGrupo:
    def __init__(self, *, grupos: GrupoRepository) -> None:
        self._grupos = grupos

    async def executar(self, *, tenant_id: UUID, grupo_id: UUID, nome: str, telefone: str):
        return await self._grupos.adicionar_contato(
            tenant_id=tenant_id, grupo_id=grupo_id, nome=nome, telefone=telefone
        )


@dataclass
class ResultadoEnvioGrupo:
    grupo_id: UUID
    total_contatos: int
    broadcast: ResultadoBroadcast


class EnviarBroadcastParaGrupo:
    """Envia uma mensagem (via template aprovado) apenas aos contatos de um grupo.

    Resolve os membros do grupo em destinatários e delega a ``EnviarBroadcast``, que
    aplica template aprovado, rate limiting e cota diária (tier Meta).
    """

    def __init__(self, *, grupos: GrupoRepository, enviar: EnviarBroadcast) -> None:
        self._grupos = grupos
        self._enviar = enviar

    async def executar(
        self,
        *,
        tenant_id: UUID,
        grupo_id: UUID,
        template_id: UUID,
        titulo: str,
        mensagem: str,
    ) -> ResultadoEnvioGrupo:
        contatos = await self._grupos.membros(tenant_id=tenant_id, grupo_id=grupo_id)
        if not contatos:
            raise ValueError("Grupo sem contatos ou inexistente.")

        # Parâmetros do template padrão: {{1}} = nome do responsável, {{2}} = mensagem.
        destinatarios = [
            DestinatarioBroadcast(contato=c.telefone, parametros=[c.nome, mensagem])
            for c in contatos
        ]
        broadcast = Broadcast(
            tenant_id=tenant_id,
            template_id=template_id,
            titulo=titulo,
            destinatarios=destinatarios,
        )
        resultado = await self._enviar.executar(broadcast=broadcast)
        return ResultadoEnvioGrupo(
            grupo_id=grupo_id, total_contatos=len(contatos), broadcast=resultado
        )
