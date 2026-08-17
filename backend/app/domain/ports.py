"""Portas (interfaces) do domínio.

Definem os contratos que a camada de aplicação usa e que a infraestrutura implementa.
A regra de dependência aponta para dentro: aqui não há framework/SDK.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import (
    Aluno,
    ArquivoBaixado,
    AtendimentoHumano,
    AvisoFalta,
    AvisoTemporizado,
    Broadcast,
    CategoriaDocumento,
    Contato,
    Conversa,
    CotaImpressao,
    Documento,
    DocumentoLido,
    DocumentoRecebido,
    EstadoAtendimento,
    FerramentaSpec,
    FichaMatricula,
    FonteConhecimento,
    Grupo,
    LeituraRecado,
    Mensagem,
    NumeroBloqueado,
    MensagemMediada,
    MetricasUsoEscola,
    MessageQuota,
    MessageTemplate,
    Professor,
    PromptTenant,
    Recado,
    RegistroAuditoria,
    RespostaLLM,
    RespostaRapida,
    ResultadoBusca,
    ResultadoTaxa,
    ResumoConversa,
    ResumoEscola,
    Sala,
    SugestaoBloqueio,
    SolicitacaoImpressao,
    SolicitacaoInterna,
    SolicitacaoMatricula,
    StatusAtendimentoHumano,
    StatusDocumento,
    StatusEntrega,
    StatusFalta,
    StatusImpressao,
    StatusMatricula,
    StatusSolicitacaoInterna,
    Tenant,
    TemplateRemoto,
    TrechoConhecimento,
    TurnoConversa,
    Usuario,
    Waba,
)


# --------------------------------------------------------------------------- #
# LLM (geração / raciocínio)
# --------------------------------------------------------------------------- #
@runtime_checkable
class LLMProvider(Protocol):
    """Geração de texto. Adaptadores: fake, Anthropic, OpenAI..."""

    async def gerar(self, *, sistema: str, mensagens: list[dict[str, str]]) -> str:
        """Recebe um prompt de sistema e o histórico ({"role","content"}) e devolve texto."""
        ...

    async def gerar_com_ferramentas(
        self,
        *,
        sistema: str,
        turnos: list[TurnoConversa],
        ferramentas: list[FerramentaSpec],
    ) -> RespostaLLM:
        """Um round-trip com ferramentas: devolve texto e/ou chamadas de ferramenta.

        Não executa o loop agêntico — apenas reporta a intenção do modelo. Quem
        executa as ferramentas e itera é o caso de uso na camada de aplicação.
        """
        ...


@runtime_checkable
class Embedder(Protocol):
    """Geração de embeddings para o RAG."""

    @property
    def dimensao(self) -> int: ...

    async def embed(self, textos: list[str]) -> list[list[float]]: ...


# --------------------------------------------------------------------------- #
# Vector store / conhecimento (RAG)
# --------------------------------------------------------------------------- #
@runtime_checkable
class VectorStore(Protocol):
    async def indexar(self, trecho: TrechoConhecimento, embedding: list[float]) -> None: ...

    async def buscar(
        self, *, tenant_id: UUID, embedding: list[float], k: int = 4
    ) -> list[ResultadoBusca]: ...

    async def remover_por_fonte(self, *, tenant_id: UUID, fonte_id: UUID) -> int:
        """Remove todos os trechos de uma fonte (documento). Retorna a quantidade removida."""
        ...


# --------------------------------------------------------------------------- #
# Documentos (sistemas externos)
# --------------------------------------------------------------------------- #
@runtime_checkable
class DocumentSource(Protocol):
    """Recupera documentos em sistemas externos. Implementação atual: mock."""

    async def buscar_documentos(
        self, *, tenant_id: UUID, contato: str, consulta: str
    ) -> list[Documento]: ...


# --------------------------------------------------------------------------- #
# Canal de mensagens (inbound + outbound)
# --------------------------------------------------------------------------- #
class EnvioRecusado(RuntimeError):
    """O envio não saiu, com o motivo de quem recusou — não com o código HTTP.

    Mora no domínio, e não no adaptador da Meta, porque **é parte do contrato da porta**:
    quem decide o que fazer com uma falha é o caso de uso, e ele não pode importar
    infraestrutura para saber de que tipo ela foi.

    ``transitorio`` é a distinção que faz a diferença entre reenviar e desistir:

    - **Transitório** (timeout, queda de conexão, 5xx, 429): a mensagem não saiu por algo
      que passa. Tentar de novo resolve, e desistir custa um aviso que a escola acha que
      mandou.
    - **Definitivo** (4xx: template inexistente na conta, número inválido, parâmetros em
      número errado): tentar de novo dá exatamente o mesmo erro, gasta cota e ainda por
      cima **queima a qualidade do número** — que é o que trava a subida do tier (§2.2.2 de
      `docs/producao-whatsapp.md`). Aqui insistir é pior que falhar.
    """

    def __init__(self, motivo: str, *, transitorio: bool = False) -> None:
        super().__init__(motivo)
        self.transitorio = transitorio


@runtime_checkable
class MessageChannel(Protocol):
    # ``remetente`` identifica o número da escola no canal (multi-tenant), tal como
    # ``Tenant.remetente_canal`` o resolve: na Meta é o ``phone_number_id``, nos canais que
    # roteiam por número é o E.164. Quando None/vazio, o adaptador usa o número padrão
    # configurado no canal.
    async def enviar_texto(
        self, *, contato: str, texto: str, remetente: str | None = None
    ) -> str:
        """Envia uma mensagem de texto livre. Retorna o id externo da mensagem."""
        ...

    async def enviar_template(
        self,
        *,
        contato: str,
        template: MessageTemplate,
        parametros: list[str],
        remetente: str | None = None,
    ) -> str:
        """Envia uma mensagem de template (HSM). Retorna o id externo."""
        ...

    async def enviar_documento(
        self, *, contato: str, documento: Documento, remetente: str | None = None
    ) -> str: ...


# --------------------------------------------------------------------------- #
# Rate limiting / cota diária
# --------------------------------------------------------------------------- #
@runtime_checkable
class QuotaPolicy(Protocol):
    """Cota de conversas iniciadas pelo negócio, em janela de 24h corridas por portfólio.

    ``registrar_envio`` recebe o **contato**, não uma quantidade, porque a unidade que a
    Meta cobra é *cliente único na janela* — sem saber para quem foi, não há como não
    contar duas vezes o mesmo responsável. Todo caminho que dispara template precisa
    chamá-lo: além do broadcast, a retomada de atendimento fora da janela de 24h também
    inicia conversa e também consome o teto.
    """

    async def cota(self, tenant_id: UUID) -> MessageQuota: ...

    async def registrar_envio(self, tenant_id: UUID, contato: str) -> None: ...


@runtime_checkable
class RateLimiter(Protocol):
    """Throttling da taxa por segundo da API (independente da cota diária)."""

    async def aguardar_vaga(self) -> None: ...


@runtime_checkable
class ControleTaxa(Protocol):
    """Limite de taxa **de entrada**: quantas chamadas uma origem pode fazer por janela.

    Cobre o brute force contra o login e o consumo desenfreado de LLM por um número em
    loop no webhook. Ao contrário do ``RateLimiter`` (que *espera* uma vaga para não
    estourar a API da Meta), aqui a chamada excedente é **recusada** — quem está
    atacando não merece ser enfileirado.
    """

    async def registrar(
        self, *, chave: str, limite: int, janela_segundos: int
    ) -> ResultadoTaxa:
        """Contabiliza uma tentativa e diz se ela cabe na janela."""
        ...


# --------------------------------------------------------------------------- #
# E-mail (avisos administrativos, ex.: licença a vencer)
# --------------------------------------------------------------------------- #
@runtime_checkable
class EmailSender(Protocol):
    """Envio de e-mails transacionais. Implementação atual: log (mock)."""

    async def enviar(self, *, destinatario: str, assunto: str, corpo: str) -> None: ...


# --------------------------------------------------------------------------- #
# Idempotência (reentrega de webhooks)
# --------------------------------------------------------------------------- #
@runtime_checkable
class RegistroAtendimento(Protocol):
    """Estado do atendimento de cada mensagem recebida, para descartar reentregas.

    A Meta **reenvia** o webhook quando não recebe o ``200 OK`` a tempo. Sem isso a mesma
    dúvida seria atendida (e cobrada na LLM) mais de uma vez.

    O contrato é de **reserva**, não de consulta: ``iniciar`` tenta reservar a mensagem e
    devolve o que encontrou. Consultar-e-depois-gravar abriria a janela em que duas
    réplicas leem "inédita" ao mesmo tempo — que é exatamente o caso da reentrega, já que
    ela chega enquanto a primeira tentativa ainda está na LLM.
    """

    async def iniciar(
        self, *, chave: str, tenant_id: UUID | None = None, origem: str = ""
    ) -> EstadoAtendimento: ...

    async def concluir(self, *, chave: str, resumo: str = "") -> None:
        """Marca a dúvida como sanada (a resposta saiu)."""
        ...

    async def falhar(self, *, chave: str, erro: str = "") -> None:
        """Libera a reserva quando o atendimento não terminou, para que a reentrega da
        Meta possa tentar de novo em vez de encontrar a mensagem eternamente 'em
        atendimento'."""
        ...


