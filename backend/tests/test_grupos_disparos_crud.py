"""Editar e excluir grupos; renomear e cancelar disparos (§6a, §13).

O painel só criava: grupo com nome errado ficava errado para sempre, contato adicionado
por engano recebia o próximo aviso, e um disparo errado não tinha como ser parado.

Disparo **não se exclui**: o que já saiu é o registro de que a escola avisou. O que existe
é cancelar — e cancelar tem de interromper de verdade: o envio em curso para no
destinatário seguinte, e a retomada não volta ao que ficou.
"""

from __future__ import annotations

import uuid

import pytest

from app.application.admin_use_cases import (
    AdicionarContatoAoGrupo,
    AtualizarGrupo,
    CriarGrupo,
    GrupoNaoEncontrado,
    RemoverContatoDoGrupo,
    RemoverGrupo,
)
from app.application.retomada_use_cases import RetomarBroadcastsPendentes
from app.application.tenant_use_cases import (
    CancelarBroadcastDaEscola,
    DisparoJaEncerrado,
    DisparoNaoEncontrado,
    RenomearBroadcastDaEscola,
)
from app.application.use_cases import EnviarBroadcast
from app.domain.entities import (
    Broadcast,
    CategoriaTemplate,
    DestinatarioBroadcast,
    MessageTemplate,
    StatusBroadcast,
    StatusEntrega,
    StatusTemplate,
    TemplateNaWaba,
)
from tests.fakes import (
    WABA_PADRAO_ID,
    FakeBroadcastRepo,
    FakeChannel,
    FakeGrupoRepo,
    FakeQuota,
    FakeRateLimiter,
    FakeTemplateRepo,
)

TENANT = uuid.uuid4()
OUTRA_ESCOLA = uuid.uuid4()


# --------------------------------------------------------------------------- #
# Grupos
# --------------------------------------------------------------------------- #
async def _grupo(grupos, nome="Turma 5º A", tenant_id=TENANT):
    return await CriarGrupo(grupos=grupos).executar(tenant_id=tenant_id, nome=nome)


async def test_grupo_e_renomeado_e_mantem_os_contatos():
    grupos = FakeGrupoRepo()
    grupo = await _grupo(grupos)
    await AdicionarContatoAoGrupo(grupos=grupos).executar(
        tenant_id=TENANT, grupo_id=grupo.id, nome="Maria", telefone="+5511900000001"
    )

    atualizado = await AtualizarGrupo(grupos=grupos).executar(
        tenant_id=TENANT, grupo_id=grupo.id, nome="  Turma 5º B ", descricao=" tarde "
    )

    assert atualizado.nome == "Turma 5º B"
    assert atualizado.descricao == "tarde"
    assert [c.nome for c in atualizado.membros] == ["Maria"]


async def test_nome_de_grupo_repetido_na_escola_e_recusado():
    grupos = FakeGrupoRepo()
    await _grupo(grupos, "Turma 5º A")
    outro = await _grupo(grupos, "Pais do Fundamental I")

    with pytest.raises(ValueError, match="Já existe um grupo"):
        await AtualizarGrupo(grupos=grupos).executar(
            tenant_id=TENANT, grupo_id=outro.id, nome="turma 5º a"
        )
    with pytest.raises(ValueError, match="Já existe um grupo"):
        await _grupo(grupos, "TURMA 5º A")


async def test_grupo_pode_manter_o_proprio_nome_e_repetir_o_de_outra_escola():
    grupos = FakeGrupoRepo()
    grupo = await _grupo(grupos, "Turma 5º A")
    # Mesmo nome noutra escola não é conflito: a unicidade é por tenant.
    await _grupo(grupos, "Turma 5º A", tenant_id=OUTRA_ESCOLA)

    atualizado = await AtualizarGrupo(grupos=grupos).executar(
        tenant_id=TENANT, grupo_id=grupo.id, nome="Turma 5º A", descricao="manhã"
    )

    assert atualizado.descricao == "manhã"


async def test_grupo_sem_nome_e_recusado():
    grupos = FakeGrupoRepo()
    grupo = await _grupo(grupos)

    with pytest.raises(ValueError, match="Informe o nome"):
        await AtualizarGrupo(grupos=grupos).executar(
            tenant_id=TENANT, grupo_id=grupo.id, nome="   "
        )
    with pytest.raises(ValueError, match="Informe o nome"):
        await _grupo(grupos, "")


