"""A limpeza de dado pessoal antes de o evento sair para o Sentry.

O Sentry é operador nos Estados Unidos, e um evento de erro carrega — sem pedir licença — o
corpo da requisição, cabeçalhos e as variáveis locais do traceback. Numa base que guarda
laudo, CPF e telefone de responsável, isso é transferência internacional de dado sensível de
menor. Estes testes existem porque o `before_send` é a **única** coisa entre a exceção e a
rede: se ele falhar em silêncio, ninguém percebe até o incidente.
"""

from __future__ import annotations

from app.config import Settings
from app.infrastructure.observabilidade import before_send, iniciar_sentry


def test_remove_valor_de_chave_sensivel():
    evento = {
        "extra": {
            "senha": "hunter2",
            "telefone_responsavel": "+5515997536978",
            "laudo_cid": "F84.0",
            "rota": "/api/admin/documentos",  # não é sensível: precisa sobreviver
        }
    }
    limpo = before_send(evento, None)
    assert limpo["extra"]["senha"] == "[redigido]"
    assert limpo["extra"]["telefone_responsavel"] == "[redigido]"
    assert limpo["extra"]["laudo_cid"] == "[redigido]"
    assert limpo["extra"]["rota"] == "/api/admin/documentos"


def test_mascara_telefone_e_cpf_dentro_da_MENSAGEM():
    """A limpeza por chave não alcança o que está embutido em texto livre — e mensagem de
    erro costuma citar o dado que causou o problema."""
    evento = {
        "message": "Falha ao enviar para +5515997536978 (CPF 123.456.789-09)",
        "logentry": {"message": "número 5511900000001 inválido"},
    }
    limpo = before_send(evento, None)
    assert "5515997536978" not in limpo["message"]
    assert "123.456.789-09" not in limpo["message"]
    assert "5511900000001" not in limpo["logentry"]["message"]


def test_limpa_estruturas_aninhadas():
    """Stack frames do Sentry aninham variáveis locais vários níveis abaixo."""
    evento = {"exception": {"values": [{"stacktrace": {"frames": [
        {"vars": {"contato": "+5511999998888", "titulo": "Reunião de pais"}}
    ]}}]}}
    frame = before_send(evento, None)["exception"]["values"][0]["stacktrace"]["frames"][0]
    assert frame["vars"]["contato"] == "[redigido]"
    assert frame["vars"]["titulo"] == "Reunião de pais"


def test_falha_na_limpeza_descarta_o_evento():
    """Falha FECHADO: perder um alerta é incômodo, vazar laudo de criança é incidente.

    Deixar passar "só desta vez" seria escolher o pior dos dois.
    """
    class _Explode(dict):
        def items(self):
            raise RuntimeError("estrutura inesperada")

    assert before_send(_Explode(a=1), None) is None


def test_estrutura_muito_profunda_nao_trava():
    """Recursão sem freio no `before_send` — que roda no caminho do erro — viraria um
    segundo problema em cima do primeiro."""
    evento = atual = {}
    for _ in range(60):
        atual["nivel"] = {}
        atual = atual["nivel"]
    atual["senha"] = "x"
    assert before_send(evento, None) is not None  # devolve algo, sem estourar a pilha


def test_sem_dsn_nao_liga_e_nao_e_erro():
    """Estado de desenvolvimento e de quem não quer o subprocessador. O produto funciona
    igual — só não avisa ninguém."""
    assert iniciar_sentry(Settings(sentry_dsn="")) is False


# --------------------------------------------------------------------------- #
# O item 8 do checklist de pré-deploy (§15) fecha com o alerta
# --------------------------------------------------------------------------- #
def _item8(**over):
    from app.application.seguranca_use_cases import (
        AvaliarPosturaSeguranca,
        ConfiguracaoSeguranca,
    )

    base = dict(
        canal="meta",
        meta_access_token_definido=True,
        meta_validate_signature=True,
        meta_app_secret_definido=True,
        meta_verify_token_padrao=False,
        jwt_secret_padrao=False,
        jwt_expira_minutos=480,
        cors_liberado=False,
        app_env="production",
        logs_persistidos=True,
        logs_retencao_dias=14,
    )
    base.update(over)
    postura = AvaliarPosturaSeguranca().executar(config=ConfiguracaoSeguranca(**base))
    return next(i for i in postura.checklist if i.numero == 8)


def test_item_8_fica_em_atencao_sem_alerta():
    """Era o último ⚠️ do checklist, e o motivo é honesto: log persistido sem notificação
    significa que a escola descobre o erro antes de nós."""
    from app.domain.entities import StatusMedida

    item = _item8(alerta_ativo=False)
    assert item.status is StatusMedida.ATENCAO
    assert "SENTRY_DSN" in item.situacao


def test_item_8_fecha_com_o_alerta_ligado():
    from app.domain.entities import StatusMedida

    item = _item8(alerta_ativo=True)
    assert item.status is StatusMedida.ATIVA


def test_alerta_sem_log_persistido_ainda_e_atencao():
    """Alerta sem log é meio caminho: chega a notificação e não há onde investigar."""
    from app.domain.entities import StatusMedida

    assert _item8(alerta_ativo=True, logs_persistidos=False).status is StatusMedida.ATENCAO