# --------------------------------------------------------------------------- #
# Repositórios de persistência
# --------------------------------------------------------------------------- #
@runtime_checkable
class TenantRepository(Protocol):
    """CRUD de escolas (tenants). Operado apenas pelo super admin."""

    async def criar(self, tenant: Tenant) -> Tenant: ...

    async def obter(self, tenant_id: UUID) -> Tenant | None: ...

    async def por_slug(self, slug: str) -> Tenant | None: ...

    async def por_whatsapp(self, numero: str) -> Tenant | None:
        """Escola cujo ``whatsapp_numero`` casa com ``numero`` (E.164). Referência humana."""
        ...

    async def por_meta_phone_number_id(self, phone_number_id: str) -> Tenant | None:
        """Escola dona do ``phone_number_id`` da Meta. **Roteia o inbound do webhook.**

        É o identificador que chega em ``value.metadata.phone_number_id``. Sem escola
        correspondente o evento é descartado — nunca cai num tenant padrão, sob pena de
        vazar a conversa de uma escola para outra.
        """
        ...

    async def listar(self) -> list[Tenant]: ...

    async def listar_resumos(self) -> list[ResumoEscola]: ...

    async def metricas_uso(self, tenant_id: UUID) -> MetricasUsoEscola:
        """Contadores de uso da escola (usuários ativos, contatos, alunos, etc.)."""
        ...

    async def atualizar(self, tenant: Tenant) -> Tenant: ...

    async def remover(self, tenant_id: UUID) -> bool: ...