async def test_grupo_de_outra_escola_nao_e_alterado_nem_excluido():
    grupos = FakeGrupoRepo()
    alheio = await _grupo(grupos, "Turma 5º A", tenant_id=OUTRA_ESCOLA)

    with pytest.raises(GrupoNaoEncontrado):
        await AtualizarGrupo(grupos=grupos).executar(
            tenant_id=TENANT, grupo_id=alheio.id, nome="Invadido"
        )
    with pytest.raises(GrupoNaoEncontrado):
        await RemoverGrupo(grupos=grupos).executar(tenant_id=TENANT, grupo_id=alheio.id)

    intacto = await grupos.obter(tenant_id=OUTRA_ESCOLA, grupo_id=alheio.id)
    assert intacto is not None and intacto.nome == "Turma 5º A"


async def test_excluir_grupo_devolve_o_que_saiu_para_a_auditoria():
    grupos = FakeGrupoRepo()
    grupo = await _grupo(grupos)
    await AdicionarContatoAoGrupo(grupos=grupos).executar(
        tenant_id=TENANT, grupo_id=grupo.id, nome="Maria", telefone="+5511900000001"
    )

    removido = await RemoverGrupo(grupos=grupos).executar(tenant_id=TENANT, grupo_id=grupo.id)

    assert removido.nome == "Turma 5º A" and len(removido.membros) == 1
    assert await grupos.listar(tenant_id=TENANT) == []
    with pytest.raises(GrupoNaoEncontrado):
        await RemoverGrupo(grupos=grupos).executar(tenant_id=TENANT, grupo_id=grupo.id)


async def test_contato_sai_do_grupo_sem_levar_os_outros():
    grupos = FakeGrupoRepo()
    grupo = await _grupo(grupos)
    add = AdicionarContatoAoGrupo(grupos=grupos)
    maria = await add.executar(
        tenant_id=TENANT, grupo_id=grupo.id, nome="Maria", telefone="+5511900000001"
    )
    await add.executar(
        tenant_id=TENANT, grupo_id=grupo.id, nome="João", telefone="+5511900000002"
    )

    await RemoverContatoDoGrupo(grupos=grupos).executar(
        tenant_id=TENANT, grupo_id=grupo.id, contato_id=maria.id
    )

    restantes = await grupos.membros(tenant_id=TENANT, grupo_id=grupo.id)
    assert [c.nome for c in restantes] == ["João"]
    # Remover de novo, ou pelo tenant errado, não é sucesso silencioso.
    with pytest.raises(GrupoNaoEncontrado):
        await RemoverContatoDoGrupo(grupos=grupos).executar(
            tenant_id=TENANT, grupo_id=grupo.id, contato_id=maria.id
        )
    with pytest.raises(GrupoNaoEncontrado):
        await RemoverContatoDoGrupo(grupos=grupos).executar(
            tenant_id=OUTRA_ESCOLA, grupo_id=grupo.id, contato_id=restantes[0].id
        )


# --------------------------------------------------------------------------- #
# Disparos
# --------------------------------------------------------------------------- #
async def _disparo(
    broadcasts, *, status=StatusBroadcast.CONCLUIDO, tenant_id=TENANT, titulo="Reunião"
) -> Broadcast:
    broadcast = Broadcast(
        tenant_id=tenant_id,
        template_id=uuid.uuid4(),
        titulo=titulo,
        status=status,
        destinatarios=[
            DestinatarioBroadcast(contato="+5511900000001", status=StatusEntrega.ENTREGUE),
            DestinatarioBroadcast(contato="+5511900000002", status=StatusEntrega.FALHOU),
        ],
    )
    await broadcasts.salvar(broadcast)
    return broadcast


async def test_titulo_do_disparo_e_corrigido_sem_tocar_nos_destinatarios():
    broadcasts = FakeBroadcastRepo()
    disparo = await _disparo(broadcasts, titulo="Reuniao")

    titulo = await RenomearBroadcastDaEscola(broadcasts=broadcasts).executar(
        tenant_id=TENANT, broadcast_id=disparo.id, titulo="  Reunião de pais  "
    )

    salvo = await broadcasts.obter(disparo.id)
    assert titulo == salvo.titulo == "Reunião de pais"
    assert [d.status for d in salvo.destinatarios] == [
        StatusEntrega.ENTREGUE,
        StatusEntrega.FALHOU,
    ]


async def test_titulo_vazio_ou_longo_demais_e_recusado():
    broadcasts = FakeBroadcastRepo()
    disparo = await _disparo(broadcasts)
    renomear = RenomearBroadcastDaEscola(broadcasts=broadcasts)

    with pytest.raises(ValueError, match="Informe o título"):
        await renomear.executar(tenant_id=TENANT, broadcast_id=disparo.id, titulo="  ")
    # A coluna é String(300): estourar só falharia no banco, como erro interno.
    with pytest.raises(ValueError, match="300"):
        await renomear.executar(tenant_id=TENANT, broadcast_id=disparo.id, titulo="x" * 301)
    assert (await broadcasts.obter(disparo.id)).titulo == "Reunião"


