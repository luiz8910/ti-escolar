"""Cargos da escola e a hierarquia de quem gere quem (§2.4 do plano de 10/08).

O que se testa aqui é **escalada de privilégio**, não o caminho feliz. A tela de equipe é
o ponto mais tentador do painel para uma escalada dentro da própria escola: quem cadastra
gente escolhe o cargo de quem cadastra, e sem trava a coordenadora criaria uma "diretora"
e entraria com ela.

Três buracos distintos, cada um com seu teste:

1. criar alguém **acima** de si;
2. **promover** um subordinado (ou a si mesmo) acima de si;
3. a secretaria mexer em contas — a exceção explícita do apontamento.
"""

from __future__ import annotations

import uuid

import pytest

from app.application.admin_use_cases import (
    AtualizarUsuario,
    CriarUsuario,
    DadosUsuario,
)
from app.domain.entities import Cargo, Papel, Turno, Usuario

TENANT = uuid.uuid4()
OUTRA_ESCOLA = uuid.uuid4()


class _FakeUsuarioRepo:
    def __init__(self, usuarios: list[Usuario] | None = None) -> None:
        self.usuarios = {u.id: u for u in (usuarios or [])}

    async def por_email(self, email):
        return next((u for u in self.usuarios.values() if u.email == email), None)

    async def criar(self, usuario):
        self.usuarios[usuario.id] = usuario
        return usuario

    async def obter(self, usuario_id):
        return self.usuarios.get(usuario_id)

    async def listar(self, *, tenant_id=None):
        return [
            u
            for u in self.usuarios.values()
            if tenant_id is None or u.tenant_id == tenant_id
        ]

    async def atualizar(self, usuario):
        self.usuarios[usuario.id] = usuario
        return usuario


def _usuario(cargo: Cargo | None, *, tenant_id=TENANT, nome="Fulano") -> Usuario:
    papel = Papel.SUPER_ADMIN if cargo is None else cargo.papel_correspondente
    return Usuario(
        nome=nome,
        email=f"{nome.lower().replace(' ', '')}@escola.test",
        senha_hash="x",
        papel=papel,
        tenant_id=None if cargo is None else tenant_id,
        cargo=cargo,
    )


# --------------------------------------------------------------------------- #
# A hierarquia, no domínio
# --------------------------------------------------------------------------- #
def test_ordem_dos_cargos():
    assert (
        Cargo.DIRETOR.nivel
        > Cargo.VICE_DIRETOR.nivel
        > Cargo.COORDENADOR.nivel
        > Cargo.SECRETARIA.nivel
    )


def test_papel_decorre_do_cargo():
    """Só a secretaria não administra — é a exceção do apontamento."""
    assert Cargo.SECRETARIA.papel_correspondente is Papel.SECRETARIA
    for cargo in (Cargo.DIRETOR, Cargo.VICE_DIRETOR, Cargo.COORDENADOR):
        assert cargo.papel_correspondente is Papel.TENANT_ADMIN


def test_manda_em_exige_estar_estritamente_acima():
    diretor = _usuario(Cargo.DIRETOR)
    outro_diretor = _usuario(Cargo.VICE_DIRETOR, nome="Vice")
    outro_diretor.cargo = Cargo.DIRETOR  # mesmo nível

    assert diretor.manda_em(_usuario(Cargo.COORDENADOR, nome="Coord"))
    # Mesmo nível não manda: diretor editando diretor é como uma conta é tomada.
    assert not diretor.manda_em(outro_diretor)
    assert not diretor.manda_em(diretor)


def test_ninguem_manda_em_quem_e_de_outra_escola():
    diretor = _usuario(Cargo.DIRETOR)
    de_fora = _usuario(Cargo.SECRETARIA, tenant_id=OUTRA_ESCOLA, nome="Alheia")
    assert not diretor.manda_em(de_fora)


def test_super_admin_manda_em_todos_e_ninguem_manda_nele():
    superadmin = _usuario(None)
    diretor = _usuario(Cargo.DIRETOR)
    assert superadmin.manda_em(diretor)
    assert not diretor.manda_em(superadmin)


def test_secretaria_nao_gerencia_usuarios():
    assert _usuario(Cargo.SECRETARIA).gere_usuarios is False
    for cargo in (Cargo.DIRETOR, Cargo.VICE_DIRETOR, Cargo.COORDENADOR):
        assert _usuario(cargo).gere_usuarios is True