@runtime_checkable
class ConversaRepository(Protocol):
    async def obter_ou_criar(self, *, tenant_id: UUID, contato: str) -> Conversa:
        """A **sessão viva** do responsável, abrindo outra quando a anterior venceu."""
        ...

    async def encerrar(self, *, conversa_id: UUID) -> None:
        """Fecha a sessão. Idempotente — encerrar duas vezes não reescreve a data."""
        ...

    async def adicionar_mensagem(
        self,
        *,
        conversa_id: UUID,
        autor: str,
        texto: str,
        fontes: list[str] | None = None,
        # Nome de quem respondeu, quando ``autor`` é uma pessoa da secretaria (§6j).
        autor_nome: str = "",
    ) -> None: ...

    async def historico(self, *, conversa_id: UUID, limite: int = 20) -> list[dict[str, str]]: ...

    async def listar_resumos(self, *, tenant_id: UUID) -> list[ResumoConversa]:
        """Conversas do tenant com metadados (total, última mensagem)."""
        ...

    async def obter_conversa(self, *, tenant_id: UUID, conversa_id: UUID) -> Conversa | None: ...

    async def mensagens(self, *, conversa_id: UUID) -> list[Mensagem]: ...


@runtime_checkable
class TemplateRepository(Protocol):
    async def obter(self, *, tenant_id: UUID, template_id: UUID) -> MessageTemplate | None:
        """O template da escola **ou** um global — os dois são visíveis para o tenant."""
        ...

    async def por_nome(self, *, tenant_id: UUID, nome: str) -> MessageTemplate | None:
        """Template pelo nome aprovado na Meta (a chave que a Graph API entende).

        Usado pela retomada de conversa fora da janela de 24h (§A9), onde o template é
        escolhido por configuração — e não por um id que ninguém digitaria. O da própria
        escola tem precedência sobre o global de mesmo nome: quem personalizou espera que
        a versão dela seja a usada.
        """
        ...

    async def listar(self, *, tenant_id: UUID) -> list[MessageTemplate]:
        """Catálogo visível para a escola: os globais mais os dela."""
        ...

    async def salvar(self, template: MessageTemplate) -> MessageTemplate: ...

    async def remover(self, template_id: UUID) -> bool: ...

    async def por_meta_id(self, meta_template_id: str) -> MessageTemplate | None:
        """Busca **cross-tenant**, pelo id da Meta — o caminho do webhook.

        O evento de status não traz escola nenhuma (templates são da WABA), então esta é
        a única chave que o webhook tem. Por isso ela ignora ``tenant_id`` de propósito.
        O id é emitido **por WABA**, então ele identifica não só o texto como em qual
        conta ele foi revisado.
        """
        ...

    async def por_nome_e_idioma(self, *, nome: str, idioma: str) -> MessageTemplate | None:
        """Também cross-tenant: o par (nome, idioma) é único na WABA, e é o que a Meta
        manda quando o evento vem sem o id."""
        ...

    async def listar_todos(self) -> list[MessageTemplate]:
        """Todos os templates, de todas as escolas — usado só pela sincronização."""
        ...


@runtime_checkable
class WabaRepository(Protocol):
    """As contas do WhatsApp Business em que as escolas operam (``Waba``).

    Poucas linhas e raramente escritas — uma a cada lote de escolas —, mas é sobre esta
    lista que a replicação de template global itera: um texto novo precisa ir para toda
    conta ativa, senão as escolas de uma delas ficam sem catálogo.
    """

    async def listar(self, *, apenas_ativas: bool = False) -> list[Waba]: ...

    async def obter(self, waba_id: UUID) -> Waba | None: ...

    async def por_meta_id(self, meta_waba_id: str) -> Waba | None:
        """A conta pelo id na Meta — como o webhook a identifica (``entry[].id``)."""
        ...

    async def salvar(self, waba: Waba) -> Waba: ...

    async def remover(self, waba_id: UUID) -> bool: ...

    async def total_escolas(self) -> dict[UUID, int]:
        """Quantas escolas em cada conta — a ocupação contra o teto de números."""
        ...


