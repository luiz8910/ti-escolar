"""DTOs de entrada/saída da API (Pydantic)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MensagemEntrada(BaseModel):
    tenant_id: UUID
    contato: str = Field(..., examples=["+5511999998888"])
    texto: str


class DocumentoSaida(BaseModel):
    nome: str
    categoria: str
    url: str


class MensagemSaida(BaseModel):
    texto: str
    fontes: list[str] = []
    documentos: list[DocumentoSaida] = []


class DestinatarioEntrada(BaseModel):
    contato: str
    parametros: list[str] = []


class BroadcastEntrada(BaseModel):
    tenant_id: UUID
    template_id: UUID
    titulo: str
    destinatarios: list[DestinatarioEntrada]


class BroadcastSaida(BaseModel):
    broadcast_id: UUID
    status: str
    enviados: int
    falhas: int
    bloqueados_por_limite: int
    restante_cota: int


class QuotaSaida(BaseModel):
    tenant_id: UUID
    dia: str
    limite_diario: int
    enviados: int
    restante: int


# --------------------------------------------------------------------------- #
# Administração e grupos
# --------------------------------------------------------------------------- #
class LoginEntrada(BaseModel):
    email: str
    senha: str


class UsuarioSaida(BaseModel):
    id: UUID
    nome: str
    email: str
    papel: str
    tenant_id: UUID | None = None


class TokenSaida(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_em: int  # validade do token em segundos
    usuario: UsuarioSaida


class CriarUsuarioEntrada(BaseModel):
    nome: str
    email: str
    senha: str
    papel: str = Field(..., examples=["tenant_admin", "super_admin"])
    tenant_id: UUID | None = None


class GrupoEntrada(BaseModel):
    tenant_id: UUID
    nome: str
    descricao: str = ""


class ContatoSaida(BaseModel):
    id: UUID
    nome: str
    telefone: str


class GrupoSaida(BaseModel):
    id: UUID
    nome: str
    descricao: str
    total_membros: int
    membros: list[ContatoSaida] = []


class ContatoEntrada(BaseModel):
    tenant_id: UUID
    nome: str
    telefone: str = Field(..., examples=["+5511999990000"])


class EnvioGrupoEntrada(BaseModel):
    tenant_id: UUID
    template_id: UUID
    titulo: str
    mensagem: str


class EnvioGrupoSaida(BaseModel):
    grupo_id: UUID
    total_contatos: int
    broadcast: BroadcastSaida


# --------------------------------------------------------------------------- #
# Escolas (tenants) — CRUD do super admin
# --------------------------------------------------------------------------- #
class EscolaEntrada(BaseModel):
    nome: str
    # Opcional: se vazio, é derivado do nome.
    slug: str = ""
    # Número de WhatsApp da escola (E.164) operado pela plataforma. Vazio = usa o número
    # padrão do canal.
    whatsapp_numero: str = ""
    # Telefone de contato público (E.164) da escola — **obrigatório**, apenas informativo.
    telefone_contato: str = ""


class LicencaSaida(BaseModel):
    """Estado de licenciamento/cobrança/bloqueio de uma escola."""

    status: str  # "ativo" | "bloqueado" | "cancelado"
    motivo_bloqueio: str = ""
    bloqueado_em: datetime | None = None
    plano: str  # "mensal" | "anual"
    licenca_expira_em: datetime | None = None
    dias_para_expirar: int | None = None
    licenca_expirada: bool = False
    # Cobrança e cancelamento (churn).
    valor_mensal_centavos: int = 0
    valor_anual_centavos: int = 0
    cancelado_em: datetime | None = None
    motivo_cancelamento: str = ""


class EscolaSaida(BaseModel):
    id: UUID
    nome: str
    slug: str
    whatsapp_numero: str = ""
    telefone_contato: str = ""
    criado_em: datetime
    licenca: LicencaSaida


class EscolaResumoSaida(BaseModel):
    id: UUID
    nome: str
    slug: str
    whatsapp_numero: str = ""
    telefone_contato: str = ""
    criado_em: datetime
    total_conversas: int
    total_contatos: int
    total_broadcasts: int
    licenca: LicencaSaida


class BloqueioEntrada(BaseModel):
    motivo: str = Field(..., examples=["Inadimplência: mensalidade de junho/2026 em aberto."])


class CancelamentoEntrada(BaseModel):
    motivo: str = Field(..., examples=["Escola encerrou o contrato em junho/2026."])


class LicencaEntrada(BaseModel):
    plano: str = Field("mensal", examples=["mensal", "anual"])
    licenca_expira_em: datetime | None = None
    # Preços por ciclo (centavos). None preserva o valor já cadastrado.
    valor_mensal_centavos: int | None = None
    valor_anual_centavos: int | None = None


class AvisoLicencaSaida(BaseModel):
    tenant_id: UUID
    nome: str
    dias_para_expirar: int
    destinatarios: list[str] = []


class MetricasUsoSaida(BaseModel):
    total_usuarios_ativos: int = 0
    total_contatos: int = 0
    total_alunos: int = 0
    total_conversas: int = 0
    total_broadcasts: int = 0


class FichaFinanceiraSaida(BaseModel):
    """Ficha financeira/histórico de uma escola (super admin)."""

    tenant_id: UUID
    nome: str
    slug: str
    # Ciclo de vida.
    criado_em: datetime  # data de início (quando entrou)
    dias_de_casa: int
    cancelado_em: datetime | None = None
    motivo_cancelamento: str = ""
    # Licenciamento/cobrança.
    status: str
    plano: str
    licenca_expira_em: datetime | None = None  # próxima renovação
    dias_para_expirar: int | None = None
    status_pagamento: str
    valor_mensal_centavos: int
    valor_anual_centavos: int
    mrr_centavos: int
    arr_centavos: int
    receita_acumulada_centavos: int  # LTV estimado
    meses_ativos: int
    # Uso e saúde.
    uso: MetricasUsoSaida
    limite_diario_meta: int
    health_score: int


# --------------------------------------------------------------------------- #
# Visualização de conversas (inbound) e broadcasts (outbound) da escola
# --------------------------------------------------------------------------- #
class ConversaResumoSaida(BaseModel):
    id: UUID
    contato: str
    criado_em: datetime
    total_mensagens: int
    ultima_mensagem: str
    ultima_em: datetime | None = None


class MensagemConversaSaida(BaseModel):
    id: UUID
    autor: str  # "usuario" | "bot"
    texto: str
    fontes: list[str] = []
    criado_em: datetime


class ConversaDetalheSaida(BaseModel):
    id: UUID
    contato: str
    criado_em: datetime
    mensagens: list[MensagemConversaSaida] = []


class BroadcastResumoSaida(BaseModel):
    id: UUID
    titulo: str
    status: str
    template_nome: str = ""
    criado_em: datetime
    agendado_para: datetime | None = None
    total_destinatarios: int
    por_status: dict[str, int] = {}


class DestinatarioBroadcastSaida(BaseModel):
    contato: str
    nome: str = ""  # nome do responsável, se cadastrado
    status: str
    atualizado_em: datetime | None = None


class BroadcastDetalheSaida(BaseModel):
    id: UUID
    titulo: str
    status: str
    template_nome: str = ""
    criado_em: datetime
    agendado_para: datetime | None = None
    total_destinatarios: int
    por_status: dict[str, int] = {}
    destinatarios: list[DestinatarioBroadcastSaida] = []


class NaoEntregaSaida(BaseModel):
    """Um responsável que (provavelmente) não recebeu o aviso de um broadcast."""

    contato: str
    nome: str
    status: str
    motivo: str  # "falha_envio" | "sem_confirmacao"
    atualizado_em: datetime | None = None


# --------------------------------------------------------------------------- #
# Auditoria de ações (usuários logados + LLM)
# --------------------------------------------------------------------------- #
class RegistroAuditoriaSaida(BaseModel):
    id: UUID
    tenant_id: UUID | None = None
    ator: str  # "usuario" | "llm" | "sistema"
    ator_id: str = ""
    ator_nome: str = ""
    acao: str
    descricao: str = ""
    metadados: dict = {}
    criado_em: datetime


# --------------------------------------------------------------------------- #
# Pais/responsáveis (CRUD) e salas/turmas
# --------------------------------------------------------------------------- #
class PaiEntrada(BaseModel):
    tenant_id: UUID
    nome: str
    telefone: str = Field(..., examples=["+5511999990000"])
    # Salas às quais já vincular o responsável no cadastro (opcional).
    sala_ids: list[UUID] = []


class PaiAtualizar(BaseModel):
    tenant_id: UUID
    nome: str
    telefone: str = Field(..., examples=["+5511999990000"])


class PaiSaida(BaseModel):
    id: UUID
    nome: str
    telefone: str


class SalaEntrada(BaseModel):
    tenant_id: UUID
    nome: str = Field(..., examples=["4ª série B"])
    descricao: str = ""


class SalaAtualizar(BaseModel):
    tenant_id: UUID
    nome: str = Field(..., examples=["4ª série B"])
    descricao: str = ""


class SalaSaida(BaseModel):
    id: UUID
    nome: str
    descricao: str
    total_pais: int
    pais: list[PaiSaida] = []
    professor_id: UUID | None = None
    professor_nome: str = ""


class TenantRef(BaseModel):
    """Corpo mínimo para operações que só precisam confirmar o tenant."""

    tenant_id: UUID


class VinculoPaiEntrada(BaseModel):
    tenant_id: UUID
    contato_id: UUID


# --------------------------------------------------------------------------- #
# Professores (CRUD) e atribuição à série
# --------------------------------------------------------------------------- #
class ProfessorEntrada(BaseModel):
    tenant_id: UUID
    nome: str
    telefone: str = Field(..., examples=["+5511999990000"])
    # Senha opcional: habilita o login do professor no mural (§A1).
    senha: str = ""


class ProfessorAtualizar(BaseModel):
    tenant_id: UUID
    nome: str
    telefone: str = Field(..., examples=["+5511999990000"])
    # ``None`` mantém a senha atual; "" limpa o acesso; texto define nova senha.
    senha: str | None = None


class ProfessorSaida(BaseModel):
    id: UUID
    nome: str
    telefone: str
    tem_acesso: bool = False


class AtribuirProfessorEntrada(BaseModel):
    tenant_id: UUID
    # ``None`` desvincula o professor da série.
    professor_id: UUID | None = None


# --------------------------------------------------------------------------- #
# Alunos (CRUD) — responsáveis N:N, série 1:1
# --------------------------------------------------------------------------- #
class AlunoEntrada(BaseModel):
    tenant_id: UUID
    nome: str
    matricula: str = ""
    # Série/turma (1:1) — obrigatória.
    sala_id: UUID
    # Responsáveis a vincular já no cadastro (opcional).
    responsavel_ids: list[UUID] = []


class AlunoAtualizar(BaseModel):
    tenant_id: UUID
    nome: str
    matricula: str = ""
    sala_id: UUID
    ativo: bool = True


class AlunoSaida(BaseModel):
    id: UUID
    nome: str
    matricula: str
    ativo: bool
    sala_id: UUID
    sala_nome: str = ""
    responsaveis: list[PaiSaida] = []


# --------------------------------------------------------------------------- #
# Importação de alunos em massa (planilha/PDF normalizados pela LLM)
# --------------------------------------------------------------------------- #
class ResponsavelImportadoDTO(BaseModel):
    nome: str
    telefone: str = ""
    aviso: str = ""


class LinhaImportacaoAlunoDTO(BaseModel):
    nome: str
    serie: str
    matricula: str = ""
    responsaveis: list[ResponsavelImportadoDTO] = []
    erros: list[str] = []
    avisos: list[str] = []
    serie_nova: bool = False
    valido: bool = True


class ImportacaoPreviaEntrada(BaseModel):
    tenant_id: UUID
    # Texto bruto da planilha/PDF (CSV, colado, etc.). A LLM normaliza.
    conteudo: str


class ImportacaoPreviaSaida(BaseModel):
    linhas: list[LinhaImportacaoAlunoDTO] = []
    series_existentes: list[str] = []
    series_novas: list[str] = []
    total_validos: int = 0


class ImportacaoConfirmarEntrada(BaseModel):
    tenant_id: UUID
    linhas: list[LinhaImportacaoAlunoDTO] = []
    # Cria as séries citadas que ainda não existem (senão, alunos delas são ignorados).
    criar_series_ausentes: bool = False


class ImportacaoResultadoSaida(BaseModel):
    criados: int = 0
    ignorados: int = 0
    series_criadas: list[str] = []
    erros: list[str] = []


# --------------------------------------------------------------------------- #
# Cobertura de contatos da turma e notificação ao professor
# --------------------------------------------------------------------------- #
class AlunoResumoSaida(BaseModel):
    id: UUID
    nome: str
    matricula: str = ""


class CoberturaSalaSaida(BaseModel):
    sala_id: UUID
    sala_nome: str
    total_alunos: int
    total_sem_contato: int
    alunos_sem_contato: list[AlunoResumoSaida] = []


class NotificarProfessorEntrada(BaseModel):
    tenant_id: UUID
    # WhatsApp do professor que vai coletar os contatos faltantes.
    telefone: str = Field(..., examples=["+5511999990000"])
    # Mensagem opcional acrescentada antes do aviso automático.
    mensagem: str = ""


class NotificarProfessorSaida(BaseModel):
    enviado: bool
    id_externo: str
    telefone: str
    total_sem_contato: int
    cobertura: CoberturaSalaSaida


# --------------------------------------------------------------------------- #
# Base de conhecimento (RAG) e system prompt por tenant
# --------------------------------------------------------------------------- #
class DocumentoConhecimentoEntrada(BaseModel):
    tenant_id: UUID
    nome: str = Field(..., examples=["Manual de procedimentos 2026"])
    conteudo: str
    # "procedimento" | "aviso" | "faq"
    tipo: str = "procedimento"


class FonteConhecimentoSaida(BaseModel):
    id: UUID
    nome: str
    tipo: str
    total_trechos: int
    criado_em: datetime


class RespostaRapidaEntrada(BaseModel):
    tenant_id: UUID
    chave: str = Field(..., examples=["Horário do portão"])
    conteudo: str
    ativo: bool = True


class RespostaRapidaAtualizar(BaseModel):
    tenant_id: UUID
    chave: str
    conteudo: str
    ativo: bool = True


class RespostaRapidaSaida(BaseModel):
    id: UUID
    chave: str
    conteudo: str
    ativo: bool
    fonte_id: UUID | None = None
    atualizado_em: datetime | None = None


class ImpressaoEntrada(BaseModel):
    tenant_id: UUID
    arquivo_nome: str = Field(..., examples=["prova_2bim_5A.pdf"])
    professor_id: UUID | None = None
    arquivo_url: str = ""
    copias: int = 1
    colorido: bool = False
    frente_verso: bool = False
    observacao: str = ""


class ImpressaoStatusEntrada(BaseModel):
    tenant_id: UUID
    # "pendente" | "em_processo" | "concluida" | "cancelada"
    status: str


class ImpressaoSaida(BaseModel):
    id: UUID
    professor_id: UUID | None = None
    professor_nome: str = ""
    arquivo_nome: str
    arquivo_url: str = ""
    copias: int
    colorido: bool
    frente_verso: bool
    observacao: str = ""
    status: str
    criado_em: datetime
    atualizado_em: datetime | None = None


class AvisoTemporizadoEntrada(BaseModel):
    tenant_id: UUID
    mensagem: str = Field(
        ..., examples=["Por motivo de saúde, a secretaria não abre à tarde hoje."]
    )
    ativo: bool = True
    inicia_em: datetime | None = None
    expira_em: datetime | None = None


class AvisoTemporizadoAtualizar(BaseModel):
    tenant_id: UUID
    mensagem: str
    ativo: bool = True
    inicia_em: datetime | None = None
    expira_em: datetime | None = None


class AvisoTemporizadoSaida(BaseModel):
    id: UUID
    mensagem: str
    ativo: bool
    inicia_em: datetime | None = None
    expira_em: datetime | None = None
    vigente: bool = False
    atualizado_em: datetime | None = None


class PromptTenantEntrada(BaseModel):
    tenant_id: UUID
    conteudo: str = ""


class PromptTenantSaida(BaseModel):
    tenant_id: UUID
    conteudo: str
    atualizado_em: datetime | None = None


# --------------------------------------------------------------------------- #
# Mural do professor: recados + confirmação de leitura (§A1)
# --------------------------------------------------------------------------- #
class ProfessorLoginEntrada(BaseModel):
    tenant_id: UUID
    telefone: str = Field(..., examples=["+5511999990000"])
    senha: str


class ProfessorLogadoSaida(BaseModel):
    id: UUID
    nome: str
    telefone: str
    tenant_id: UUID


class ProfessorTokenSaida(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_em: int
    professor: ProfessorLogadoSaida


class RecadoEntrada(BaseModel):
    tenant_id: UUID
    titulo: str = Field(..., examples=["Reunião pedagógica sexta-feira"])
    corpo: str


class RecadoResumoSaida(BaseModel):
    id: UUID
    titulo: str
    corpo: str
    autor_nome: str = ""
    criado_em: datetime
    total_professores: int = 0
    total_lidos: int = 0
    total_nao_lidos: int = 0


class LeitorRecadoSaida(BaseModel):
    professor_id: UUID
    nome: str
    telefone: str
    lido_em: datetime | None = None


class RecadoStatusLeituraSaida(BaseModel):
    id: UUID
    titulo: str
    corpo: str
    criado_em: datetime
    lidos: list[LeitorRecadoSaida] = []
    nao_lidos: list[LeitorRecadoSaida] = []


class RecadoDoProfessorSaida(BaseModel):
    id: UUID
    titulo: str
    corpo: str
    autor_nome: str = ""
    criado_em: datetime
    lido: bool = False
    lido_em: datetime | None = None


class ReNotificarRecadoSaida(BaseModel):
    avisados: int


class ProfessorImpressaoEntrada(BaseModel):
    """Solicitação de impressão criada pelo próprio professor logado (tenant/professor
    vêm do token, não do corpo)."""

    arquivo_nome: str = Field(..., examples=["prova_2bim_5A.pdf"])
    arquivo_url: str = ""
    copias: int = 1
    colorido: bool = False
    frente_verso: bool = False
    observacao: str = ""


# --------------------------------------------------------------------------- #
# Onda 2 · A2/A4 — Canal interno professor → secretaria/gestão/pedagógico
# --------------------------------------------------------------------------- #
class SolicitacaoInternaEntrada(BaseModel):
    """Solicitação interna aberta pela secretaria em nome de um professor."""

    tenant_id: UUID
    assunto: str = Field(..., examples=["Falta amanhã (consulta médica)"])
    corpo: str
    professor_id: UUID | None = None
    categoria: str = Field("secretaria", examples=["secretaria", "gestao", "pedagogico"])


class ProfessorSolicitacaoInternaEntrada(BaseModel):
    """Solicitação interna criada pelo próprio professor logado (tenant/professor vêm do token)."""

    assunto: str = Field(..., examples=["Preciso de 2ª via da lista de chamada"])
    corpo: str
    categoria: str = Field("secretaria", examples=["secretaria", "gestao", "pedagogico"])


class SolicitacaoInternaRespostaEntrada(BaseModel):
    tenant_id: UUID
    resposta: str
    notificar: bool = False


class SolicitacaoInternaStatusEntrada(BaseModel):
    tenant_id: UUID
    status: str = Field(..., examples=["em_andamento", "resolvida", "cancelada"])


class SolicitacaoInternaSaida(BaseModel):
    id: UUID
    professor_id: UUID | None = None
    professor_nome: str = ""
    assunto: str
    corpo: str
    categoria: str
    status: str
    resposta: str = ""
    respondido_em: datetime | None = None
    criado_em: datetime
    atualizado_em: datetime


# --------------------------------------------------------------------------- #
# Onda 2 · A3 — Canal pai ↔ professor mediado
# --------------------------------------------------------------------------- #
class MediacaoEnvioEntrada(BaseModel):
    """Mensagem enviada pelo professor logado a um responsável (sai pelo nº da escola)."""

    contato_telefone: str = Field(..., examples=["+5515999990000"])
    corpo: str


class MediacaoRecebidaEntrada(BaseModel):
    """Registro de mensagem recebida de um responsável, direcionada a um professor."""

    tenant_id: UUID
    professor_id: UUID
    contato_telefone: str
    corpo: str
    contato_nome: str = ""


class MensagemMediadaSaida(BaseModel):
    id: UUID
    professor_id: UUID
    contato_telefone: str
    contato_nome: str = ""
    professor_nome: str = ""
    direcao: str
    corpo: str
    criado_em: datetime


class InterlocutorMediadoSaida(BaseModel):
    contato_telefone: str
    contato_nome: str = ""
    total_mensagens: int
    ultima_em: datetime | None = None
    ultima_previa: str = ""


# --------------------------------------------------------------------------- #
# Onda 2 · B2 — Cota e relatório de impressões
# --------------------------------------------------------------------------- #
class CotaImpressaoEntrada(BaseModel):
    tenant_id: UUID
    professor_id: UUID
    limite_mensal: int = Field(0, examples=[3000])


class CotaImpressaoSaida(BaseModel):
    id: UUID
    professor_id: UUID
    professor_nome: str = ""
    limite_mensal: int
    ilimitado: bool


class LinhaRelatorioImpressaoSaida(BaseModel):
    professor_id: UUID | None = None
    professor_nome: str
    total_solicitacoes: int
    total_copias: int
    limite_mensal: int
    ilimitado: bool
    excedeu: bool
    restante: int


class RelatorioImpressaoSaida(BaseModel):
    competencia: str
    total_copias: int
    total_solicitacoes: int
    linhas: list[LinhaRelatorioImpressaoSaida] = []


# --------------------------------------------------------------------------- #
# Onda 2 · F1 — Progressão de série e ciclo de vida do responsável
# --------------------------------------------------------------------------- #
class PromocaoItemEntrada(BaseModel):
    origem_sala_id: UUID
    destino_sala_id: UUID | None = None  # None = última série (marca ex-alunos)


class PromoverTurmasEntrada(BaseModel):
    tenant_id: UUID
    promocoes: list[PromocaoItemEntrada]


class ResultadoPromocaoSaida(BaseModel):
    origem_sala_id: UUID
    origem_sala_nome: str
    destino_sala_id: UUID | None = None
    destino_sala_nome: str = ""
    alunos_promovidos: int
    alunos_formados: int


class InativarResponsaveisEntrada(BaseModel):
    tenant_id: UUID


class ResponsavelInativadoSaida(BaseModel):
    contato_id: UUID
    nome: str
    telefone: str


# --------------------------------------------------------------------------- #
# Onda 3 · I1 — Aviso de falta e chamada de eventual
# --------------------------------------------------------------------------- #
class FaltaEntrada(BaseModel):
    tenant_id: UUID
    data: str  # "YYYY-MM-DD"
    motivo: str = ""
    professor_id: UUID | None = None
    professor_nome: str = ""


class ProfessorFaltaEntrada(BaseModel):
    data: str  # "YYYY-MM-DD"
    motivo: str = ""


class ChamarEventualEntrada(BaseModel):
    tenant_id: UUID
    telefones: list[str]
    mensagem: str = ""


class ConfirmarEventualEntrada(BaseModel):
    tenant_id: UUID
    eventual_nome: str
    eventual_telefone: str = ""


class FaltaAcaoEntrada(BaseModel):
    tenant_id: UUID


class FaltaSaida(BaseModel):
    id: UUID
    data: str
    motivo: str
    professor_id: UUID | None = None
    professor_nome: str = ""
    status: str
    eventual_nome: str = ""
    eventual_telefone: str = ""
    eventuais_chamados: list[str] = []
    criado_em: datetime
    atualizado_em: datetime


# --------------------------------------------------------------------------- #
# Onda 3 · H1 — Exportação de conversa para fins legais
# --------------------------------------------------------------------------- #
class ConversaExportadaSaida(BaseModel):
    conversa_id: UUID
    escola_nome: str
    contato: str
    documento: str
    total_mensagens: int
    inicio: datetime | None = None
    fim: datetime | None = None
    gerado_em: datetime


# --------------------------------------------------------------------------- #
# Onda 3 · D1/D2/D3 — Ficha de matrícula digital
# --------------------------------------------------------------------------- #
class FichaEntrada(BaseModel):
    tenant_id: UUID
    aluno_id: UUID
    campos: dict


class FichaSaida(BaseModel):
    aluno_id: UUID
    aluno_nome: str = ""
    campos: dict
    atualizado_em: datetime


class FichaPreviaEntrada(BaseModel):
    tenant_id: UUID
    conteudo: str


class FichaPreviaSaida(BaseModel):
    campos: dict
    avisos: list[str] = []
    erros: list[str] = []
    valido: bool


class FichaConfirmarEntrada(BaseModel):
    tenant_id: UUID
    aluno_id: UUID
    campos: dict


# --------------------------------------------------------------------------- #
# Onda 3 · E1 — Matrícula self-service pelo WhatsApp
# --------------------------------------------------------------------------- #
class MatriculaIniciarEntrada(BaseModel):
    tenant_id: UUID
    contato_telefone: str
    nome_responsavel: str = ""
    nome_aluno: str = ""


class DocumentoMatriculaSaida(BaseModel):
    nome: str
    url: str = ""
    recebido_em: datetime


class MatriculaSaida(BaseModel):
    id: UUID
    contato_telefone: str
    nome_responsavel: str = ""
    nome_aluno: str = ""
    status: str
    observacao: str = ""
    documentos: list[DocumentoMatriculaSaida] = []
    criado_em: datetime
    atualizado_em: datetime


class MatriculaIniciarSaida(BaseModel):
    solicitacao: MatriculaSaida
    mensagem: str


class MatriculaDocumentoEntrada(BaseModel):
    tenant_id: UUID
    nome: str
    url: str = ""


class MatriculaStatusEntrada(BaseModel):
    tenant_id: UUID
    status: str
    observacao: str | None = None
