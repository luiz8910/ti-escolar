"""Casos de uso de administração: usuários, grupos e disparo direcionado a grupo."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.application.use_cases import EnviarBroadcast, ResultadoBroadcast
from app.application.validacao import normalizar_telefone
from app.application.validacao_template import placeholders_do_corpo
from app.domain.entities import (
    Broadcast,
    Cargo,
    DestinatarioBroadcast,
    Grupo,
    Papel,
    ParametroTemplate,
    Turno,
    Usuario,
)
from app.domain.ports import (
    GrupoRepository,
    TemplateRepository,
    TenantRepository,
    UsuarioRepository,
)
from app.infrastructure.security import hash_senha, verificar_senha


# --------------------------------------------------------------------------- #
# Usuários (super admin / tenant admin)
# --------------------------------------------------------------------------- #
@dataclass
class DadosUsuario:
    """Contato e lotação de um usuário da escola. Todos opcionais."""

    telefone: str = ""
    endereco: str = ""
    turno: Turno | None = None


def _validar_dados_usuario(dados: DadosUsuario) -> DadosUsuario:
    e164, aviso = normalizar_telefone(dados.telefone)
    if aviso:
        raise ValueError(f"Telefone: {aviso}")
    return DadosUsuario(telefone=e164, endereco=dados.endereco.strip(), turno=dados.turno)


def _exige_hierarquia(criador: Usuario, cargo: Cargo) -> None:
    """Só se gerencia alguém **estritamente abaixo** do próprio posto.

    Sem isto, a tela de equipe seria o caminho mais curto para escalar privilégio dentro
    da escola: a coordenadora cadastraria uma "diretora" e entraria com ela.
    """
    if criador.eh_super_admin:
        return
    if not criador.gere_usuarios:
        raise PermissionError("A secretaria não gerencia usuários.")
    if cargo.nivel >= criador.nivel_hierarquico:
        rotulo = criador.cargo.rotulo if criador.cargo else "Você"
        raise PermissionError(
            f"{rotulo} só pode gerenciar cargos abaixo do seu — {cargo.rotulo} não está."
        )


class CriarUsuario:
    """Cria um usuário administrativo.

    Três regras, em camadas:

    1. só um super admin cria outro super admin, ou usuários de outra escola;
    2. a **secretaria não gerencia usuários** (é a exceção do apontamento);
    3. dentro da escola, só se cria alguém **estritamente abaixo** do próprio cargo.

    O ``papel`` deixou de ser escolhido por quem cadastra: ele **decorre do cargo**
    (``Cargo.papel_correspondente``). Deixar os dois independentes permitiria criar uma
    "secretaria" com papel de admin — exatamente o que a exceção do apontamento proíbe.
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
        cargo: Cargo | None = None,
        dados: DadosUsuario | None = None,
    ) -> Usuario:
        if papel == Papel.SUPER_ADMIN and not criador.eh_super_admin:
            raise PermissionError("Apenas o super admin pode criar outro super admin.")
        if not criador.eh_super_admin and tenant_id != criador.tenant_id:
            raise PermissionError("Admin de tenant só pode criar usuários do próprio tenant.")

        if papel == Papel.SUPER_ADMIN:
            cargo = None  # não ocupa posto em escola nenhuma
        else:
            if tenant_id is None:
                raise ValueError("Usuário de escola exige tenant_id.")
            # Retrocompatível: quem não informa cargo cria um admin de escola, que é o
            # que ``papel=tenant_admin`` sempre significou.
            cargo = cargo or Cargo.DIRETOR
            _exige_hierarquia(criador, cargo)
            papel = cargo.papel_correspondente

        if await self._usuarios.por_email(email):
            raise ValueError("Já existe um usuário com este e-mail.")

        validos = _validar_dados_usuario(dados or DadosUsuario())
        usuario = Usuario(
            nome=nome,
            email=email.lower(),
            senha_hash=hash_senha(senha),
            papel=papel,
            tenant_id=None if papel == Papel.SUPER_ADMIN else tenant_id,
            cargo=cargo,
            telefone=validos.telefone,
            endereco=validos.endereco,
            turno=validos.turno,
        )
        return await self._usuarios.criar(usuario)