async def test_disparo_de_outra_escola_nao_e_renomeado_nem_cancelado():
    broadcasts = FakeBroadcastRepo()
    alheio = await _disparo(
        broadcasts, tenant_id=OUTRA_ESCOLA, status=StatusBroadcast.PARCIAL_LIMITE
    )

    with pytest.raises(DisparoNaoEncontrado):
        await RenomearBroadcastDaEscola(broadcasts=broadcasts).executar(
            tenant_id=TENANT, broadcast_id=alheio.id, titulo="Invadido"
        )
    with pytest.raises(DisparoNaoEncontrado):
        await CancelarBroadcastDaEscola(broadcasts=broadcasts).executar(
            tenant_id=TENANT, broadcast_id=alheio.id
        )

    assert (await broadcasts.obter(alheio.id)).titulo == "Reunião"
    assert alheio.id not in broadcasts.cancelados


# --------------------------------------------------------------------------- #
# Cancelar: o disparo tem de parar
# --------------------------------------------------------------------------- #
def _template() -> MessageTemplate:
    return MessageTemplate(
        tenant_id=TENANT,
        nome="aviso",
        categoria=CategoriaTemplate.UTILITY,
        idioma="pt_BR",
        corpo="Olá, {{1}}!",
        wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.APROVADO)],
    )


def _pendente(n: int) -> list[DestinatarioBroadcast]:
    return [
        DestinatarioBroadcast(contato=f"+55119000000{i:02d}", parametros=["Maria"])
        for i in range(1, n + 1)
    ]


def _enviar(broadcasts, canal, template, *, limite: int = 1000) -> EnviarBroadcast:
    return EnviarBroadcast(
        broadcasts=broadcasts,
        templates=FakeTemplateRepo(template),
        canal=canal,
        quota=FakeQuota(limite_diario=limite),
        rate_limiter=FakeRateLimiter(),
    )


class _CanalQueCancelaNoMeio(FakeChannel):
    """Depois de N envios, alguém cancela o disparo por outra tela."""

    def __init__(self, broadcasts: FakeBroadcastRepo, *, apos: int) -> None:
        super().__init__()
        self._broadcasts = broadcasts
        self._apos = apos
        self.alvo = None

    async def enviar_template(self, **kwargs) -> str:
        mensagem_id = await super().enviar_template(**kwargs)
        if len(self.enviados) == self._apos:
            self._broadcasts.cancelados.add(self.alvo)
        return mensagem_id


@pytest.mark.parametrize(
    "status",
    [StatusBroadcast.EM_ENVIO, StatusBroadcast.PARCIAL_LIMITE, StatusBroadcast.AGENDADO],
)
async def test_disparo_com_envio_pendente_e_cancelado(status):
    broadcasts = FakeBroadcastRepo()
    disparo = Broadcast(
        tenant_id=TENANT,
        template_id=uuid.uuid4(),
        titulo="Reunião",
        status=status,
        destinatarios=[
            DestinatarioBroadcast(contato="+5511900000001", status=StatusEntrega.ENTREGUE),
            *_pendente(3),
        ],
    )
    await broadcasts.salvar(disparo)

    antes, aguardavam = await CancelarBroadcastDaEscola(broadcasts=broadcasts).executar(
        tenant_id=TENANT, broadcast_id=disparo.id
    )

    assert antes.titulo == "Reunião"
    # Só os três que ainda não tinham recebido; o entregue continua entregue.
    assert aguardavam == 3
    assert await broadcasts.status_atual(disparo.id) is StatusBroadcast.CANCELADO


@pytest.mark.parametrize(
    "status", [StatusBroadcast.CONCLUIDO, StatusBroadcast.CANCELADO, StatusBroadcast.RASCUNHO]
)
async def test_disparo_que_ja_terminou_nao_tem_o_que_cancelar(status):
    broadcasts = FakeBroadcastRepo()
    disparo = await _disparo(broadcasts, status=status)

    with pytest.raises(DisparoJaEncerrado):
        await CancelarBroadcastDaEscola(broadcasts=broadcasts).executar(
            tenant_id=TENANT, broadcast_id=disparo.id
        )


async def test_disparo_novo_e_gravado_antes_de_enviar_para_poder_ser_cancelado():
    """Antes o disparo só existia no banco **depois** do lote: durante o envio não
    aparecia no histórico, e não havia o que cancelar."""
    broadcasts = FakeBroadcastRepo()
    template = _template()

    class _CanalEspiao(FakeChannel):
        gravado_no_primeiro_envio = None
        confirmado_no_primeiro_envio = None

        async def enviar_template(self, **kwargs) -> str:
            if self.gravado_no_primeiro_envio is None:
                self.gravado_no_primeiro_envio = disparo.id in broadcasts.salvos
                self.confirmado_no_primeiro_envio = broadcasts.confirmacoes >= 1
            return await super().enviar_template(**kwargs)

    canal = _CanalEspiao()
    disparo = Broadcast(
        tenant_id=TENANT, template_id=template.id, titulo="Reunião", destinatarios=_pendente(2)
    )

    await _enviar(broadcasts, canal, template).executar(broadcast=disparo)

    assert canal.gravado_no_primeiro_envio and canal.confirmado_no_primeiro_envio