@runtime_checkable
class CatalogoTemplates(Protocol):
    """Gestão de templates na Meta (WhatsApp Business Management API).

    Separada de ``MessageChannel`` porque é outra API e outro escopo de token: enviar usa
    ``whatsapp_business_messaging`` e fala com ``/{phone_number_id}/messages``; gerenciar
    template usa ``whatsapp_business_management`` e fala com ``/{waba_id}/message_templates``.
    Misturar as duas obrigaria todo canal a saber submeter template a revisão.

    **A conta é parâmetro, não estado do adaptador.** O mesmo token administra todas as
    WABAs do portfólio, e o que muda entre elas é só o nó da URL; fixar uma no construtor
    faria o produto inteiro escrever numa conta só — que é como o catálogo nasceu, e o
    motivo de a segunda WABA quebrá-lo.
    """

    async def submeter(
        self, template: MessageTemplate, *, meta_waba_id: str
    ) -> TemplateRemoto:
        """Cria o template na Meta e o põe em revisão (é o mesmo POST).

        A revisão é **assíncrona**: o retorno é o estado inicial (normalmente pendente),
        não a aprovação.
        """
        ...

    async def listar(self, *, meta_waba_id: str) -> list[TemplateRemoto]: ...

    async def remover(self, *, nome: str, meta_waba_id: str) -> bool: ...

    async def descrever(self, *, meta_waba_id: str) -> str | None:
        """Nome da conta na Meta, ou ``None`` se o id não corresponde a uma que possamos ver.

        Serve para **confirmar** um id antes de gravá-lo (``AdotarContaDoWebhook``): sem
        isso, adotar um id lido de um evento seria acreditar num campo cujo significado a
        documentação não afirma. Aqui a resposta da própria Meta decide.
        """
        ...


@runtime_checkable
class BroadcastRepository(Protocol):
    async def salvar(self, broadcast: Broadcast) -> None: ...

    async def obter(self, broadcast_id: UUID) -> Broadcast | None: ...

    async def listar(self, *, tenant_id: UUID) -> list[Broadcast]:
        """Broadcasts (mensagens em massa) do tenant, mais recentes primeiro."""
        ...

    async def registrar_status(
        self, *, mensagem_id_externo: str, status: StatusEntrega
    ) -> bool:
        """Atualiza o status de um destinatário pelo id externo da mensagem (webhook Meta).

        Retorna ``True`` se algum destinatário foi atualizado.
        """
        ...

    async def listar_retomaveis(self, *, desde: datetime) -> list[Broadcast]:
        """Disparos interrompidos pela cota diária, ainda dentro do prazo de retomada.

        São os ``PARCIAL_LIMITE``: começaram, esbarraram no teto de destinatários únicos
        por 24h e deixaram o resto pendente. ``desde`` recorta por idade — aviso de três
        semanas atrás entregue hoje é pior que aviso não entregue.
        """
        ...


@runtime_checkable
class AuditLogRepository(Protocol):
    """Registro e consulta do log de auditoria (ações de usuários e da LLM)."""

    async def registrar(self, registro: RegistroAuditoria) -> RegistroAuditoria: ...

    async def listar(
        self, *, tenant_id: UUID, limite: int = 200
    ) -> list[RegistroAuditoria]:
        """Registros da escola, mais recentes primeiro."""
        ...


@runtime_checkable
class UsuarioRepository(Protocol):
    async def por_email(self, email: str) -> Usuario | None: ...

    async def obter(self, usuario_id: UUID) -> Usuario | None: ...

    async def criar(self, usuario: Usuario) -> Usuario: ...

    async def listar(self, *, tenant_id: UUID | None = None) -> list[Usuario]: ...

    async def por_ids(self, ids: Sequence[UUID]) -> list[Usuario]:
        """Resolve vários usuários numa consulta só — é o que a auditoria precisa.

        Sem isso, uma página de log com dez atores diferentes faria dez idas ao banco.
        """
        ...

    async def atualizar(self, usuario: Usuario) -> Usuario: ...


@runtime_checkable
class GrupoRepository(Protocol):
    async def criar(self, grupo: Grupo) -> Grupo: ...

    async def obter(self, *, tenant_id: UUID, grupo_id: UUID) -> Grupo | None: ...

    async def listar(self, *, tenant_id: UUID) -> list[Grupo]: ...

    async def adicionar_contato(
        self, *, tenant_id: UUID, grupo_id: UUID, nome: str, telefone: str
    ) -> Contato: ...

    async def membros(self, *, tenant_id: UUID, grupo_id: UUID) -> list[Contato]: ...


