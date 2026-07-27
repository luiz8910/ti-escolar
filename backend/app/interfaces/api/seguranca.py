"""Postura de segurança — auditoria interna do super admin (§14).

Rota **exclusiva do super admin**: expõe quais medidas protetivas a plataforma aplica e o
status real de cada uma no ambiente em execução. É material de auditoria interna (sócios),
não conteúdo para a escola — daí o guarda ``_exige_super_admin``.

A resposta **não devolve nenhum segredo**, só se um segredo é o valor de exemplo ou não.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.application.seguranca_use_cases import (
    JWT_SECRET_PADRAO,
    META_VERIFY_TOKEN_PADRAO,
    AvaliarPosturaSeguranca,
    ConfiguracaoSeguranca,
)
from app.config import Settings
from app.domain.entities import Usuario
from app.interfaces.api.admin import _exige_super_admin, usuario_autenticado
from app.interfaces.deps import get_settings_dep
from app.interfaces.dto import MedidaSegurancaSaida, PosturaSegurancaSaida

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _config_atual(settings: Settings) -> ConfiguracaoSeguranca:
    """Traduz as ``Settings`` em sinais booleanos — o caso de uso não vê env nem segredo."""
    return ConfiguracaoSeguranca(
        canal=settings.message_channel,
        meta_validate_signature=settings.meta_validate_signature,
        meta_app_secret_definido=bool(settings.meta_app_secret),
        meta_verify_token_padrao=(
            settings.meta_webhook_verify_token == META_VERIFY_TOKEN_PADRAO
        ),
        jwt_secret_padrao=(settings.jwt_secret == JWT_SECRET_PADRAO),
        jwt_expira_minutos=settings.jwt_expira_minutos,
        cors_liberado=("*" in settings.cors_origins),
        app_env=settings.app_env,
    )


@router.get("/seguranca", response_model=PosturaSegurancaSaida)
async def obter_postura_seguranca(
    solicitante: Usuario = Depends(usuario_autenticado),
    settings: Settings = Depends(get_settings_dep),
) -> PosturaSegurancaSaida:
    _exige_super_admin(solicitante)

    postura = AvaliarPosturaSeguranca().executar(config=_config_atual(settings))
    return PosturaSegurancaSaida(
        medidas=[
            MedidaSegurancaSaida(
                chave=m.chave,
                titulo=m.titulo,
                categoria=m.categoria,
                descricao=m.descricao,
                risco=m.risco,
                status=m.status.value,
                detalhe=m.detalhe,
                referencia=m.referencia,
            )
            for m in postura.medidas
        ],
        total_ativas=postura.total_ativas,
        total_atencao=postura.total_atencao,
        total_pendentes=postura.total_pendentes,
        pronto_para_producao=postura.pronto_para_producao,
        ambiente=settings.app_env,
        canal=settings.message_channel,
        gerado_em=datetime.now(timezone.utc),
    )
