"""Onboarding do WhatsApp de uma escola — do chip ao primeiro atendimento (§9e.3).

Até aqui, pôr uma escola no ar era um roteiro de documento: seis passos em três telas do
console da Meta, dois deles **silenciosos** (app não publicado, WABA não inscrita no app),
mais um `INSERT` do `phone_number_id` no painel. Roteiro que a gente segue uma vez por
escola é roteiro que a gente erra na segunda — e o erro aqui não aparece: o webhook
simplesmente emudece.

Este módulo transforma o roteiro em **estado consultável e passos executáveis**:

- ``DiagnosticarWhatsAppDaEscola`` responde "o que falta para esta escola atender?",
  perguntando à Meta em vez de acreditar no banco;
- ``CadastrarNumeroDaEscola`` → ``PedirCodigoDeVerificacao`` →
  ``ConfirmarCodigoDeVerificacao`` → ``InscreverNumeroNaCloudApi`` são os quatro passos do
  provisionamento, na única ordem em que a Meta os aceita;
- ``ConcluirOnboardingDaEscola`` fecha os dois passos que ninguém lembra: inscrever a
  conta no app e replicar os templates globais nela.

**O humano no meio é de propósito.** Entre pedir o código e confirmá-lo há um chip num
aparelho e alguém lendo um SMS. Não existe API para isso e fingir que existe produziria um
"provisione tudo" que trava. O que se automatiza é todo o resto — que é a maior parte.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from app.domain.entities import (
    EtapaOnboarding,
    NumeroNaMeta,
    StatusTemplate,
    Tenant,
    Usuario,
    Waba,
)
from app.domain.ports import (
    CatalogoTemplates,
    GestorDeNumeros,
    TemplateRepository,
    TenantRepository,
    WabaRepository,
)

logger = logging.getLogger("onboarding")


class EscolaNaoEncontrada(LookupError):
    pass


class PermissaoOnboardingNegada(PermissionError):
    pass


class OnboardingRecusado(RuntimeError):
    """Pré-condição do produto não satisfeita — antes de gastar uma chamada à Meta."""


def _exige_super_admin(solicitante: Usuario) -> None:
    """Onboarding é operação de plataforma, não de escola.

    Quem cadastra número na WABA mexe num ativo **compartilhado**: o teto de números é do
    portfólio (§9e.3), então um cadastro a mais consome a vaga da próxima escola. E o
    admin de uma escola não tem por que poder olhar a conta onde as outras vivem.
    """
    if not solicitante.eh_super_admin:
        raise PermissaoOnboardingNegada(
            "Apenas o super admin cadastra números do WhatsApp na Meta."
        )


# --------------------------------------------------------------------------- #
# Diagnóstico
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PassoOnboarding:
    """Um passo do roteiro, com o veredito e o que fazer a seguir.

    ``concluido`` é o que a tela pinta de verde; ``acao`` é o que ela oferece como botão.
    ``detalhe`` existe porque "faltando" sem motivo é o mesmo que erro sem mensagem — e
    metade dos passos aqui falha por uma razão que só a Meta sabe.
    """

    chave: str
    titulo: str
    concluido: bool
    detalhe: str = ""
    # Nome do passo executável que resolve isto, quando existe um. Vazio = resolve-se
    # fora da aplicação (comprar chip, publicar app, adicionar cartão).
    acao: str = ""
    # Passo que depende de gente/console e não de um clique nosso.
    manual: bool = False


@dataclass(frozen=True)
class DiagnosticoWhatsApp:
    tenant_id: UUID
    escola: str
    # Canal **efetivo** do processo, não a env: sem token o produto inteiro fala pelo demo
    # e todo o resto deste diagnóstico seria teatro.
    canal: str
    conta: Waba | None = None
    numero: NumeroNaMeta | None = None
    passos: tuple[PassoOnboarding, ...] = ()

    @property
    def pronta(self) -> bool:
        return all(p.concluido for p in self.passos)

    @property
    def pendencias(self) -> list[PassoOnboarding]:
        return [p for p in self.passos if not p.concluido]


class DiagnosticarWhatsAppDaEscola:
    """Responde "o que falta para esta escola atender no WhatsApp?".

    **Pergunta à Meta, não ao banco.** O banco sabe o id que digitamos; só a Meta sabe se
    o número está inscrito, se o nome de exibição passou na revisão e se a qualidade caiu.
    O modo de falha que este caso de uso existe para evitar é o painel afirmar "pronta"
    sobre uma escola cujo número a Meta pausou ontem.

    Cada passo silencioso do go-live vira uma linha aqui — é o inventário do que já custou
    um dia de depuração: número não inscrito (§2), id não cadastrado (§6.2), conta não
    inscrita no app (§5.1), catálogo sem template aprovado (§7).
    """

    def __init__(
        self,
        *,
        tenants: TenantRepository,
        wabas: WabaRepository,
        numeros: GestorDeNumeros,
        templates: TemplateRepository,
        canal: str,
    ) -> None:
        self._tenants = tenants
        self._wabas = wabas
        self._numeros = numeros
        self._templates = templates
        self._canal = canal

    async def executar(
        self, *, solicitante: Usuario, tenant_id: UUID
    ) -> DiagnosticoWhatsApp:
        _exige_super_admin(solicitante)
        escola = await self._tenants.obter(tenant_id)
        if escola is None:
            raise EscolaNaoEncontrada("Escola não encontrada.")

        conta = await self._wabas.obter(escola.waba_id) if escola.waba_id else None
        numero = (
            await self._numeros.descrever(phone_number_id=escola.meta_phone_number_id)
            if escola.meta_phone_number_id
            else None
        )
        passos = [
            self._passo_canal(),
            self._passo_conta(conta),
            self._passo_numero(escola, numero),
            self._passo_registro(escola, numero),
            self._passo_nome(numero),
            await self._passo_templates(escola, conta),
        ]
        return DiagnosticoWhatsApp(
            tenant_id=tenant_id,
            escola=escola.nome,
            canal=self._canal,
            conta=conta,
            numero=numero,
            passos=tuple(passos),
        )

    # ------------------------------------------------------------------ os passos --
    def _passo_canal(self) -> PassoOnboarding:
        return PassoOnboarding(
            chave="canal",
            titulo="Canal da Meta ligado no servidor",
            concluido=self._canal == "meta",
            detalhe=(
                ""
                if self._canal == "meta"
                else "O processo está no canal demo: falta META_ACCESS_TOKEN ou "
                "MESSAGE_CHANNEL=meta. Nada abaixo pode ser conferido contra a Meta, e "
                "nenhuma mensagem chega ao responsável."
            ),
            manual=True,
        )

    def _passo_conta(self, conta: Waba | None) -> PassoOnboarding:
        if conta is None:
            return PassoOnboarding(
                chave="conta",
                titulo="Conta do WhatsApp Business (WABA) escolhida",
                concluido=False,
                detalhe=(
                    "A escola não está em nenhuma conta. Sem isso não há onde criar nem "
                    "conferir template, e o disparo por template é recusado."
                ),
                acao="escolher_conta",
            )
        if not conta.meta_waba_id:
            return PassoOnboarding(
                chave="conta",
                titulo="Conta do WhatsApp Business (WABA) escolhida",
                concluido=False,
                detalhe=(
                    f"A conta {conta.nome!r} está sem o id da Meta. Preencha-o em "
                    "Administração → Contas WhatsApp, ou espere o primeiro evento do "
                    "webhook reconhecê-lo."
                ),
                acao="escolher_conta",
            )
        return PassoOnboarding(
            chave="conta",
            titulo="Conta do WhatsApp Business (WABA) escolhida",
            concluido=True,
            detalhe=f"{conta.nome} ({conta.meta_waba_id})",
        )

    def _passo_numero(
        self, escola: Tenant, numero: NumeroNaMeta | None
    ) -> PassoOnboarding:
        if not escola.meta_phone_number_id:
            return PassoOnboarding(
                chave="numero",
                titulo="Número cadastrado na Meta e vinculado à escola",
                concluido=False,
                detalhe=(
                    "Sem o phone_number_id a escola **não recebe mensagem**: o inbound "
                    "dela é descartado, porque não há para quem rotear."
                ),
                acao="cadastrar_numero",
            )
        if numero is None:
            return PassoOnboarding(
                chave="numero",
                titulo="Número cadastrado na Meta e vinculado à escola",
                concluido=False,
                detalhe=(
                    f"O id {escola.meta_phone_number_id} está gravado aqui, mas a Meta não "
                    "o reconhece (ou o token não o enxerga). Confira se ele foi copiado "
                    "da conta certa."
                ),
            )
        return PassoOnboarding(
            chave="numero",
            titulo="Número cadastrado na Meta e vinculado à escola",
            concluido=True,
            detalhe=f"{numero.numero_exibicao or escola.whatsapp_numero} "
            f"({numero.phone_number_id})",
        )

    def _passo_registro(
        self, escola: Tenant, numero: NumeroNaMeta | None
    ) -> PassoOnboarding:
        if numero is None:
            return PassoOnboarding(
                chave="registro",
                titulo="Número verificado e inscrito na Cloud API",
                concluido=False,
                detalhe="Depende do passo anterior.",
            )
        if numero.etapa is EtapaOnboarding.NAO_VERIFICADO:
            return PassoOnboarding(
                chave="registro",
                titulo="Número verificado e inscrito na Cloud API",
                concluido=False,
                detalhe=(
                    "Falta o código de 6 dígitos. Peça-o por SMS ou ligação e digite o "
                    "que chegar no chip. Depois de duas tentativas falhas, **espere** "
                    "algumas horas: insistir trava a verificação."
                ),
                acao="pedir_codigo",
            )
        if numero.etapa is EtapaOnboarding.NAO_REGISTRADO:
            return PassoOnboarding(
                chave="registro",
                titulo="Número verificado e inscrito na Cloud API",
                concluido=False,
                detalhe=(
                    "Verificado, mas ainda mudo — **verificar não é registrar**. Falta "
                    "inscrevê-lo com um PIN de 6 dígitos, que a Meta exigirá de novo no "
                    "futuro e não exibe outra vez."
                ),
                acao="registrar_numero",
            )
        if numero.etapa is EtapaOnboarding.REGISTRADO:
            return PassoOnboarding(
                chave="registro",
                titulo="Número verificado e inscrito na Cloud API",
                concluido=True,
                detalhe=f"Inscrito · qualidade {numero.qualidade or 'desconhecida'}",
            )
        return PassoOnboarding(
            chave="registro",
            titulo="Número verificado e inscrito na Cloud API",
            concluido=False,
            detalhe=(
                f"A Meta respondeu um estado que não sabemos ler ({numero.bruto}). "
                "Confira no Gerenciador do WhatsApp antes de disparar."
            ),
        )

    def _passo_nome(self, numero: NumeroNaMeta | None) -> PassoOnboarding:
        """Nome de exibição — o caminho crítico do prazo, e o passo que ninguém dispara cedo."""
        status = (numero.status_nome if numero else "").upper()
        aprovado = status in {"APPROVED", "AVAILABLE_WITHOUT_REVIEW"}
        return PassoOnboarding(
            chave="nome",
            titulo="Nome de exibição aprovado pela Meta",
            concluido=aprovado,
            detalhe=(
                f"{numero.nome_exibicao} ({status})"
                if numero and aprovado
                else "A revisão do nome é assíncrona e é o passo mais demorado do "
                f"onboarding. Estado atual: {status or 'desconhecido'}."
            ),
            manual=True,
        )

    async def _passo_templates(
        self, escola: Tenant, conta: Waba | None
    ) -> PassoOnboarding:
        """Sem template aprovado **nesta conta**, a escola só responde dentro das 24h.

        Aprovação é por conta (§9a-ter): um global aprovado na conta A não existe na B.
        Por isso a pergunta certa é ``aprovado_em(conta)``, e não "o template existe?".
        """
        if conta is None:
            return PassoOnboarding(
                chave="templates",
                titulo="Ao menos um template aprovado na conta da escola",
                concluido=False,
                detalhe="Depende da conta.",
            )
        aprovados = [
            t
            for t in await self._templates.listar(tenant_id=escola.id)
            if t.status_em(conta.id) is StatusTemplate.APROVADO
        ]
        return PassoOnboarding(
            chave="templates",
            titulo="Ao menos um template aprovado na conta da escola",
            concluido=bool(aprovados),
            detalhe=(
                ", ".join(t.nome for t in aprovados[:5])
                if aprovados
                else "Fora da janela de 24h só se envia template aprovado. Replique os "
                "globais nesta conta e acompanhe a revisão."
            ),
            acao="" if aprovados else "replicar_templates",
        )


# --------------------------------------------------------------------------- #
# Os quatro passos do provisionamento
# --------------------------------------------------------------------------- #
class _PassoDaMeta:
    """Base dos passos: carrega escola + conta e valida o que a Meta exigiria depois."""

    def __init__(
        self,
        *,
        tenants: TenantRepository,
        wabas: WabaRepository,
        numeros: GestorDeNumeros,
    ) -> None:
        self._tenants = tenants
        self._wabas = wabas
        self._numeros = numeros

    async def _escola(self, tenant_id: UUID) -> Tenant:
        escola = await self._tenants.obter(tenant_id)
        if escola is None:
            raise EscolaNaoEncontrada("Escola não encontrada.")
        return escola

    async def _conta_de(self, escola: Tenant) -> Waba:
        if escola.waba_id is None:
            raise OnboardingRecusado(
                f"A escola {escola.nome!r} não está em nenhuma conta do WhatsApp "
                "Business. Escolha a conta antes de cadastrar o número — é ela que diz "
                "onde o número vai morar."
            )
        conta = await self._wabas.obter(escola.waba_id)
        if conta is None:
            raise OnboardingRecusado("A conta do WhatsApp desta escola não existe mais.")
        if not conta.meta_waba_id:
            raise OnboardingRecusado(
                f"A conta {conta.nome!r} está sem o id da Meta. Preencha-o em "
                "Administração → Contas WhatsApp."
            )
        return conta

    def _numero_da(self, escola: Tenant) -> str:
        if not escola.meta_phone_number_id:
            raise OnboardingRecusado(
                f"A escola {escola.nome!r} ainda não tem número cadastrado na Meta. "
                "Cadastre-o primeiro."
            )
        return escola.meta_phone_number_id


class CadastrarNumeroDaEscola(_PassoDaMeta):
    """Cria o número na WABA da escola e **grava o id no tenant na mesma operação**.

    Os dois juntos não é conveniência: é o passo que separava um número existente na Meta
    de uma escola que recebe mensagem. Cadastrar lá e esquecer de colar o
    ``phone_number_id`` aqui produz o pior estado — número conectado, inbound descartado
    em silêncio porque não há tenant a quem entregar.
    """

    async def executar(
        self,
        *,
        solicitante: Usuario,
        tenant_id: UUID,
        numero_e164: str,
        nome_exibicao: str = "",
    ) -> NumeroNaMeta:
        _exige_super_admin(solicitante)
        from app.infrastructure.channel.meta_numeros import separar_e164

        escola = await self._escola(tenant_id)
        conta = await self._conta_de(escola)
        if escola.meta_phone_number_id:
            raise OnboardingRecusado(
                f"A escola {escola.nome!r} já tem o número {escola.whatsapp_numero or ''} "
                f"(id {escola.meta_phone_number_id}). Remova-o antes de cadastrar outro — "
                "trocar o número custa a identidade do canal para os pais."
            )
        codigo_pais, numero = separar_e164(numero_e164)
        # O nome de exibição é o da escola por padrão: é o que os pais reconhecem, e a
        # revisão da Meta recusa nome genérico.
        nome = (nome_exibicao or escola.nome).strip()

        criado = await self._numeros.adicionar(
            meta_waba_id=conta.meta_waba_id,
            codigo_pais=codigo_pais,
            numero=numero,
            nome_exibicao=nome,
        )
        escola.meta_phone_number_id = criado.phone_number_id
        escola.whatsapp_numero = _e164(codigo_pais, numero)
        await self._tenants.atualizar(escola)
        logger.warning(
            "Número %s cadastrado para a escola %s (id %s).",
            escola.whatsapp_numero,
            escola.nome,
            criado.phone_number_id,
        )
        return criado


class PedirCodigoDeVerificacao(_PassoDaMeta):
    """Dispara o código de 6 dígitos para o chip — que está com a gente, não com a escola.

    **Não insista.** A Meta trava a verificação por horas depois de alguns reenvios
    falhos, e é a tentativa seguinte que se perde. Duas falhas ⇒ esperar, não trocar de
    método nem de chip (docs/producao-whatsapp.md §2.1).
    """

    async def executar(
        self,
        *,
        solicitante: Usuario,
        tenant_id: UUID,
        metodo: str = "SMS",
        idioma: str = "pt_BR",
    ) -> NumeroNaMeta | None:
        _exige_super_admin(solicitante)
        escola = await self._escola(tenant_id)
        numero_id = self._numero_da(escola)
        await self._numeros.solicitar_codigo(
            phone_number_id=numero_id, metodo=metodo, idioma=idioma
        )
        return await self._numeros.descrever(phone_number_id=numero_id)


class ConfirmarCodigoDeVerificacao(_PassoDaMeta):
    """Confere o código. Depois disto o número está verificado — e ainda mudo."""

    async def executar(
        self, *, solicitante: Usuario, tenant_id: UUID, codigo: str
    ) -> NumeroNaMeta:
        _exige_super_admin(solicitante)
        escola = await self._escola(tenant_id)
        return await self._numeros.confirmar_codigo(
            phone_number_id=self._numero_da(escola), codigo=codigo
        )


class InscreverNumeroNaCloudApi(_PassoDaMeta):
    """``POST /register`` com o PIN — é aqui que o número passa a falar.

    O PIN **não é persistido**. A Meta o exige de novo para reinscrever o número (troca de
    conta, incidente), e o lugar disso é o gerenciador de senhas de quem opera: guardar
    num banco multi-tenant o segredo que reassume o canal de todas as escolas trocaria um
    passo manual por um alvo.
    """

    async def executar(
        self, *, solicitante: Usuario, tenant_id: UUID, pin: str
    ) -> NumeroNaMeta:
        _exige_super_admin(solicitante)
        escola = await self._escola(tenant_id)
        return await self._numeros.registrar(
            phone_number_id=self._numero_da(escola), pin=pin
        )


@dataclass
class ResultadoConclusao:
    """O que os dois passos esquecíveis fizeram — para a tela contar, não adivinhar."""

    conta_inscrita_no_app: bool = False
    templates_submetidos: int = 0
    templates_ja_existiam: int = 0
    templates_com_falha: int = 0
    perfil_atualizado: bool = False
    avisos: list[str] = field(default_factory=list)


class ConcluirOnboardingDaEscola(_PassoDaMeta):
    """Fecha os dois passos que não têm tela no console e por isso somem do roteiro.

    1. **Inscrever a conta no app** (``POST /{waba_id}/subscribed_apps``). Sem isto a Meta
       não envia evento nenhum e não reporta erro em lugar nenhum: console verde, número
       conectado, webhook mudo (§5.1). É por WABA, então toda conta nova precisa dele.
    2. **Replicar os templates globais** na conta. Aprovação é por conta: a escola cuja
       conta não tem o catálogo nasce sem poder disparar nada fora da janela de 24h.

    E, de brinde, o **perfil comercial** do número — que é o que distingue, na tela do
    responsável, um número institucional de um desconhecido pedindo dados do filho.

    Idempotente por natureza: as duas chamadas são seguras de repetir, e é isso que
    permite oferecê-la como um botão "conferir e completar" em vez de um passo de uma vez só.
    """

    def __init__(
        self,
        *,
        tenants: TenantRepository,
        wabas: WabaRepository,
        numeros: GestorDeNumeros,
        templates: TemplateRepository,
        catalogo: CatalogoTemplates,
    ) -> None:
        super().__init__(tenants=tenants, wabas=wabas, numeros=numeros)
        self._templates = templates
        self._catalogo = catalogo

    async def executar(
        self, *, solicitante: Usuario, tenant_id: UUID, atualizar_perfil: bool = True
    ) -> ResultadoConclusao:
        _exige_super_admin(solicitante)
        escola = await self._escola(tenant_id)
        conta = await self._conta_de(escola)
        resultado = ResultadoConclusao()

        try:
            resultado.conta_inscrita_no_app = await self._numeros.inscrever_no_app(
                meta_waba_id=conta.meta_waba_id
            )
        except Exception as erro:  # noqa: BLE001 — um passo falho não anula os outros
            resultado.avisos.append(f"Inscrição da conta no app: {erro}")

        # A replicação é do catálogo inteiro, não desta escola: templates globais valem
        # para todas, e a conta é que precisa tê-los.
        from app.application.templates_use_cases import ReplicarTemplates

        try:
            replicacao = await ReplicarTemplates(
                templates=self._templates, catalogo=self._catalogo, wabas=self._wabas
            ).executar()
            resultado.templates_submetidos = replicacao.submetidos
            resultado.templates_ja_existiam = replicacao.ja_existiam
            resultado.templates_com_falha = replicacao.falhas
        except Exception as erro:  # noqa: BLE001
            resultado.avisos.append(f"Replicação de templates: {erro}")

        if atualizar_perfil and escola.meta_phone_number_id:
            try:
                resultado.perfil_atualizado = await self._numeros.definir_perfil(
                    phone_number_id=escola.meta_phone_number_id,
                    descricao=(
                        f"Canal oficial de comunicação da {escola.nome} com os "
                        "responsáveis."
                    ),
                    setor="EDU",
                )
            except Exception as erro:  # noqa: BLE001 — cosmético, nunca bloqueante
                resultado.avisos.append(f"Perfil comercial: {erro}")

        logger.warning(
            "Onboarding concluído para %s: app=%s templates=%d/%d falhas=%d",
            escola.nome,
            resultado.conta_inscrita_no_app,
            resultado.templates_submetidos,
            resultado.templates_submetidos + resultado.templates_ja_existiam,
            resultado.templates_com_falha,
        )
        return resultado


class DesvincularNumeroDaEscola(_PassoDaMeta):
    """Solta o ``phone_number_id`` do tenant — **sem tocar na Meta**.

    Existe para o caso em que o id foi cadastrado na escola errada, que é o erro que o
    teste de fumaça cruzado (§9, passo 6) procura. Não desregistra nem apaga o número: um
    ``deregister`` disparado por engano derruba o canal de uma escola em produção, e essa
    é uma decisão para o console da Meta, com a fricção que ele impõe.
    """

    async def executar(self, *, solicitante: Usuario, tenant_id: UUID) -> Tenant:
        _exige_super_admin(solicitante)
        escola = await self._escola(tenant_id)
        anterior = escola.meta_phone_number_id
        escola.meta_phone_number_id = ""
        atualizada = await self._tenants.atualizar(escola)
        logger.warning(
            "Número %s desvinculado da escola %s (continua existindo na Meta).",
            anterior,
            escola.nome,
        )
        return atualizada


def _e164(codigo_pais: str, numero: str) -> str:
    return f"+{codigo_pais}{numero}"