@runtime_checkable
class ContatoRepository(Protocol):
    """CRUD de pais/responsáveis (``Contato``), escopado por tenant."""

    async def criar(self, contato: Contato) -> Contato: ...

    async def obter(self, *, tenant_id: UUID, contato_id: UUID) -> Contato | None: ...

    async def por_telefone(self, *, tenant_id: UUID, telefone: str) -> Contato | None: ...

    async def por_cpf(self, *, tenant_id: UUID, cpf: str) -> Contato | None:
        """CPF vazio devolve ``None`` — não identifica ninguém."""
        ...

    async def por_telefones(
        self, *, tenant_id: UUID, telefones: Sequence[str]
    ) -> dict[str, Contato]:
        """Versão em lote de ``por_telefone``, indexada pelo telefone.

        Existe para nomear uma página inteira de atendimentos (§6j) numa consulta só, em
        vez de uma por card.
        """
        ...

    async def listar(self, *, tenant_id: UUID) -> list[Contato]: ...

    async def atualizar(self, contato: Contato) -> Contato: ...

    async def remover(self, *, tenant_id: UUID, contato_id: UUID) -> bool: ...


@runtime_checkable
class FonteConhecimentoRepository(Protocol):
    """Metadados dos documentos enviados pela escola para a base de RAG (por tenant)."""

    async def criar(self, fonte: FonteConhecimento) -> FonteConhecimento: ...

    async def obter(self, *, tenant_id: UUID, fonte_id: UUID) -> FonteConhecimento | None: ...

    async def listar(self, *, tenant_id: UUID) -> list[FonteConhecimento]: ...

    async def atualizar(self, fonte: FonteConhecimento) -> FonteConhecimento: ...

    async def remover(self, *, tenant_id: UUID, fonte_id: UUID) -> bool: ...


@runtime_checkable
class PromptTenantRepository(Protocol):
    """System prompt personalizado por tenant (o "CLAUDE.md" da escola)."""

    async def obter(self, *, tenant_id: UUID) -> PromptTenant | None: ...

    async def salvar(self, *, tenant_id: UUID, conteudo: str) -> PromptTenant: ...


@runtime_checkable
class AvisoTemporizadoRepository(Protocol):
    """CRUD dos avisos temporizados da escola, escopado por tenant."""

    async def criar(self, aviso: AvisoTemporizado) -> AvisoTemporizado: ...

    async def obter(
        self, *, tenant_id: UUID, aviso_id: UUID
    ) -> AvisoTemporizado | None: ...

    async def listar(self, *, tenant_id: UUID) -> list[AvisoTemporizado]: ...

    async def vigente(self, *, tenant_id: UUID) -> AvisoTemporizado | None:
        """Aviso atualmente vigente do tenant (ativo e dentro da janela), se houver."""
        ...

    async def atualizar(self, aviso: AvisoTemporizado) -> AvisoTemporizado: ...

    async def remover(self, *, tenant_id: UUID, aviso_id: UUID) -> bool: ...


@runtime_checkable
class MuralRepository(Protocol):
    """Mural de recados aos professores + confirmação de leitura, escopado por tenant."""

    async def criar(self, recado: Recado) -> Recado: ...

    async def obter(self, *, tenant_id: UUID, recado_id: UUID) -> Recado | None: ...

    async def listar(self, *, tenant_id: UUID) -> list[Recado]: ...

    async def remover(self, *, tenant_id: UUID, recado_id: UUID) -> bool: ...

    async def marcar_leitura(
        self, *, tenant_id: UUID, recado_id: UUID, professor_id: UUID
    ) -> LeituraRecado:
        """Marca (idempotente) que o professor leu o recado; devolve a leitura."""
        ...

    async def leituras(self, *, recado_id: UUID) -> list[LeituraRecado]:
        """Leituras de um recado (quem leu e quando)."""
        ...

    async def leituras_do_professor(
        self, *, tenant_id: UUID, professor_id: UUID
    ) -> list[LeituraRecado]:
        """Leituras feitas por um professor (para marcar seus recados como lidos)."""
        ...


@runtime_checkable
class SolicitacaoImpressaoRepository(Protocol):
    """Fila de solicitações de impressão dos professores, escopada por tenant."""

    async def criar(self, solicitacao: SolicitacaoImpressao) -> SolicitacaoImpressao: ...

    async def obter(
        self, *, tenant_id: UUID, solicitacao_id: UUID
    ) -> SolicitacaoImpressao | None: ...

    async def listar(
        self, *, tenant_id: UUID, status: StatusImpressao | None = None
    ) -> list[SolicitacaoImpressao]:
        """Solicitações do tenant (opcionalmente filtradas por status), recentes primeiro."""
        ...

    async def atualizar(self, solicitacao: SolicitacaoImpressao) -> SolicitacaoImpressao: ...

    async def por_media_id(
        self, *, tenant_id: UUID, media_id: str
    ) -> SolicitacaoImpressao | None:
        """Pedido já criado a partir de uma mídia da Meta (dedupe de reentrega)."""
        ...

    async def consumo_do_professor(
        self, *, tenant_id: UUID, professor_id: UUID, competencia: str
    ) -> int:
        """Cópias consumidas na competência ``YYYY-MM``, ignorando as canceladas."""
        ...

    async def remover(self, *, tenant_id: UUID, solicitacao_id: UUID) -> bool: ...


