"""Seed de demonstração: escola, conhecimento (RAG indexado) e template aprovado.

Idempotente: usa um tenant fixo (DEMO_TENANT_ID) e não duplica se já existir.
Executado pelo docker-compose após as migrations.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.application.admin_use_cases import CriarGrupo
from app.application.cadastro_use_cases import (
    AtribuirProfessorASala,
    AtualizarProfessor,
    CadastrarAluno,
    CadastrarPai,
    CadastrarProfessor,
    CriarSala,
)
from app.application.mural_use_cases import PublicarRecado
from app.application.respostas_rapidas_use_cases import CriarRespostaRapida
from app.application.use_cases import IndexarConhecimento
from app.config import get_settings
from app.domain.entities import Papel, TipoConhecimento, Usuario
from app.infrastructure.db.models import TemplateORM, TenantORM
from app.infrastructure.db.pgvector_store import PgVectorStore
from app.infrastructure.db.repositories_admin import (
    SqlAlunoRepository,
    SqlContatoRepository,
    SqlGrupoRepository,
    SqlProfessorRepository,
    SqlSalaRepository,
    SqlUsuarioRepository,
)
from app.infrastructure.db.repositories_comunicacao import SqlMuralRepository
from app.infrastructure.db.repositories_conhecimento import (
    SqlFonteConhecimentoRepository,
    SqlPromptTenantRepository,
    SqlRespostaRapidaRepository,
)
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.factories import criar_embedder
from app.infrastructure.security import hash_senha

# Tenant fixo para o demo (o front-end usa este id).
DEMO_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEMO_TEMPLATE_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a1")

# Grupos de demonstração e seus contatos (nome, telefone E.164).
_GRUPOS_DEMO = {
    "Turma 5º A": [
        ("Maria Souza", "+5511999990001"),
        ("João Pereira", "+5511999990002"),
        ("Ana Lima", "+5511999990003"),
    ],
    "Pais do Fundamental I": [
        ("Carlos Mendes", "+5511999990004"),
        ("Patrícia Rocha", "+5511999990005"),
    ],
}

# Salas (turmas) de demonstração e seus pais/responsáveis (nome, telefone E.164).
_SALAS_DEMO = {
    "4ª série B": [
        ("Beatriz Almeida", "+5511988880001"),
        ("Rafael Nogueira", "+5511988880002"),
    ],
    "5ª série A": [
        ("Cláudia Fonseca", "+5511988880003"),
        ("Eduardo Tavares", "+5511988880004"),
    ],
}

# System prompt personalizado do tenant demo (o "CLAUDE.md" da escola).
_PROMPT_DEMO = (
    "Esta é a Escola Demonstração. Trate os responsáveis pelo primeiro nome quando souber. "
    "Reforce sempre o uso obrigatório do uniforme e o e-mail da secretaria "
    "(secretaria@escola.test) para assuntos formais. Em caso de emergência, oriente a ligar "
    "para a portaria. Nunca compartilhe notas ou dados de um aluno com quem não seja o "
    "responsável cadastrado."
)

# Respostas rápidas ("atalhos") reais da EM Rosa Cury (chave, conteúdo).
# São a base de conhecimento pronta da secretaria: ingeridas no RAG para o bot responder.
_RESPOSTAS_RAPIDAS = [
    ("SEDU", "O acesso ao portal SEDU (Secretaria de Educação) é feito pelo site oficial com o login do responsável. Em caso de dúvida no acesso, procure a secretaria."),
    ("Horário do portão", "O portão abre às 7h e fecha às 7h30 no período da manhã. Após o horário, a entrada é somente pela secretaria."),
    ("Horário da secretaria", "A secretaria atende de segunda a sexta-feira, das 7h30 às 17h."),
    ("Buscar mais cedo", "Para buscar o aluno mais cedo, o responsável deve comparecer à secretaria e assinar o registro de saída antecipada."),
    ("Pix APM", "As contribuições da APM podem ser feitas por Pix. Solicite a chave atualizada na secretaria e envie o comprovante."),
    ("Eventual (lista complementar)", "A lista complementar de professores eventuais é organizada pela secretaria. Interessados devem deixar nome e contato atualizados."),
    ("Histórico escolar", "O histórico escolar pode ser solicitado na secretaria; o prazo de emissão é informado no ato do pedido."),
    ("Transferência (SED)", "A transferência é registrada no sistema SED. Traga um documento do aluno e o comprovante da nova escola para dar entrada."),
    ("Endereço da escola", "A EM Rosa Cury fica no endereço informado no site da prefeitura. Em caso de dúvida, confirme com a secretaria."),
    ("Transporte escolar gratuito", "O transporte escolar gratuito é solicitado na secretaria mediante comprovante de endereço e conforme os critérios da rede municipal."),
    ("Inscrição rede municipal", "As inscrições na rede municipal seguem o calendário da Secretaria de Educação. Consulte prazos e documentos na secretaria."),
    ("Conselho Tutelar", "Casos que envolvem o Conselho Tutelar são encaminhados pela direção. Em emergências, procure diretamente o órgão."),
    ("Atestado", "O atestado médico deve ser entregue à secretaria em até 48 horas para justificar a ausência do aluno."),
    ("Faltas", "Para justificar faltas, envie atestado ou justificativa à secretaria em até 48 horas, presencialmente ou pelo WhatsApp."),
    ("Autorizar retirada", "A autorização de retirada por terceiros deve ser registrada por escrito na secretaria, com documento do autorizado."),
    ("Autorizar van", "A autorização para transporte por van é feita na secretaria, identificando o condutor responsável."),
    ("Troca de período", "A troca de período depende de vaga na turma desejada. Faça a solicitação na secretaria."),
    ("Declaração de escolaridade", "A declaração de escolaridade é emitida pela secretaria e enviada em PDF quando solicitada pelo WhatsApp."),
    ("Boas-vindas / grupo da turma", "Seja bem-vindo(a)! O grupo oficial da turma é usado apenas para avisos da escola. Assuntos de secretaria devem ser tratados por este canal."),
]

_CONHECIMENTO = [
    (
        TipoConhecimento.PROCEDIMENTO,
        "Horário de funcionamento",
        "A secretaria atende de segunda a sexta-feira, das 7h30 às 17h. "
        "As aulas do período da manhã começam às 7h30 e as do período da tarde às 13h.",
    ),
    (
        TipoConhecimento.PROCEDIMENTO,
        "Como justificar faltas",
        "Para justificar a falta do aluno, o responsável deve enviar atestado ou justificativa "
        "à secretaria em até 48 horas, presencialmente ou pelo e-mail secretaria@escola.test.",
    ),
    (
        TipoConhecimento.PROCEDIMENTO,
        "Segunda via de boletim e declarações",
        "Boletins, declarações de matrícula e históricos podem ser solicitados pelo WhatsApp. "
        "Basta pedir o documento desejado que enviaremos o arquivo em PDF.",
    ),
    (
        TipoConhecimento.AVISO,
        "Reunião de pais e mestres",
        "A próxima reunião de pais e mestres será no dia 20 de junho, às 19h, no auditório. "
        "A presença dos responsáveis é muito importante.",
    ),
    (
        TipoConhecimento.AVISO,
        "Calendário de provas",
        "As provas do segundo bimestre ocorrerão entre 1º e 5 de julho. "
        "O calendário detalhado por turma está disponível na secretaria.",
    ),
    (
        TipoConhecimento.FAQ,
        "Uniforme escolar",
        "O uso do uniforme é obrigatório. O kit pode ser adquirido na loja parceira indicada "
        "na secretaria. Em dias de educação física, usar o uniforme esportivo.",
    ),
]


async def _seed() -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        # Tenant
        tenant = await session.get(TenantORM, DEMO_TENANT_ID)
        if tenant is None:
            session.add(
                TenantORM(
                    id=DEMO_TENANT_ID,
                    nome="Escola Demonstração",
                    slug="escola-demo",
                    criado_em=datetime.now(timezone.utc),
                    # Telefone de contato público da escola (informativo).
                    telefone_contato="+5511999990000",
                    # Preços da ficha financeira (centavos): R$ 299/mês, R$ 2.990/ano.
                    valor_mensal_centavos=29900,
                    valor_anual_centavos=299000,
                )
            )
            await session.flush()

        # Conhecimento (RAG) — só indexa se ainda não houver
        store = PgVectorStore(session)
        indexar = IndexarConhecimento(embedder=criar_embedder(settings), store=store)
        from app.infrastructure.db.models import ConhecimentoORM

        existe = (
            await session.execute(
                select(ConhecimentoORM).where(ConhecimentoORM.tenant_id == DEMO_TENANT_ID).limit(1)
            )
        ).scalar_one_or_none()
        if existe is None:
            for tipo, titulo, conteudo in _CONHECIMENTO:
                await indexar.executar(
                    tenant_id=DEMO_TENANT_ID, tipo=tipo, titulo=titulo, conteudo=conteudo
                )

        # Template aprovado para broadcasts
        template = await session.get(TemplateORM, DEMO_TEMPLATE_ID)
        if template is None:
            session.add(
                TemplateORM(
                    id=DEMO_TEMPLATE_ID,
                    tenant_id=DEMO_TENANT_ID,
                    nome="aviso_reuniao",
                    categoria="utility",
                    idioma="pt_BR",
                    corpo="Olá, {{1}}! Lembrete: {{2}}. Atenciosamente, Escola Demonstração.",
                    status="aprovado",
                )
            )

        # Usuários administrativos (super admin + admin do tenant demo)
        usuarios = SqlUsuarioRepository(session)
        if await usuarios.por_email(settings.super_admin_email) is None:
            await usuarios.criar(
                Usuario(
                    nome=settings.super_admin_nome,
                    email=settings.super_admin_email,
                    senha_hash=hash_senha(settings.super_admin_senha),
                    papel=Papel.SUPER_ADMIN,
                    tenant_id=None,
                )
            )
        if await usuarios.por_email(settings.demo_admin_email) is None:
            await usuarios.criar(
                Usuario(
                    nome="Admin Escola Demonstração",
                    email=settings.demo_admin_email,
                    senha_hash=hash_senha(settings.demo_admin_senha),
                    papel=Papel.TENANT_ADMIN,
                    tenant_id=DEMO_TENANT_ID,
                )
            )

        # Grupos de contatos (pais) — só cria se ainda não houver grupos no tenant
        grupos_repo = SqlGrupoRepository(session)
        if not await grupos_repo.listar(tenant_id=DEMO_TENANT_ID):
            criar_grupo = CriarGrupo(grupos=grupos_repo)
            for nome_grupo, contatos in _GRUPOS_DEMO.items():
                grupo = await criar_grupo.executar(tenant_id=DEMO_TENANT_ID, nome=nome_grupo)
                for nome, telefone in contatos:
                    await grupos_repo.adicionar_contato(
                        tenant_id=DEMO_TENANT_ID,
                        grupo_id=grupo.id,
                        nome=nome,
                        telefone=telefone,
                    )

        # Salas (turmas) com pais/responsáveis vinculados — só cria se ainda não houver
        salas_repo = SqlSalaRepository(session)
        contatos_repo = SqlContatoRepository(session)
        if not await salas_repo.listar(tenant_id=DEMO_TENANT_ID):
            criar_sala = CriarSala(salas=salas_repo)
            cadastrar_pai = CadastrarPai(contatos=contatos_repo, salas=salas_repo)
            for nome_sala, responsaveis in _SALAS_DEMO.items():
                sala = await criar_sala.executar(tenant_id=DEMO_TENANT_ID, nome=nome_sala)
                for nome, telefone in responsaveis:
                    existente = await contatos_repo.por_telefone(
                        tenant_id=DEMO_TENANT_ID, telefone=telefone
                    )
                    if existente is None:
                        await cadastrar_pai.executar(
                            tenant_id=DEMO_TENANT_ID,
                            nome=nome,
                            telefone=telefone,
                            sala_ids=[sala.id],
                        )
                    else:
                        await salas_repo.vincular_pai(
                            tenant_id=DEMO_TENANT_ID,
                            sala_id=sala.id,
                            contato_id=existente.id,
                        )

        # Alunos de demonstração — vinculados às salas e responsáveis já criados.
        alunos_repo = SqlAlunoRepository(session)
        if not await alunos_repo.listar(tenant_id=DEMO_TENANT_ID):
            cadastrar_aluno = CadastrarAluno(alunos=alunos_repo, salas=salas_repo)
            salas_demo = await salas_repo.listar(tenant_id=DEMO_TENANT_ID)
            for i, sala in enumerate(salas_demo, start=1):
                responsaveis = await salas_repo.pais(tenant_id=DEMO_TENANT_ID, sala_id=sala.id)
                await cadastrar_aluno.executar(
                    tenant_id=DEMO_TENANT_ID,
                    nome=f"Aluno Demonstração {i}",
                    sala_id=sala.id,
                    matricula=f"2026-{i:03d}",
                    responsavel_ids=[c.id for c in responsaveis[:1]],
                )
            # Um aluno propositalmente sem responsável com telefone, para demonstrar o
            # alerta de cobertura de contatos da turma e a notificação ao professor.
            if salas_demo:
                await cadastrar_aluno.executar(
                    tenant_id=DEMO_TENANT_ID,
                    nome="Aluno Sem Contato",
                    sala_id=salas_demo[0].id,
                    matricula="2026-099",
                )

        # Professores de demonstração — um por série, reusando o mesmo professor em
        # ambas para ilustrar "um professor conduz várias séries".
        professores_repo = SqlProfessorRepository(session)
        if not await professores_repo.listar(tenant_id=DEMO_TENANT_ID):
            cadastrar_professor = CadastrarProfessor(professores=professores_repo)
            atribuir = AtribuirProfessorASala(salas=salas_repo)
            prof = await cadastrar_professor.executar(
                tenant_id=DEMO_TENANT_ID,
                nome="Prof. Carla Mendes",
                telefone="+5511977770001",
                # Senha para o login do professor no mural (§A1) — trocar em produção.
                senha=settings.demo_professor_senha,
            )
            for sala in await salas_repo.listar(tenant_id=DEMO_TENANT_ID):
                await atribuir.executar(
                    tenant_id=DEMO_TENANT_ID, sala_id=sala.id, professor_id=prof.id
                )

        # Garante que o professor demo tenha senha para o login do mural, mesmo em bases
        # já semeadas antes desta feature (idempotente: só define se estiver vazia).
        prof_demo = await professores_repo.por_telefone(
            tenant_id=DEMO_TENANT_ID, telefone="+5511977770001"
        )
        if prof_demo is not None and not prof_demo.senha_hash:
            await AtualizarProfessor(professores=professores_repo).executar(
                tenant_id=DEMO_TENANT_ID,
                professor_id=prof_demo.id,
                nome=prof_demo.nome,
                telefone=prof_demo.telefone,
                senha=settings.demo_professor_senha,
            )

        # Mural do professor — um recado de demonstração da secretaria.
        mural_repo = SqlMuralRepository(session)
        if not await mural_repo.listar(tenant_id=DEMO_TENANT_ID):
            await PublicarRecado(mural=mural_repo).executar(
                tenant_id=DEMO_TENANT_ID,
                titulo="Reunião pedagógica na sexta-feira",
                corpo=(
                    "Prezados professores, teremos reunião pedagógica nesta sexta-feira, "
                    "às 17h, na sala dos professores. Confirmem a leitura deste recado."
                ),
                autor_nome="Secretaria",
            )

        # Respostas rápidas ("atalhos") da Rosa Cury — só cria se ainda não houver.
        respostas_repo = SqlRespostaRapidaRepository(session)
        if not await respostas_repo.listar(tenant_id=DEMO_TENANT_ID):
            criar_resposta = CriarRespostaRapida(
                respostas=respostas_repo,
                embedder=criar_embedder(settings),
                store=store,
                fontes=SqlFonteConhecimentoRepository(session),
            )
            for chave, conteudo in _RESPOSTAS_RAPIDAS:
                await criar_resposta.executar(
                    tenant_id=DEMO_TENANT_ID, chave=chave, conteudo=conteudo
                )

        # System prompt do tenant demo — só define se ainda não houver um
        prompts_repo = SqlPromptTenantRepository(session)
        if await prompts_repo.obter(tenant_id=DEMO_TENANT_ID) is None:
            await prompts_repo.salvar(tenant_id=DEMO_TENANT_ID, conteudo=_PROMPT_DEMO)

        await session.commit()
    print("Seed concluído (tenant demo:", DEMO_TENANT_ID, ")")
    print("  super admin:", settings.super_admin_email)
    print("  admin tenant demo:", settings.demo_admin_email)


if __name__ == "__main__":
    asyncio.run(_seed())