# --------------------------------------------------------------------------- #
# Buraco 1: criar alguém acima de si
# --------------------------------------------------------------------------- #
async def _criar(criador, cargo, repo=None, **kwargs):
    repo = repo or _FakeUsuarioRepo([criador])
    return await CriarUsuario(usuarios=repo).executar(
        criador=criador,
        nome=kwargs.pop("nome", "Nova Pessoa"),
        email=kwargs.pop("email", "nova@escola.test"),
        senha="segredo",
        papel=Papel.TENANT_ADMIN,
        tenant_id=kwargs.pop("tenant_id", TENANT),
        cargo=cargo,
        **kwargs,
    )


async def test_coordenador_nao_cria_diretor():
    with pytest.raises(PermissionError, match="abaixo do seu"):
        await _criar(_usuario(Cargo.COORDENADOR), Cargo.DIRETOR)


async def test_coordenador_nao_cria_outro_coordenador():
    """Mesmo nível também não: dois coordenadores se editando é o mesmo buraco."""
    with pytest.raises(PermissionError):
        await _criar(_usuario(Cargo.COORDENADOR), Cargo.COORDENADOR)


async def test_coordenador_cria_secretaria():
    nova = await _criar(_usuario(Cargo.COORDENADOR), Cargo.SECRETARIA)
    assert nova.cargo is Cargo.SECRETARIA
    # E ela nasce SEM poder gerenciar usuários, mesmo tendo sido pedida como tenant_admin.
    assert nova.papel is Papel.SECRETARIA
    assert nova.gere_usuarios is False


async def test_diretor_cria_vice_e_coordenador():
    diretor = _usuario(Cargo.DIRETOR)
    repo = _FakeUsuarioRepo([diretor])
    vice = await _criar(diretor, Cargo.VICE_DIRETOR, repo=repo, email="v@escola.test")
    coord = await _criar(diretor, Cargo.COORDENADOR, repo=repo, email="c@escola.test")
    assert vice.papel is Papel.TENANT_ADMIN
    assert coord.papel is Papel.TENANT_ADMIN


async def test_secretaria_nao_cria_ninguem():
    with pytest.raises(PermissionError, match="secretaria"):
        await _criar(_usuario(Cargo.SECRETARIA), Cargo.SECRETARIA)


async def test_cargo_omitido_cria_admin_da_escola():
    """Retrocompatibilidade: era o que `papel=tenant_admin` sempre significou."""
    nova = await _criar(_usuario(None), None)
    assert nova.cargo is Cargo.DIRETOR
    assert nova.papel is Papel.TENANT_ADMIN


async def test_super_admin_nao_recebe_cargo():
    repo = _FakeUsuarioRepo()
    novo = await CriarUsuario(usuarios=repo).executar(
        criador=_usuario(None),
        nome="Outro Super",
        email="super2@plataforma.test",
        senha="segredo",
        papel=Papel.SUPER_ADMIN,
        tenant_id=None,
        cargo=Cargo.DIRETOR,  # ignorado: não ocupa posto em escola nenhuma
    )
    assert novo.cargo is None
    assert novo.tenant_id is None


async def test_contato_e_normalizado_no_cadastro():
    nova = await _criar(
        _usuario(Cargo.DIRETOR),
        Cargo.COORDENADOR,
        dados=DadosUsuario(
            telefone="(15) 99753-6978", endereco="  Rua A, 10  ", turno=Turno.TARDE
        ),
    )
    assert nova.telefone == "+5515997536978"
    assert nova.endereco == "Rua A, 10"
    assert nova.turno is Turno.TARDE


async def test_telefone_irreconhecivel_e_recusado():
    with pytest.raises(ValueError, match="Telefone"):
        await _criar(
            _usuario(Cargo.DIRETOR),
            Cargo.SECRETARIA,
            dados=DadosUsuario(telefone="123"),
        )


# --------------------------------------------------------------------------- #
# Buraco 2: promoção
# --------------------------------------------------------------------------- #
async def _editar(editor, alvo, **kwargs):
    repo = _FakeUsuarioRepo([editor, alvo])
    return await AtualizarUsuario(usuarios=repo).executar(
        editor=editor, usuario_id=alvo.id, **kwargs
    )


async def test_ninguem_promove_a_si_mesmo():
    coord = _usuario(Cargo.COORDENADOR)
    with pytest.raises(ValueError, match="próprio cargo"):
        await _editar(coord, coord, cargo=Cargo.DIRETOR)