class AtualizarUsuario:
    """Edita um usuário: nome, senha, situação, contato e **cargo**.

    Não mexe em ``tenant_id``: mover alguém de escola é criar outra conta. O ``papel``
    também não é editável diretamente — ele **acompanha o cargo**, senão a tela de edição
    seria a porta para transformar uma secretaria em admin sem trocar o cargo dela.

    Três travas de hierarquia, e cada uma fecha um buraco diferente:

    - só se edita quem está **estritamente abaixo** (``manda_em``) — inclusive para trocar
      senha, que é como uma conta é tomada;
    - **ninguém muda o próprio cargo**, nem para cima nem para baixo: promover a si mesmo
      é o ataque óbvio, e rebaixar-se sozinho tranca a escola sem ninguém no topo;
    - o cargo **novo** também precisa estar abaixo de quem edita — senão o vice-diretor
      promoveria a coordenadora a diretora e usaria a conta dela.

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
        cargo: Cargo | None = None,
        dados: DadosUsuario | None = None,
    ) -> Usuario:
        alvo = await self._usuarios.obter(usuario_id)
        if alvo is None:
            raise ValueError("Usuário não encontrado.")
        # Editar a si mesmo é permitido (nome, senha, contato) — `manda_em` recusaria,
        # porque ninguém está estritamente acima de si.
        proprio = alvo.id == editor.id
        if not proprio and not editor.manda_em(alvo):
            raise PermissionError(
                "Você só pode editar usuários da própria escola com cargo abaixo do seu."
            )
        if not proprio and not editor.gere_usuarios:
            raise PermissionError("A secretaria não gerencia usuários.")

        if cargo is not None and cargo != alvo.cargo:
            if proprio:
                raise ValueError("Você não pode alterar o próprio cargo.")
            if alvo.eh_super_admin:
                raise PermissionError("O super admin não ocupa cargo em uma escola.")
            _exige_hierarquia(editor, cargo)
            alvo.cargo = cargo
            # O papel acompanha o cargo: sem isto, uma secretaria promovida a coordenadora
            # continuaria sem acesso, e uma coordenadora rebaixada continuaria com ele.
            alvo.papel = cargo.papel_correspondente

        if dados is not None:
            validos = _validar_dados_usuario(dados)
            alvo.telefone = validos.telefone
            alvo.endereco = validos.endereco
            alvo.turno = validos.turno

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
            if not ativo and proprio:
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

    def __init__(
        self,
        *,
        grupos: GrupoRepository,
        enviar: EnviarBroadcast,
        templates: TemplateRepository,
        tenants: TenantRepository,
    ) -> None:
        self._grupos = grupos
        self._enviar = enviar
        self._templates = templates
        self._tenants = tenants

    async def executar(
        self,
        *,
        tenant_id: UUID,
        grupo_id: UUID,
        template_id: UUID,
        titulo: str,
        parametros: Sequence[ParametroTemplate],
    ) -> ResultadoEnvioGrupo:
        contatos = await self._grupos.membros(tenant_id=tenant_id, grupo_id=grupo_id)
        if not contatos:
            raise ValueError("Grupo sem contatos ou inexistente.")

        template = await self._templates.obter(
            tenant_id=tenant_id, template_id=template_id
        )
        if template is None:
            raise ValueError("Template não encontrado para esta escola.")

        # **A contagem é conferida aqui, não descoberta na Graph API.** O disparo mandava
        # dois parâmetros fixos para um corpo que hoje tem três, e a Meta recusa por número
        # de parâmetros — erro que chega como falha de envio por destinatário, depois de a
        # cota já ter sido consumida.
        esperados = placeholders_do_corpo(template.corpo)
        if len(parametros) != len(esperados):
            raise ValueError(
                f"O template {template.nome!r} tem {len(esperados)} variável(is) "
                f"({', '.join('{{%d}}' % n for n in esperados) or 'nenhuma'}) e foram "
                f"informados {len(parametros)} valor(es). A Meta recusa o envio quando a "
                "contagem não bate."
            )

        escola = await self._tenants.obter(tenant_id)
        nome_escola = escola.nome if escola else ""

        destinatarios = [
            DestinatarioBroadcast(
                contato=c.telefone,
                parametros=[
                    p.resolver(responsavel=c.nome, escola=nome_escola) for p in parametros
                ],
            )
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