@runtime_checkable
class RespostaRapidaRepository(Protocol):
    """CRUD das respostas rápidas ("atalhos") da escola, escopado por tenant."""

    async def criar(self, resposta: RespostaRapida) -> RespostaRapida: ...

    async def obter(
        self, *, tenant_id: UUID, resposta_id: UUID
    ) -> RespostaRapida | None: ...

    async def por_chave(self, *, tenant_id: UUID, chave: str) -> RespostaRapida | None: ...

    async def listar(self, *, tenant_id: UUID) -> list[RespostaRapida]: ...

    async def atualizar(self, resposta: RespostaRapida) -> RespostaRapida: ...

    async def remover(self, *, tenant_id: UUID, resposta_id: UUID) -> bool: ...


@runtime_checkable
class SalaRepository(Protocol):
    """CRUD de turmas, escopado por tenant.

    O vínculo pai↔turma **não é mantido aqui**: ele é derivado dos alunos ativos da turma
    (``pais``). ``vincular_pai``/``desvincular_pai`` existiram e foram removidos junto com
    a tabela ``sala_contatos`` — ver §6c.
    """

    async def criar(self, sala: Sala) -> Sala: ...

    async def obter(self, *, tenant_id: UUID, sala_id: UUID) -> Sala | None: ...

    async def listar(self, *, tenant_id: UUID) -> list[Sala]: ...

    async def atualizar(self, sala: Sala) -> Sala: ...

    async def remover(self, *, tenant_id: UUID, sala_id: UUID) -> bool: ...

    async def pais(self, *, tenant_id: UUID, sala_id: UUID) -> list[Contato]:
        """Responsáveis com **aluno ativo** na turma. Derivado, não armazenado."""
        ...

    async def definir_professor(
        self, *, tenant_id: UUID, sala_id: UUID, professor_id: UUID | None
    ) -> Sala: ...


@runtime_checkable
class ProfessorRepository(Protocol):
    """CRUD do cadastro funcional de professores, escopado por tenant."""

    async def criar(self, professor: Professor) -> Professor: ...

    async def obter(self, *, tenant_id: UUID, professor_id: UUID) -> Professor | None: ...

    async def por_telefone(self, *, tenant_id: UUID, telefone: str) -> Professor | None: ...

    async def por_cpf(self, *, tenant_id: UUID, cpf: str) -> Professor | None:
        """CPF vazio devolve ``None`` — não identifica ninguém."""
        ...

    async def listar(
        self, *, tenant_id: UUID, apenas_eventuais: bool = False
    ) -> list[Professor]:
        """``apenas_eventuais`` filtra os candidatos a cobrir falta (§I1)."""
        ...

    async def atualizar(self, professor: Professor) -> Professor: ...

    async def remover(self, *, tenant_id: UUID, professor_id: UUID) -> bool: ...


@runtime_checkable
class AlunoRepository(Protocol):
    """CRUD de alunos e vínculo N:N com responsáveis (contatos), escopado por tenant."""

    async def criar(self, aluno: Aluno) -> Aluno: ...

    async def obter(self, *, tenant_id: UUID, aluno_id: UUID) -> Aluno | None: ...

    async def listar(
        self,
        *,
        tenant_id: UUID,
        sala_id: UUID | None = None,
        apenas_ativos: bool | None = None,
        q: str = "",
        pagina: int | None = None,
        por_pagina: int | None = None,
    ) -> list[Aluno]:
        """``q`` busca por nome ou matrícula (sem diferenciar maiúsculas)."""
        ...

    async def contar(
        self,
        *,
        tenant_id: UUID,
        sala_id: UUID | None = None,
        apenas_ativos: bool | None = None,
        q: str = "",
    ) -> int: ...

    async def atualizar(self, aluno: Aluno) -> Aluno: ...

    async def remover(self, *, tenant_id: UUID, aluno_id: UUID) -> bool: ...

    async def vincular_responsavel(
        self, *, tenant_id: UUID, aluno_id: UUID, contato_id: UUID
    ) -> None: ...

    async def desvincular_responsavel(
        self, *, tenant_id: UUID, aluno_id: UUID, contato_id: UUID
    ) -> None: ...


# --------------------------------------------------------------------------- #
# Onda 2 — comunicação interna, mediação, cota de impressão
# --------------------------------------------------------------------------- #
@runtime_checkable
class SolicitacaoInternaRepository(Protocol):
    """Canal interno professor → secretaria/gestão/pedagógico (§A2/A4), por tenant."""

    async def criar(self, solicitacao: SolicitacaoInterna) -> SolicitacaoInterna: ...

    async def obter(
        self, *, tenant_id: UUID, solicitacao_id: UUID
    ) -> SolicitacaoInterna | None: ...

    async def listar(
        self,
        *,
        tenant_id: UUID,
        categoria: str | None = None,
        status: StatusSolicitacaoInterna | None = None,
        professor_id: UUID | None = None,
    ) -> list[SolicitacaoInterna]:
        """Solicitações do tenant, mais recentes primeiro; filtros opcionais."""
        ...

    async def atualizar(self, solicitacao: SolicitacaoInterna) -> SolicitacaoInterna: ...

    async def remover(self, *, tenant_id: UUID, solicitacao_id: UUID) -> bool: ...