async def test_ninguem_rebaixa_a_si_mesmo():
    """Rebaixar-se sozinho deixa a escola sem ninguém no topo."""
    diretor = _usuario(Cargo.DIRETOR)
    with pytest.raises(ValueError, match="próprio cargo"):
        await _editar(diretor, diretor, cargo=Cargo.SECRETARIA)


async def test_vice_nao_promove_subordinado_ao_proprio_nivel():
    """Senão o vice promove a coordenadora a vice e usa a conta dela."""
    vice = _usuario(Cargo.VICE_DIRETOR)
    coord = _usuario(Cargo.COORDENADOR, nome="Coord")
    with pytest.raises(PermissionError, match="abaixo do seu"):
        await _editar(vice, coord, cargo=Cargo.VICE_DIRETOR)


async def test_diretor_promove_coordenador_a_vice_e_o_papel_acompanha():
    diretor = _usuario(Cargo.DIRETOR)
    secretaria = _usuario(Cargo.SECRETARIA, nome="Sec")
    assert secretaria.papel is Papel.SECRETARIA

    promovida = await _editar(diretor, secretaria, cargo=Cargo.COORDENADOR)

    assert promovida.cargo is Cargo.COORDENADOR
    # Sem isto, a promovida continuaria sem acesso à gestão de usuários.
    assert promovida.papel is Papel.TENANT_ADMIN
    assert promovida.gere_usuarios is True


async def test_rebaixar_a_secretaria_tira_o_acesso():
    diretor = _usuario(Cargo.DIRETOR)
    coord = _usuario(Cargo.COORDENADOR, nome="Coord")

    rebaixada = await _editar(diretor, coord, cargo=Cargo.SECRETARIA)

    assert rebaixada.papel is Papel.SECRETARIA
    assert rebaixada.gere_usuarios is False


# --------------------------------------------------------------------------- #
# Buraco 3: quem pode editar quem
# --------------------------------------------------------------------------- #
async def test_coordenador_nao_edita_diretor():
    """Inclusive para trocar a senha — é assim que uma conta é tomada."""
    coord = _usuario(Cargo.COORDENADOR)
    diretor = _usuario(Cargo.DIRETOR, nome="Dir")
    with pytest.raises(PermissionError):
        await _editar(coord, diretor, senha="nova-senha")


async def test_secretaria_nao_edita_outra_pessoa():
    sec = _usuario(Cargo.SECRETARIA)
    outra = _usuario(Cargo.SECRETARIA, nome="Outra")
    with pytest.raises(PermissionError):
        await _editar(sec, outra, senha="nova-senha")


async def test_qualquer_um_edita_a_propria_conta():
    """Trocar a própria senha não pode depender de cargo — nem da secretaria."""
    sec = _usuario(Cargo.SECRETARIA)
    editada = await _editar(sec, sec, nome="Nome Novo", senha="outra-senha")
    assert editada.nome == "Nome Novo"


async def test_editar_nome_nao_apaga_o_contato():
    """Campo ausente = não mexer. Editar o nome não pode zerar o telefone."""
    diretor = _usuario(Cargo.DIRETOR)
    sec = _usuario(Cargo.SECRETARIA, nome="Sec")
    sec.telefone = "+5515997536978"
    sec.endereco = "Rua A, 10"

    editada = await _editar(diretor, sec, nome="Sec Maria")

    assert editada.nome == "Sec Maria"
    assert editada.telefone == "+5515997536978"
    assert editada.endereco == "Rua A, 10"


async def test_diretor_nao_edita_usuario_de_outra_escola():
    diretor = _usuario(Cargo.DIRETOR)
    de_fora = _usuario(Cargo.SECRETARIA, tenant_id=OUTRA_ESCOLA, nome="Alheia")
    with pytest.raises(PermissionError):
        await _editar(diretor, de_fora, nome="Invadida")


async def test_diretor_nao_edita_super_admin():
    diretor = _usuario(Cargo.DIRETOR)
    with pytest.raises(PermissionError):
        await _editar(diretor, _usuario(None), senha="nova")


async def test_desativar_a_propria_conta_e_recusado():
    diretor = _usuario(Cargo.DIRETOR)
    with pytest.raises(ValueError, match="própria conta"):
        await _editar(diretor, diretor, ativo=False)
