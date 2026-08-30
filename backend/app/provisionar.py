"""Provisionamento de uma escola em ambiente **real** — o meio que faltava (§9e.3).

Havia dois extremos e nada entre eles:

- ``app.bootstrap`` cria **só o super admin**. Roda em todo deploy, inclusive produção.
- ``app.seed`` cria a **vitrine inteira** — escola fictícia, alunos, fichas, professor e
  logins com senha versionada no repositório. ``avaliar_seed`` o proíbe em produção, e a
  proibição está certa: dado fictício no banco de uma escola real é lixo que ninguém
  consegue distinguir do que é verdadeiro.

Faltava o meio: pôr **uma escola** de pé num banco real, com o mínimo para ela atender no
WhatsApp — o tenant, o admin dela, a conta (WABA) e, opcionalmente, uma base de
conhecimento. É o que este módulo faz, e é o caminho tanto para a escola de demonstração
da produção quanto para a primeira escola cliente.

**O que ele não é.** Não é o seed com uma bandeira nova. Não cria aluno, responsável,
turma, ficha nem professor: esses são dados de gente de verdade, e inventá-los numa base
de produção é o problema que ``avaliar_seed`` existe para evitar. E não aceita senha de
exemplo — ela é obrigatória, vem de fora e é recusada se for a do repositório.

Uso (na máquina que tem o ``DATABASE_URL``):

    fly ssh console --app ti-escolar -C "python -m app.provisionar \\
        --nome 'Escola Demonstração' --slug escola-demo \\
        --admin-email admin@tiescolar.com.br \\
        --numero +5515997536978 --phone-number-id 1231892910008454 \\
        --meta-waba-id 2116419572321695 --conhecimento demo"

A senha do admin vem de ``PROVISIONAR_ADMIN_SENHA`` no ambiente — nunca da linha de
comando, que fica no histórico do shell e no log do ``fly``.

**Idempotente.** Rodar de novo não duplica nada e **não sobrescreve senha** de quem já
existe: quem trocou a senha pelo painel não pode tê-la revertida por um provisionamento
repetido. O que ele completa são os campos vazios.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from uuid import UUID, uuid4

from sqlalchemy import select

from app.application.use_cases import IndexarConhecimento
from app.bootstrap import CAMPOS_SENHA_DEMO, valor_default
from app.config import Settings, get_settings
from app.domain.entities import Papel, TipoConhecimento, Usuario
from app.infrastructure.db.models import ConhecimentoORM, TenantORM, WabaORM
from app.infrastructure.db.pgvector_store import PgVectorStore
from app.infrastructure.db.repositories_admin import SqlUsuarioRepository
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.factories import criar_embedder
from app.infrastructure.security import hash_senha

# Base de conhecimento genérica de escola, para a **demonstração**. É o insumo do RAG:
# sem nenhuma fonte indexada o assistente responde sem citar nada, e o teste do WhatsApp
# provaria o transporte sem provar o atendimento.
#
# Fica aqui, e não importada de ``app.seed``, de propósito: o seed é material de vitrine e
# muda por motivos de vitrine (alunos novos, fichas novas). Um provisionamento de produção
# que herdasse esse arquivo herdaria também as mudanças dele.
CONHECIMENTO_DEMO: tuple[tuple[TipoConhecimento, str, str], ...] = (
    (
        TipoConhecimento.PROCEDIMENTO,
        "Horário de funcionamento",
        "A secretaria atende de segunda a sexta-feira, das 7h30 às 17h. As aulas do "
        "período da manhã começam às 7h30 e as do período da tarde às 13h.",
    ),
    (
        TipoConhecimento.PROCEDIMENTO,
        "Como justificar faltas",
        "Para justificar a falta do aluno, o responsável deve enviar atestado ou "
        "justificativa à secretaria em até 48 horas, presencialmente ou por este canal.",
    ),
    (
        TipoConhecimento.PROCEDIMENTO,
        "Segunda via de boletim e declarações",
        "Boletins, declarações de matrícula e históricos podem ser solicitados por aqui. "
        "Basta pedir o documento desejado que enviaremos o arquivo em PDF.",
    ),
    (
        TipoConhecimento.PROCEDIMENTO,
        "Saída antecipada",
        "Para buscar o aluno antes do fim do período, o responsável deve comparecer à "
        "secretaria e assinar o registro de saída antecipada.",
    ),
    (
        TipoConhecimento.PROCEDIMENTO,
        "Autorização de retirada por terceiros",
        "A autorização para que outra pessoa retire o aluno deve ser registrada por "
        "escrito na secretaria, com documento de identificação do autorizado.",
    ),
    (
        TipoConhecimento.FAQ,
        "Uniforme escolar",
        "O uso do uniforme é obrigatório. Em dias de educação física, usar o uniforme "
        "esportivo. O kit pode ser adquirido na loja parceira indicada na secretaria.",
    ),
    (
        TipoConhecimento.FAQ,
        "Transporte escolar",
        "O transporte escolar é solicitado na secretaria mediante comprovante de "
        "endereço e conforme os critérios da rede municipal.",
    ),
    (
        TipoConhecimento.AVISO,
        "Canal oficial de comunicação",
        "Este WhatsApp é o canal oficial da escola com os responsáveis. Assuntos de "
        "secretaria devem ser tratados por aqui; o grupo da turma é apenas para avisos.",
    ),
)

# Senha que o ambiente precisa fornecer. Vazia ou igual à do repositório é recusada — o
# provisionamento cria um login que **abre o painel de uma escola** num banco real.
_ENV_SENHA = "PROVISIONAR_ADMIN_SENHA"


class ProvisionamentoRecusado(RuntimeError):
    """Pré-condição não satisfeita. Falha fechada, com a causa por extenso."""


@dataclass
class ResultadoProvisionamento:
    """O que mudou — para o log do deploy contar, não para alguém adivinhar."""

    escola_criada: bool = False
    admin_criado: bool = False
    conta_vinculada: bool = False
    conhecimento_indexado: int = 0
    tenant_id: UUID | None = None
    notas: list[str] = field(default_factory=list)

    def resumo(self) -> str:
        partes = [
            f"escola {'criada' if self.escola_criada else 'já existia'}",
            f"admin {'criado' if self.admin_criado else 'já existia'}",
            f"conta {'vinculada' if self.conta_vinculada else 'já vinculada'}",
            f"{self.conhecimento_indexado} fonte(s) de conhecimento indexada(s)",
        ]
        cabeca = f"provisionamento ({self.tenant_id}): " + ", ".join(partes)
        return "\n".join([cabeca, *(f"  - {n}" for n in self.notas)])


def normalizar_slug(bruto: str) -> str:
    """Slug em minúsculas, sem acento e sem separador repetido.

    É a chave que o painel usa na URL e o prefixo dos templates da escola
    (``rosacury_festa_junina``); um espaço ou acento aqui vira nome inválido na Meta.
    """
    texto = (bruto or "").strip().lower()
    trocas = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüçñ", "aaaaaeeeeiiiiooooouuuucn")
    texto = texto.translate(trocas)
    texto = re.sub(r"[^a-z0-9]+", "-", texto).strip("-")
    return texto


def normalizar_e164(bruto: str) -> str:
    digitos = "".join(c for c in (bruto or "") if c.isdigit())
    return f"+{digitos}" if digitos else ""


def so_digitos(bruto: str) -> str:
    return "".join(c for c in (bruto or "") if c.isdigit())


def senha_do_ambiente(settings: Settings) -> str:
    """A senha do admin da escola, exigida de fora e recusada se for a do repositório.

    A alternativa — cair num default — é exatamente o que ``avaliar_seed`` proíbe: um
    login conhecido, versionado, abrindo o painel de uma escola num banco real.
    """
    senha = (os.environ.get(_ENV_SENHA) or "").strip()
    if not senha:
        raise ProvisionamentoRecusado(
            f"Defina {_ENV_SENHA} no ambiente: o provisionamento cria um login que abre "
            "o painel da escola, e senha de exemplo em banco real é o que este módulo "
            "existe para evitar."
        )
    # A senha de exemplo é conferida **antes** do comprimento, e não depois: as do repo
    # são curtas ("escola123"), então a ordem inversa devolveria "senha curta" para o
    # caso em que a causa real — e a correção — são outras.
    #
    # Compara com os valores **de fábrica**, não com os do ambiente: é o que está
    # versionado que não pode virar senha de produção, e olhar `settings` daria falso
    # positivo justamente no ambiente que já definiu a sua.
    if senha in {valor_default(campo) for campo in CAMPOS_SENHA_DEMO}:
        raise ProvisionamentoRecusado(
            f"{_ENV_SENHA} está com uma senha de exemplo do repositório. Troque-a."
        )
    if len(senha) < 12:
        raise ProvisionamentoRecusado(
            f"{_ENV_SENHA} tem menos de 12 caracteres. O painel dá acesso a dado de "
            "menor (§17): use uma senha do gerenciador de senhas."
        )
    return senha


async def provisionar(
    *,
    nome: str,
    slug: str = "",
    admin_email: str,
    admin_nome: str = "",
    numero_e164: str = "",
    phone_number_id: str = "",
    meta_waba_id: str = "",
    meta_business_id: str = "",
    telefone_contato: str = "",
    conhecimento: tuple[tuple[TipoConhecimento, str, str], ...] = (),
    settings: Settings | None = None,
) -> ResultadoProvisionamento:
    """Cria (ou completa) uma escola pronta para atender no WhatsApp.

    Cada passo é condicional ao que já existe: é o que permite rodar de novo depois de
    corrigir um campo, sem medo de duplicar escola ou reverter senha.
    """
    settings = settings or get_settings()
    resultado = ResultadoProvisionamento()

    nome = (nome or "").strip()
    if not nome:
        raise ProvisionamentoRecusado("A escola precisa de um nome.")
    slug = normalizar_slug(slug or nome)
    admin_email = (admin_email or "").strip().lower()
    if not admin_email:
        raise ProvisionamentoRecusado("Informe o e-mail do admin da escola.")
    senha = senha_do_ambiente(settings)
    numero_e164 = normalizar_e164(numero_e164)
    phone_number_id = so_digitos(phone_number_id)
    meta_waba_id = so_digitos(meta_waba_id)

    async with SessionLocal() as session:
        # --- Conta (WABA) ----------------------------------------------------------- #
        # A migration 0042 já criou "WABA principal" sem id. Reaproveitá-la, em vez de
        # criar outra, evita o ambiente com duas contas e o catálogo apontando para a errada.
        conta = (
            await session.execute(select(WabaORM).order_by(WabaORM.criado_em).limit(1))
        ).scalar_one_or_none()
        if conta is None:
            conta = WabaORM(
                id=uuid4(),
                meta_waba_id=meta_waba_id,
                nome="TI-Escolar" if meta_waba_id else "WABA principal",
                meta_business_id=meta_business_id,
                ativo=True,
                criado_em=datetime.now(timezone.utc),
            )
            session.add(conta)
            await session.flush()
            resultado.notas.append(f"conta do WhatsApp criada ({conta.nome})")
        elif meta_waba_id and not conta.meta_waba_id:
            conta.meta_waba_id = meta_waba_id
            if meta_business_id:
                conta.meta_business_id = meta_business_id
            resultado.notas.append(
                f"id da Meta preenchido na conta {conta.nome!r}: {meta_waba_id}"
            )
        elif meta_waba_id and conta.meta_waba_id != meta_waba_id:
            # Não sobrescreve: trocar o id de uma conta em uso redireciona o catálogo de
            # todas as escolas dela. Quem quiser mudar usa a tela, que pede confirmação.
            resultado.notas.append(
                f"ATENÇÃO: a conta {conta.nome!r} já tem o id {conta.meta_waba_id}, "
                f"diferente do informado ({meta_waba_id}). Nada foi alterado."
            )

        # --- Escola ------------------------------------------------------------------ #
        escola = (
            await session.execute(select(TenantORM).where(TenantORM.slug == slug))
        ).scalar_one_or_none()
        if escola is None:
            escola = TenantORM(
                id=uuid4(),
                nome=nome,
                slug=slug,
                criado_em=datetime.now(timezone.utc),
                telefone_contato=normalizar_e164(telefone_contato),
                whatsapp_numero=numero_e164,
                meta_phone_number_id=phone_number_id,
                waba_id=conta.id,
                # Expediente da secretaria (§6j): governa se o assistente encaminha o
                # atendimento agora ou promete o próximo dia útil. Sem valor explícito o
                # produto assumiria 24h, e prometeria secretaria às 23h.
                expediente_dias="1,2,3,4,5",
                expediente_inicio=time(7, 30),
                expediente_fim=time(17, 0),
                expediente_timezone="America/Sao_Paulo",
            )
            session.add(escola)
            await session.flush()
            resultado.escola_criada = True
        else:
            # Completar campos vazios, nunca sobrescrever o que já foi ajustado no painel.
            if numero_e164 and not escola.whatsapp_numero:
                escola.whatsapp_numero = numero_e164
            if phone_number_id and not escola.meta_phone_number_id:
                escola.meta_phone_number_id = phone_number_id
            elif phone_number_id and escola.meta_phone_number_id != phone_number_id:
                resultado.notas.append(
                    f"ATENÇÃO: a escola já tem o phone_number_id "
                    f"{escola.meta_phone_number_id}, diferente do informado "
                    f"({phone_number_id}). Nada foi alterado — trocar o número é decisão "
                    "de tela, não de script."
                )
        if escola.waba_id is None:
            escola.waba_id = conta.id
            resultado.conta_vinculada = True
        resultado.tenant_id = escola.id

        # --- Admin da escola --------------------------------------------------------- #
        usuarios = SqlUsuarioRepository(session)
        if await usuarios.por_email(admin_email) is None:
            await usuarios.criar(
                Usuario(
                    nome=(admin_nome or "Secretaria").strip(),
                    email=admin_email,
                    senha_hash=hash_senha(senha),
                    papel=Papel.TENANT_ADMIN,
                    tenant_id=escola.id,
                )
            )
            resultado.admin_criado = True
        else:
            # Não mexe na senha: quem a trocou pelo painel não pode tê-la revertida por
            # um provisionamento repetido — a mesma regra do ``bootstrap``.
            resultado.notas.append(
                f"o usuário {admin_email} já existe; senha e papel preservados."
            )

        # --- Base de conhecimento (RAG) ---------------------------------------------- #
        if conhecimento:
            ja_tem = (
                await session.execute(
                    select(ConhecimentoORM)
                    .where(ConhecimentoORM.tenant_id == escola.id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if ja_tem is None:
                indexar = IndexarConhecimento(
                    embedder=criar_embedder(settings), store=PgVectorStore(session)
                )
                for tipo, titulo, conteudo in conhecimento:
                    await indexar.executar(
                        tenant_id=escola.id, tipo=tipo, titulo=titulo, conteudo=conteudo
                    )
                resultado.conhecimento_indexado = len(conhecimento)
                if settings.embeddings_provider not in ("openai", "openai_compatible"):
                    # Com o embedder fake a busca vetorial "funciona" e recupera lixo: os
                    # vetores são determinísticos mas sem semântica. Dizer isso agora
                    # evita concluir, num teste real, que o RAG está quebrado.
                    resultado.notas.append(
                        "ATENÇÃO: EMBEDDINGS_PROVIDER está em 'fake' — o conteúdo foi "
                        "indexado com vetores sem semântica e a busca não vai recuperar "
                        "o trecho certo. Configure o provedor e reindexe pelo painel."
                    )
            else:
                resultado.notas.append(
                    "a escola já tem conhecimento indexado; nada foi acrescentado."
                )

        await session.commit()
    return resultado


def _argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.provisionar",
        description=(
            "Cria uma escola pronta para atender no WhatsApp num banco real. "
            f"A senha do admin vem de {_ENV_SENHA} no ambiente."
        ),
    )
    parser.add_argument("--nome", required=True, help="Nome da escola (visível no painel)")
    parser.add_argument("--slug", default="", help="Slug; derivado do nome se omitido")
    parser.add_argument("--admin-email", required=True, help="E-mail do admin da escola")
    parser.add_argument("--admin-nome", default="Secretaria")
    parser.add_argument(
        "--numero", default="", help="Número da escola em E.164 (ex.: +5515997536978)"
    )
    parser.add_argument(
        "--phone-number-id",
        default="",
        help="phone_number_id do número na Meta — sem ele a escola NÃO recebe mensagem",
    )
    parser.add_argument("--meta-waba-id", default="", help="Id da conta (WABA) na Meta")
    parser.add_argument("--meta-business-id", default="", help="Id do portfólio na Meta")
    parser.add_argument("--telefone-contato", default="", help="Telefone público da escola")
    parser.add_argument(
        "--conhecimento",
        choices=("nenhum", "demo"),
        default="nenhum",
        help=(
            "'demo' indexa uma base genérica de escola, para o assistente ter o que citar "
            "num teste. Para escola real, deixe 'nenhum' e cadastre o conteúdo dela."
        ),
    )
    return parser.parse_args(argv)


async def _main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    try:
        resultado = await provisionar(
            nome=args.nome,
            slug=args.slug,
            admin_email=args.admin_email,
            admin_nome=args.admin_nome,
            numero_e164=args.numero,
            phone_number_id=args.phone_number_id,
            meta_waba_id=args.meta_waba_id,
            meta_business_id=args.meta_business_id,
            telefone_contato=args.telefone_contato,
            conhecimento=(
                CONHECIMENTO_DEMO if args.conhecimento == "demo" else ()
            ),
        )
    except ProvisionamentoRecusado as erro:
        # Código 2, e não 0: ao contrário do seed (opcional, não pode derrubar o boot),
        # este comando é pedido explicitamente por alguém — falhar calado esconderia que
        # a escola não foi criada.
        print(f"Provisionamento RECUSADO — {erro}", file=sys.stderr)
        return 2
    print(resultado.resumo())
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