@runtime_checkable
class MediacaoRepository(Protocol):
    """Conversas mediadas pai ↔ professor (§A3), escopadas por tenant."""

    async def registrar(self, mensagem: MensagemMediada) -> MensagemMediada: ...

    async def conversa(
        self, *, tenant_id: UUID, professor_id: UUID, contato_telefone: str
    ) -> list[MensagemMediada]:
        """Mensagens de um par (professor, responsável), da mais antiga à mais recente."""
        ...

    async def interlocutores(
        self, *, tenant_id: UUID, professor_id: UUID
    ) -> list[MensagemMediada]:
        """Todas as mensagens do professor (para agrupar por responsável no painel)."""
        ...


@runtime_checkable
class CotaImpressaoRepository(Protocol):
    """Franquia mensal de impressão por professor (§B2), escopada por tenant."""

    async def definir(self, cota: CotaImpressao) -> CotaImpressao:
        """Cria ou atualiza (upsert) a cota do professor."""
        ...

    async def por_professor(
        self, *, tenant_id: UUID, professor_id: UUID
    ) -> CotaImpressao | None: ...

    async def listar(self, *, tenant_id: UUID) -> list[CotaImpressao]: ...

    async def remover(self, *, tenant_id: UUID, professor_id: UUID) -> bool: ...


# --------------------------------------------------------------------------- #
# Onda 3 — falta/eventual, ficha de matrícula e matrícula self-service
# --------------------------------------------------------------------------- #
@runtime_checkable
class AvisoFaltaRepository(Protocol):
    """Avisos de falta de professor + chamada de eventual (§I1), por tenant."""

    async def criar(self, aviso: AvisoFalta) -> AvisoFalta: ...

    async def obter(self, *, tenant_id: UUID, aviso_id: UUID) -> AvisoFalta | None: ...

    async def listar(
        self, *, tenant_id: UUID, status: StatusFalta | None = None
    ) -> list[AvisoFalta]:
        """Avisos do tenant (opcionalmente filtrados por status), recentes primeiro."""
        ...

    async def atualizar(self, aviso: AvisoFalta) -> AvisoFalta: ...

    async def remover(self, *, tenant_id: UUID, aviso_id: UUID) -> bool: ...


@runtime_checkable
class FichaMatriculaRepository(Protocol):
    """Ficha de matrícula digital por aluno (§D1/D2), escopada por tenant (upsert 1:1)."""

    async def salvar(self, ficha: FichaMatricula) -> FichaMatricula:
        """Cria ou atualiza (upsert) a ficha do aluno."""
        ...

    async def por_aluno(
        self, *, tenant_id: UUID, aluno_id: UUID
    ) -> FichaMatricula | None: ...

    async def remover(self, *, tenant_id: UUID, aluno_id: UUID) -> bool: ...


@runtime_checkable
class SolicitacaoMatriculaRepository(Protocol):
    """Matrículas self-service iniciadas pelo responsável (§E1), por tenant."""

    async def criar(self, solicitacao: SolicitacaoMatricula) -> SolicitacaoMatricula: ...

    async def obter(
        self, *, tenant_id: UUID, solicitacao_id: UUID
    ) -> SolicitacaoMatricula | None: ...

    async def por_telefone(
        self, *, tenant_id: UUID, telefone: str
    ) -> SolicitacaoMatricula | None:
        """Solicitação em aberto do responsável (para retomar o fluxo pelo WhatsApp)."""
        ...

    async def listar(
        self, *, tenant_id: UUID, status: StatusMatricula | None = None
    ) -> list[SolicitacaoMatricula]: ...

    async def atualizar(
        self, solicitacao: SolicitacaoMatricula
    ) -> SolicitacaoMatricula: ...


# --------------------------------------------------------------------------- #
# Atendimento humano — o assistente entrega a conversa à secretaria (§6j)
# --------------------------------------------------------------------------- #
@runtime_checkable
class AtendimentoHumanoRepository(Protocol):
    """Fila de atendimentos encaminhados pelo assistente, por tenant."""

    async def criar(self, atendimento: AtendimentoHumano) -> AtendimentoHumano: ...

    async def obter(
        self, *, tenant_id: UUID, atendimento_id: UUID
    ) -> AtendimentoHumano | None: ...

    async def em_aberto_por_conversa(
        self, *, conversa_id: UUID
    ) -> AtendimentoHumano | None:
        """Atendimento vivo da conversa — na fila **ou** apenas oferecido.

        Consultado a cada mensagem recebida, antes de decidir se o assistente responde ou
        fica em silêncio porque uma pessoa assumiu (ver ``AtendimentoHumano.na_fila``).
        """
        ...

    async def listar(
        self,
        *,
        tenant_id: UUID,
        status: Sequence[StatusAtendimentoHumano] | None = None,
        atendente_id: UUID | None = None,
        pagina: int | None = None,
        por_pagina: int | None = None,
    ) -> list[AtendimentoHumano]:
        """Fila do tenant, mais antigos primeiro (quem espera há mais tempo)."""
        ...

    async def contar(
        self,
        *,
        tenant_id: UUID,
        status: Sequence[StatusAtendimentoHumano] | None = None,
        atendente_id: UUID | None = None,
    ) -> int: ...

    async def atualizar(self, atendimento: AtendimentoHumano) -> AtendimentoHumano: ...


