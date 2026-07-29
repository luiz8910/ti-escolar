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


async def _main() -> None:
    print(await criar_super_admin())


if __name__ == "__main__":
    asyncio.run(_main())
