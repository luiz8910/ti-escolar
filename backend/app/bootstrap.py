"""Provisionamento mínimo de um ambiente: política do seed e criação do super admin.

Separado de ``app.seed`` de propósito. O seed é **material de demonstração** (escola
fictícia, alunos, fichas, senhas de exemplo) e **nunca deve tocar o banco de produção**;
o bootstrap é o único provisionamento que roda em todo deploy, e cria só o que um
ambiente vazio precisa para ter um primeiro acesso: o super admin.

Antes disso o ``CMD`` do container rodava ``python -m app.seed`` incondicionalmente, o
que despejava a escola-demo (com senhas conhecidas, versionadas no repositório) dentro
do banco real a cada deploy.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.config import Settings, get_settings
from app.domain.entities import Papel, Usuario
from app.infrastructure.db.repositories_admin import SqlUsuarioRepository
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.security import hash_senha

# Campos de senha que o seed usa e que têm valor de exemplo no ``Settings``.
CAMPOS_SENHA_DEMO = (
    "super_admin_senha",
    "demo_admin_senha",
    "demo_professor_senha",
)


def valor_default(campo: str) -> str | None:
    """Valor de fábrica de um campo do ``Settings`` (o que está no código)."""
    field = Settings.model_fields.get(campo)
    if field is None:
        return None
    default = field.default
    return default if isinstance(default, str) else None


def segredos_com_valor_default(settings: Settings, campos: tuple[str, ...]) -> list[str]:
    """Quais dos ``campos`` continuam com o valor de exemplo do repositório."""
    iguais: list[str] = []
    for campo in campos:
        default = valor_default(campo)
        if default is not None and getattr(settings, campo, None) == default:
            iguais.append(campo)
    return iguais


@dataclass(frozen=True)
class DecisaoSeed:
    """Resultado da política do seed: se pode semear e por quê."""

    permitido: bool
    motivo: str


def avaliar_seed(settings: Settings) -> DecisaoSeed:
    """Decide se o seed de demonstração pode rodar neste ambiente.

    Regras, em ordem (a primeira que bater decide):

    1. **Produção nunca semeia**, nem com ``SEED_DEMO=true``. Dados fictícios no banco de
       uma escola real são lixo que ninguém consegue distinguir do que é verdadeiro.
    2. Fora de produção, só semeia com ``SEED_DEMO=true`` — o default é **não** semear,
       para que um ambiente novo (staging apontado por engano para outro banco) falhe
       fechado.
    3. Homologação com **senha de exemplo** não semeia: o seed cria logins que abrem o
       painel, e as senhas default estão versionadas no repositório. Em ``development``
       isso é aceito, porque o banco é o container local descartável.
    """
    if settings.ambiente_producao:
        return DecisaoSeed(
            False,
            "APP_ENV=production — o seed de demonstração não roda em produção. "
            "Use `python -m app.bootstrap` para criar o super admin.",
        )
    if not settings.seed_demo:
        return DecisaoSeed(
            False,
            "SEED_DEMO não está habilitado (default: desligado). "
            "Defina SEED_DEMO=true no ambiente de homologação/desenvolvimento.",
        )
    if not settings.ambiente_desenvolvimento:
        pendentes = segredos_com_valor_default(settings, CAMPOS_SENHA_DEMO)
        if pendentes:
            return DecisaoSeed(
                False,
                "senhas de exemplo ainda em uso (" + ", ".join(sorted(pendentes)) + "). "
                "Defina valores próprios antes de semear fora de desenvolvimento.",
            )
    return DecisaoSeed(True, f"ambiente {settings.app_env} com SEED_DEMO habilitado")


async def criar_super_admin(settings: Settings | None = None) -> str:
    """Cria o super admin a partir das variáveis de ambiente, se ainda não existir.

    Idempotente e **não destrutivo**: se o e-mail já existe, não mexe na senha — quem
    trocou a senha pelo painel não pode tê-la revertida pelo próximo deploy.

    Devolve uma frase descrevendo o que aconteceu (para o log do deploy).
    """
    settings = settings or get_settings()
    email = (settings.super_admin_email or "").strip()
    senha = settings.super_admin_senha or ""

    if not email or not senha:
        return "bootstrap: SUPER_ADMIN_EMAIL/SENHA não definidos — nada a fazer."

    if settings.ambiente_producao and segredos_com_valor_default(
        settings, ("super_admin_senha",)
    ):
        # Falhar fechado: criar em produção um super admin cross-tenant com a senha que
        # está no .env.example seria entregar a plataforma inteira a quem leu o repo.
        return (
            "bootstrap: RECUSADO — SUPER_ADMIN_SENHA está com o valor de exemplo do "
            "repositório e o ambiente é produção. Defina uma senha forte e faça o deploy "
            "de novo."
        )

    async with SessionLocal() as session:
        usuarios = SqlUsuarioRepository(session)
        if await usuarios.por_email(email) is not None:
            return f"bootstrap: super admin {email} já existe — nada a fazer."
        await usuarios.criar(
            Usuario(
                nome=settings.super_admin_nome,
                email=email,
                senha_hash=hash_senha(senha),
                papel=Papel.SUPER_ADMIN,
                tenant_id=None,
            )
        )
        await session.commit()
    return f"bootstrap: super admin {email} criado."


class ConfiguracaoInsegura(RuntimeError):
    """Produção pedida com segredo de exemplo ou proteção desligada."""


# O que produção **não** aceita, e o porquê de cada um em uma linha. A mensagem é lida por
# quem está com o deploy vermelho às 22h; dizer só "configuração inválida" custaria a ele a
# meia hora que este dicionário economiza.
_EXIGENCIAS_PRODUCAO = {
    "jwt_secret": (
        "JWT_SECRET está com o valor de exemplo do repositório. Quem leu o repo forja um "
        "token de super admin e entra em todas as escolas. Gere um segredo forte."
    ),
    "meta_webhook_verify_token": (
        "META_WEBHOOK_VERIFY_TOKEN está com o valor de exemplo ('changeme'). Com ele, "
        "qualquer um reassina o webhook da Meta para um endpoint próprio."
    ),
}


def exigencias_de_producao(settings: Settings) -> list[str]:
    """O que impede este ambiente de ser produção. Lista vazia = pode subir.

    Devolve **todas** as pendências, não a primeira: quem está configurando um ambiente
    novo prefere corrigir três coisas de uma vez a descobrir uma por deploy.

    Só vale sob ``APP_ENV=production``. Em desenvolvimento os defaults são o que faz o
    projeto subir com um ``git clone``, e recusá-los ali seria atrapalhar sem proteger
    nada — o banco é um container descartável.
    """
    if not settings.ambiente_producao:
        return []

    pendencias = [
        _EXIGENCIAS_PRODUCAO[campo]
        for campo in segredos_com_valor_default(settings, tuple(_EXIGENCIAS_PRODUCAO))
    ]
    if not settings.meta_validate_signature:
        # Não é segredo default, é proteção desligada — mas o efeito é o mesmo: endpoint
        # público aceitando qualquer POST, com status de entrega e conversas forjáveis.
        pendencias.append(
            "META_VALIDATE_SIGNATURE está desligado. O webhook aceita qualquer POST, e "
            "dá para forjar status de entrega e mensagens recebidas. Ligue-o (=true) e "
            "confira que META_APP_SECRET está preenchido."
        )
    return pendencias


def exigir_producao_segura(settings: Settings | None = None) -> None:
    """Falha **fechado** no boot quando produção está mal configurada.

    Recusar-se a subir é agressivo de propósito. As três pendências acima têm em comum
    não darem sintoma nenhum: o processo sobe, o painel abre, as mensagens saem — e a
    plataforma fica aberta. Um erro que só aparece quando alguém o explora precisa
    aparecer antes, e o único momento garantido é o deploy.
    """
    settings = settings or get_settings()
    pendencias = exigencias_de_producao(settings)
    if pendencias:
        raise ConfiguracaoInsegura(
            "APP_ENV=production com configuração insegura — a aplicação não vai subir:\n"
            + "\n".join(f"  - {p}" for p in pendencias)
        )


async def _main() -> None:
    exigir_producao_segura()
    print(await criar_super_admin())


if __name__ == "__main__":
    asyncio.run(_main())