# --------------------------------------------------------------------------- #
# Documentos recebidos dos responsáveis (§6k)
# --------------------------------------------------------------------------- #
@runtime_checkable
class ArquivoStorage(Protocol):
    """Onde os bytes de um arquivo recebido moram.

    Porta separada do repositório de metadados **de propósito**: os metadados são do
    negócio e ficam no Postgres para sempre; os bytes são infraestrutura e vão mudar de
    casa. Hoje o adaptador é Postgres (``bytea``), que não pede infra nova; guardar
    atestado médico ali indefinidamente infla um banco cobrado por GB, então a troca por
    object storage é questão de quando, não de se — e esta porta é o que a torna barata.
    """

    async def guardar(self, *, chave: str, conteudo: bytes, mime: str) -> None: ...

    async def ler(self, *, chave: str) -> bytes | None:
        """Bytes do arquivo, ou ``None`` se a chave não existe (ou já foi expurgada)."""
        ...

    async def remover(self, *, chave: str) -> bool: ...


@runtime_checkable
class FonteMidia(Protocol):
    """Baixa a mídia que o responsável enviou pelo canal.

    Não faz parte de ``MessageChannel``: aquele contrato é sobre **enviar**, e misturar as
    duas coisas obrigaria todo canal a saber baixar arquivo. Na Meta o download tem dois
    passos (metadados → URL temporária autenticada), o que é detalhe do adaptador.
    """

    async def baixar(self, media_id: str) -> ArquivoBaixado | None: ...


@runtime_checkable
class LeitorDocumento(Protocol):
    """Lê um documento **como imagem/PDF** e devolve o que conseguiu extrair (§4.3).

    Porta separada de ``LLMProvider`` de propósito: aquele contrato é de **texto**, e nem
    todo provedor sabe olhar uma foto. Misturar as duas capacidades obrigaria todo
    adaptador de LLM a fingir que enxerga.

    O que volta é **sugestão**: quem valida é o código, e quem confirma é a secretaria.
    O mesmo fluxo prévia → confirmação da importação em massa (§6c-quater) e da leitura
    de ficha (§D3).
    """

    async def ler(self, *, conteudo: bytes, mime: str) -> DocumentoLido: ...


@runtime_checkable
class NumeroBloqueadoRepository(Protocol):
    """Números cuja **mídia** é recusada no inbound (§6k, anti-spam)."""

    async def bloquear(self, bloqueio: NumeroBloqueado) -> NumeroBloqueado:
        """Idempotente: bloquear duas vezes atualiza o motivo, não duplica."""
        ...

    async def desbloquear(self, *, tenant_id: UUID, telefone: str) -> bool: ...

    async def bloqueado(self, *, tenant_id: UUID, telefone: str) -> bool: ...

    async def listar(self, *, tenant_id: UUID) -> list[NumeroBloqueado]: ...


@runtime_checkable
class DocumentoRecebidoRepository(Protocol):
    """Documentos que os responsáveis enviaram, por tenant."""

    async def criar(self, documento: DocumentoRecebido) -> DocumentoRecebido: ...

    async def obter(
        self, *, tenant_id: UUID, documento_id: UUID
    ) -> DocumentoRecebido | None: ...

    async def descartados_por_numero(
        self, *, tenant_id: UUID, desde: datetime, minimo: int
    ) -> list[SugestaoBloqueio]:
        """Números com ao menos ``minimo`` documentos descartados desde ``desde``."""
        ...

    async def por_media_id(
        self, *, tenant_id: UUID, media_id: str
    ) -> DocumentoRecebido | None:
        """Deduplica a reentrega do webhook: a mesma mídia não é baixada duas vezes."""
        ...

    async def listar(
        self,
        *,
        tenant_id: UUID,
        categoria: CategoriaDocumento | None = None,
        status: StatusDocumento | None = None,
        aluno_id: UUID | None = None,
        pagina: int | None = None,
        por_pagina: int | None = None,
    ) -> list[DocumentoRecebido]: ...

    async def contar(
        self,
        *,
        tenant_id: UUID,
        categoria: CategoriaDocumento | None = None,
        status: StatusDocumento | None = None,
        aluno_id: UUID | None = None,
    ) -> int: ...

    async def atualizar(self, documento: DocumentoRecebido) -> DocumentoRecebido: ...

    async def expirados(self, *, limite: int = 500) -> list[DocumentoRecebido]:
        """Documentos cujo prazo de retenção venceu — insumo do expurgo (§6k/LGPD)."""
        ...

    async def remover(self, *, tenant_id: UUID, documento_id: UUID) -> bool: ...