async def test_cancelar_no_meio_do_envio_interrompe_no_destinatario_seguinte():
    broadcasts = FakeBroadcastRepo()
    template = _template()
    canal = _CanalQueCancelaNoMeio(broadcasts, apos=2)
    disparo = Broadcast(
        tenant_id=TENANT, template_id=template.id, titulo="Reunião", destinatarios=_pendente(5)
    )
    canal.alvo = disparo.id

    resultado = await _enviar(broadcasts, canal, template).executar(broadcast=disparo)

    # Dois saíram antes do cancelamento; o terceiro em diante, não.
    assert len(canal.enviados) == 2
    assert resultado.enviados == 2
    assert resultado.status is StatusBroadcast.CANCELADO
    salvo = await broadcasts.obter(disparo.id)
    assert salvo.status is StatusBroadcast.CANCELADO
    assert [d.status for d in salvo.destinatarios] == [
        StatusEntrega.ENVIADO,
        StatusEntrega.ENVIADO,
        StatusEntrega.CANCELADO,
        StatusEntrega.CANCELADO,
        StatusEntrega.CANCELADO,
    ]


async def test_cancelamento_que_chega_no_ultimo_envio_nao_e_apagado_ao_gravar():
    """`salvar` regrava status e destinatários. Sem a conferência final, o cancelamento
    feito durante o último envio seria sobrescrito por `CONCLUIDO`/`PARCIAL_LIMITE` — e,
    no segundo caso, a retomada mandaria o resto no dia seguinte."""
    broadcasts = FakeBroadcastRepo()
    template = _template()
    # Cota para 2 de 4: sem cancelamento, terminaria `PARCIAL_LIMITE` com 2 pendentes.
    canal = _CanalQueCancelaNoMeio(broadcasts, apos=2)
    disparo = Broadcast(
        tenant_id=TENANT, template_id=template.id, titulo="Reunião", destinatarios=_pendente(4)
    )
    canal.alvo = disparo.id

    resultado = await _enviar(broadcasts, canal, template, limite=2).executar(broadcast=disparo)

    assert resultado.status is StatusBroadcast.CANCELADO
    assert [d.status for d in disparo.destinatarios].count(StatusEntrega.CANCELADO) == 2


async def test_retomada_nao_envia_disparo_cancelado_depois_de_listado():
    """A retomada lista os pendentes e só depois os percorre: o disparo cancelado nesse
    intervalo chega ao envio ainda como `PARCIAL_LIMITE`, na cópia em memória."""
    template = _template()
    canal = FakeChannel()
    disparo = Broadcast(
        tenant_id=TENANT,
        template_id=template.id,
        titulo="Reunião",
        status=StatusBroadcast.PARCIAL_LIMITE,
        destinatarios=_pendente(3),
    )

    class _Repo(FakeBroadcastRepo):
        async def listar_retomaveis(self, *, desde):
            # O cancelamento entra logo depois de a lista ser lida.
            self.cancelados.add(disparo.id)
            return [disparo]

    broadcasts = _Repo()
    await broadcasts.salvar(disparo)

    await RetomarBroadcastsPendentes(
        broadcasts=broadcasts, enviar=_enviar(broadcasts, canal, template)
    ).executar()

    assert canal.enviados == []


async def test_destinatario_cancelado_nao_recebe_em_reenvio():
    """Mesmo que o disparo voltasse à fila, quem foi cancelado não é pendente."""
    broadcasts = FakeBroadcastRepo()
    template = _template()
    canal = FakeChannel()
    disparo = Broadcast(
        tenant_id=TENANT,
        template_id=template.id,
        titulo="Reunião",
        status=StatusBroadcast.PARCIAL_LIMITE,
        destinatarios=[
            DestinatarioBroadcast(
                contato="+5511900000001", parametros=["Maria"], status=StatusEntrega.CANCELADO
            ),
            *_pendente(1),
        ],
    )
    await broadcasts.salvar(disparo)

    await _enviar(broadcasts, canal, template).executar(broadcast=disparo)

    # `_pendente(1)` reaproveita o mesmo número de propósito: o que decide o envio é o
    # status de cada destinatário, não o telefone.
    assert len(canal.enviados) == 1
    assert disparo.destinatarios[1].status is StatusEntrega.ENVIADO
    assert disparo.destinatarios[0].status is StatusEntrega.CANCELADO
