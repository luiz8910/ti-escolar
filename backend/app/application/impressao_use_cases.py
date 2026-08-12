"""Casos de uso da fila de impressão (solicitações dos professores à secretaria).

A camada de aplicação só orquestra ``SolicitacaoImpressaoRepository`` (e, opcionalmente,
``ProfessorRepository`` para denormalizar o nome do professor). Sem framework/ORM/SDK.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from app.application.documentos_use_cases import ArquivoParaDownload
from app.domain.entities import (
    MIMES_ACEITOS,
    TAMANHO_MAXIMO_DOCUMENTO,
    ArquivoBaixado,
    CotaImpressao,
    LinhaRelatorioImpressao,
    OrigemImpressao,
    Professor,
    RelatorioImpressao,
    SaldoImpressao,
    SolicitacaoImpressao,
    StatusImpressao,
    _now,
)
from app.domain.ports import (
    ArquivoStorage,
    ConversaRepository,
    CotaImpressaoRepository,
    FonteMidia,
    ProfessorRepository,
    SolicitacaoImpressaoRepository,
)
from app.infrastructure.storage import nova_chave


class SolicitarImpressao:
    """Cria uma solicitação de impressão na fila da secretaria.

    Valida os parâmetros (arquivo e nº de cópias) e, quando um ``professor_id`` é
    informado, resolve/valida o professor no tenant para gravar seu nome (exibição).
    """

    def __init__(
        self,
        *,
        solicitacoes: SolicitacaoImpressaoRepository,
        professores: ProfessorRepository | None = None,
    ) -> None:
        self._solicitacoes = solicitacoes
        self._professores = professores

    async def executar(
        self,
        *,
        tenant_id: UUID,
        arquivo_nome: str,
        professor_id: UUID | None = None,
        arquivo_url: str = "",
        copias: int = 1,
        colorido: bool = False,
        frente_verso: bool = False,
        observacao: str = "",
        origem: OrigemImpressao = OrigemImpressao.PORTAL,
        chave_storage: str = "",
        mime: str = "",
        tamanho: int = 0,
        media_id: str = "",
    ) -> SolicitacaoImpressao:
        arquivo_nome = arquivo_nome.strip()
        if not arquivo_nome:
            raise ValueError("Informe o nome do arquivo a imprimir.")
        if copias < 1:
            raise ValueError("O número de cópias deve ser pelo menos 1.")

        professor_nome = ""
        if professor_id is not None and self._professores is not None:
            professor = await self._professores.obter(
                tenant_id=tenant_id, professor_id=professor_id
            )
            if professor is None:
                raise ValueError("Professor não encontrado para o tenant.")
            professor_nome = professor.nome

        return await self._solicitacoes.criar(
            SolicitacaoImpressao(
                tenant_id=tenant_id,
                arquivo_nome=arquivo_nome,
                professor_id=professor_id,
                professor_nome=professor_nome,
                arquivo_url=arquivo_url.strip(),
                copias=copias,
                colorido=colorido,
                frente_verso=frente_verso,
                observacao=observacao.strip(),
                origem=origem,
                chave_storage=chave_storage,
                mime=mime,
                tamanho=tamanho,
                media_id=media_id,
            )
        )


class ConsultarSaldoImpressao:
    """Franquia do professor na competência corrente, já cruzada com o consumo (§B2)."""

    def __init__(
        self,
        *,
        solicitacoes: SolicitacaoImpressaoRepository,
        cotas: CotaImpressaoRepository,
    ) -> None:
        self._solicitacoes = solicitacoes
        self._cotas = cotas

    async def executar(
        self, *, tenant_id: UUID, professor_id: UUID, competencia: str = ""
    ) -> SaldoImpressao:
        competencia = competencia or _now().strftime("%Y-%m")
        cota = await self._cotas.por_professor(
            tenant_id=tenant_id, professor_id=professor_id
        )
        consumido = await self._solicitacoes.consumo_do_professor(
            tenant_id=tenant_id, professor_id=professor_id, competencia=competencia
        )
        return SaldoImpressao(
            competencia=competencia,
            limite_mensal=cota.limite_mensal if cota else 0,
            consumido=consumido,
        )


class ListarFilaImpressao:
    """Lista a fila de impressão do tenant, opcionalmente filtrada por status."""

    def __init__(self, *, solicitacoes: SolicitacaoImpressaoRepository) -> None:
        self._solicitacoes = solicitacoes

    async def executar(
        self, *, tenant_id: UUID, status: StatusImpressao | None = None
    ) -> list[SolicitacaoImpressao]:
        return await self._solicitacoes.listar(tenant_id=tenant_id, status=status)


class ObterSolicitacaoImpressao:
    def __init__(self, *, solicitacoes: SolicitacaoImpressaoRepository) -> None:
        self._solicitacoes = solicitacoes

    async def executar(
        self, *, tenant_id: UUID, solicitacao_id: UUID
    ) -> SolicitacaoImpressao:
        solicitacao = await self._solicitacoes.obter(
            tenant_id=tenant_id, solicitacao_id=solicitacao_id
        )
        if solicitacao is None:
            raise ValueError("Solicitação de impressão não encontrada para o tenant.")
        return solicitacao


class BaixarArquivoDeImpressao:
    """Bytes do arquivo que o professor mandou pelo WhatsApp, para a secretaria imprimir.

    Só existe para o caminho do WhatsApp: no portal o arquivo é referenciado por URL e
    nunca passou por aqui. Como nos documentos recebidos (§6k), não há URL pública — os
    bytes saem por rota autenticada e escopada por tenant.
    """

    def __init__(
        self,
        *,
        solicitacoes: SolicitacaoImpressaoRepository,
        storage: ArquivoStorage,
    ) -> None:
        self._solicitacoes = solicitacoes
        self._storage = storage

    async def executar(
        self, *, tenant_id: UUID, solicitacao_id: UUID
    ) -> ArquivoParaDownload | None:
        solicitacao = await self._solicitacoes.obter(
            tenant_id=tenant_id, solicitacao_id=solicitacao_id
        )
        if solicitacao is None or not solicitacao.tem_arquivo:
            return None
        conteudo = await self._storage.ler(chave=solicitacao.chave_storage)
        if conteudo is None:
            return None
        return ArquivoParaDownload(
            nome=solicitacao.arquivo_nome or f"impressao-{solicitacao.id}",
            mime=solicitacao.mime or "application/octet-stream",
            conteudo=conteudo,
        )


class AtualizarStatusImpressao:
    """A secretaria (ou o professor) muda o status da solicitação na fila."""

    def __init__(self, *, solicitacoes: SolicitacaoImpressaoRepository) -> None:
        self._solicitacoes = solicitacoes

    async def executar(
        self, *, tenant_id: UUID, solicitacao_id: UUID, status: StatusImpressao
    ) -> SolicitacaoImpressao:
        solicitacao = await self._solicitacoes.obter(
            tenant_id=tenant_id, solicitacao_id=solicitacao_id
        )
        if solicitacao is None:
            raise ValueError("Solicitação de impressão não encontrada para o tenant.")
        solicitacao.status = status
        solicitacao.atualizado_em = _now()
        return await self._solicitacoes.atualizar(solicitacao)


class RemoverSolicitacaoImpressao:
    def __init__(self, *, solicitacoes: SolicitacaoImpressaoRepository) -> None:
        self._solicitacoes = solicitacoes

    async def executar(self, *, tenant_id: UUID, solicitacao_id: UUID) -> bool:
        return await self._solicitacoes.remover(
            tenant_id=tenant_id, solicitacao_id=solicitacao_id
        )


# --------------------------------------------------------------------------- #
# B2 · Cota (franquia mensal) e relatório de impressões por professor
# --------------------------------------------------------------------------- #
class DefinirCotaImpressao:
    """Define/atualiza (upsert) a franquia mensal de cópias de um professor.

    ``limite_mensal <= 0`` significa **sem limite**. Valida que o professor pertence
    ao tenant.
    """

    def __init__(
        self,
        *,
        cotas: CotaImpressaoRepository,
        professores: ProfessorRepository,
    ) -> None:
        self._cotas = cotas
        self._professores = professores

    async def executar(
        self, *, tenant_id: UUID, professor_id: UUID, limite_mensal: int
    ) -> CotaImpressao:
        professor = await self._professores.obter(
            tenant_id=tenant_id, professor_id=professor_id
        )
        if professor is None:
            raise ValueError("Professor não encontrado para o tenant.")
        cota = CotaImpressao(
            tenant_id=tenant_id,
            professor_id=professor_id,
            limite_mensal=max(0, limite_mensal),
            atualizado_em=_now(),
        )
        salva = await self._cotas.definir(cota)
        salva.professor_nome = professor.nome
        return salva


class ListarCotasImpressao:
    """Lista as cotas do tenant com o nome do professor resolvido."""

    def __init__(
        self,
        *,
        cotas: CotaImpressaoRepository,
        professores: ProfessorRepository,
    ) -> None:
        self._cotas = cotas
        self._professores = professores

    async def executar(self, *, tenant_id: UUID) -> list[CotaImpressao]:
        cotas = await self._cotas.listar(tenant_id=tenant_id)
        nomes = {
            p.id: p.nome
            for p in await self._professores.listar(tenant_id=tenant_id)
        }
        for cota in cotas:
            cota.professor_nome = nomes.get(cota.professor_id, "")
        return cotas


class RemoverCotaImpressao:
    def __init__(self, *, cotas: CotaImpressaoRepository) -> None:
        self._cotas = cotas

    async def executar(self, *, tenant_id: UUID, professor_id: UUID) -> bool:
        return await self._cotas.remover(tenant_id=tenant_id, professor_id=professor_id)


class RelatorioImpressaoMensal:
    """Relatório de impressões de uma competência (mês ``YYYY-MM``), por professor.

    Soma as **cópias** das solicitações **não canceladas** criadas no mês e cruza com a
    franquia (cota) de cada professor, sinalizando quem excedeu ("bateu a meta"). Inclui
    professores com cota definida mesmo sem solicitações no mês.
    """

    def __init__(
        self,
        *,
        solicitacoes: SolicitacaoImpressaoRepository,
        cotas: CotaImpressaoRepository,
        professores: ProfessorRepository,
    ) -> None:
        self._solicitacoes = solicitacoes
        self._cotas = cotas
        self._professores = professores

    async def executar(
        self, *, tenant_id: UUID, competencia: str
    ) -> RelatorioImpressao:
        todas = await self._solicitacoes.listar(tenant_id=tenant_id)
        cotas = {
            c.professor_id: c.limite_mensal
            for c in await self._cotas.listar(tenant_id=tenant_id)
        }
        nomes = {
            p.id: p.nome
            for p in await self._professores.listar(tenant_id=tenant_id)
        }

        # Agrega consumo por professor no mês (ignora canceladas).
        consumo: dict[UUID | None, dict] = {}
        for s in todas:
            if s.criado_em.strftime("%Y-%m") != competencia:
                continue
            if s.status == StatusImpressao.CANCELADA:
                continue
            item = consumo.setdefault(
                s.professor_id,
                {"solicitacoes": 0, "copias": 0, "nome": s.professor_nome},
            )
            item["solicitacoes"] += 1
            item["copias"] += s.copias
            if s.professor_nome:
                item["nome"] = s.professor_nome

        # Professores com cota, ainda que sem consumo no mês.
        professores_relevantes = set(consumo.keys()) | set(cotas.keys())

        linhas: list[LinhaRelatorioImpressao] = []
        for professor_id in professores_relevantes:
            dados = consumo.get(professor_id, {"solicitacoes": 0, "copias": 0, "nome": ""})
            nome = nomes.get(professor_id) or dados["nome"] or "Sem professor"
            linhas.append(
                LinhaRelatorioImpressao(
                    professor_id=professor_id,
                    professor_nome=nome,
                    total_solicitacoes=dados["solicitacoes"],
                    total_copias=dados["copias"],
                    limite_mensal=cotas.get(professor_id, 0),
                )
            )
        linhas.sort(key=lambda linha: linha.professor_nome.lower())
        return RelatorioImpressao(
            tenant_id=tenant_id, competencia=competencia, linhas=linhas
        )


# --------------------------------------------------------------------------- #
# Impressão pelo WhatsApp — o professor manda o arquivo para o número da escola
# --------------------------------------------------------------------------- #
# A dor: o professor já usa o WhatsApp o dia inteiro e o portal exige abrir o navegador,
# lembrar a senha e preencher um formulário para mandar a mesma lista de chamada. Como o
# número dele **está cadastrado**, o inbound sabe quem é — e quem é professor não está
# pedindo suporte à secretaria, está mandando material para imprimir.

# Quantidade: aceita "30 cópias", "30 folhas", "x30", "30x" e a legenda que é só o número.
_RE_COPIAS_COM_UNIDADE = re.compile(
    r"(\d{1,4})\s*(?:c[óo]pias?|c[óo]pia|folhas?|vias?|impress[õo]es|impress[ãa]o)",
    re.IGNORECASE,
)
_RE_COPIAS_X = re.compile(r"(?:^|\s)(?:x\s*(\d{1,4})|(\d{1,4})\s*x)(?:\s|$)", re.IGNORECASE)
_RE_SO_NUMERO = re.compile(r"^\s*(\d{1,4})\s*$")

_PISTAS_COR = ("colorid", "à cor", "a cor", "em cor", "cor)", "colorir")
_PISTAS_FRENTE_VERSO = ("frente e verso", "frente-e-verso", "frente/verso", "duplex", "f/v")

# Teto do palpite. Uma legenda com "2026" é ano, não tiragem — e mandar 2.026 folhas para
# a impressora por causa de um palpite é o tipo de erro que a escola paga em papel.
COPIAS_MAXIMAS_INFERIDAS = 500


@dataclass(frozen=True)
class ParametrosDeImpressao:
    """O que se conseguiu ler da legenda do arquivo."""

    copias: int = 1
    colorido: bool = False
    frente_verso: bool = False
    # Falso quando o número de cópias é o default, e não algo que o professor escreveu —
    # é o que a confirmação avisa, para ele corrigir antes de a secretaria imprimir.
    copias_informadas: bool = False

    def descrever(self) -> str:
        partes = [f"{self.copias} cópia" + ("s" if self.copias > 1 else "")]
        partes.append("colorido" if self.colorido else "preto e branco")
        if self.frente_verso:
            partes.append("frente e verso")
        return " · ".join(partes)


def interpretar_legenda(texto: str) -> ParametrosDeImpressao:
    """Lê cópias, cor e frente-e-verso da legenda — heurística, sem LLM.

    Mesma escolha de ``sugerir_categoria`` nos documentos recebidos (§6k): chamar o modelo
    para adivinhar o que cabe numa expressão regular não paga a latência nem o custo, e o
    palpite errado é corrigido pela secretaria na fila. O que **não** se faz é inventar
    quantidade: sem número explícito o pedido nasce com 1 cópia e a confirmação diz isso
    em voz alta.
    """
    bruto = (texto or "").strip()
    baixo = bruto.lower()

    copias, informadas = 1, False
    for regex in (_RE_COPIAS_COM_UNIDADE, _RE_COPIAS_X, _RE_SO_NUMERO):
        achado = regex.search(bruto)
        if not achado:
            continue
        valor = next((int(g) for g in achado.groups() if g), 0)
        if 1 <= valor <= COPIAS_MAXIMAS_INFERIDAS:
            copias, informadas = valor, True
            break

    return ParametrosDeImpressao(
        copias=copias,
        colorido=any(p in baixo for p in _PISTAS_COR),
        frente_verso=any(p in baixo for p in _PISTAS_FRENTE_VERSO),
        copias_informadas=informadas,
    )


def _tamanho_legivel(tamanho: int) -> str:
    if tamanho < 1024:
        return f"{tamanho} B"
    if tamanho < 1024 * 1024:
        return f"{tamanho / 1024:.0f} KB"
    return f"{tamanho / (1024 * 1024):.1f} MB"


class ReceberImpressaoDoProfessor:
    """Arquivo enviado por um professor ao número da escola vira pedido na fila.

    Espelha ``ReceberMidiaDoResponsavel`` (§6k) de propósito — a mecânica de baixar,
    guardar e confirmar é a mesma —, mas o destino é outro: aqui não nasce um
    ``DocumentoRecebido`` para a secretaria conferir, e sim uma ``SolicitacaoImpressao``
    para ela imprimir, já debitada da franquia mensal do professor (§B2).

    A confirmação com o **saldo** é o ponto da feature: hoje o professor descobre que
    estourou a cota no fim do mês, quando o relatório sai e não há mais o que fazer.
    """

    def __init__(
        self,
        *,
        fonte: FonteMidia,
        storage: ArquivoStorage,
        solicitacoes: SolicitacaoImpressaoRepository,
        saldo: ConsultarSaldoImpressao,
        conversas: ConversaRepository,
    ) -> None:
        self._fonte = fonte
        self._storage = storage
        self._solicitacoes = solicitacoes
        self._saldo = saldo
        self._conversas = conversas

    async def executar(
        self,
        *,
        tenant_id: UUID,
        professor: Professor,
        contato: str,
        media_id: str,
        legenda: str = "",
        nome_arquivo: str = "",
    ) -> str:
        """Devolve o texto a mandar de volta ao professor (``""`` = não responder)."""
        conversa = await self._conversas.obter_ou_criar(tenant_id=tenant_id, contato=contato)
        rotulo = (nome_arquivo or "").strip() or "arquivo"
        await self._conversas.adicionar_mensagem(
            conversa_id=conversa.id,
            autor="usuario",
            texto=f"🖨️ {rotulo}" + (f"\n{legenda}" if legenda.strip() else ""),
        )

        # Dedupe antes do download: a reentrega do webhook não pode virar um segundo
        # pedido na fila — a secretaria imprimiria duas vezes e a franquia seria debitada
        # em dobro.
        if media_id:
            existente = await self._solicitacoes.por_media_id(
                tenant_id=tenant_id, media_id=media_id
            )
            if existente is not None:
                return ""

        arquivo = await self._fonte.baixar(media_id)
        if arquivo is None:
            return await self._responder(
                conversa.id,
                "Não consegui abrir o arquivo que você enviou. Reenvie como **PDF**, "
                "**foto** ou **documento do Word**, por gentileza.",
            )
        if arquivo.mime not in MIMES_ACEITOS:
            return await self._responder(
                conversa.id,
                "Esse formato eu não consigo mandar para a fila de impressão. "
                "Envie um PDF, uma foto ou um documento do Word.",
            )
        if arquivo.tamanho > TAMANHO_MAXIMO_DOCUMENTO or not arquivo.conteudo:
            return await self._responder(
                conversa.id,
                f"O arquivo passou do limite de {_tamanho_legivel(TAMANHO_MAXIMO_DOCUMENTO)}. "
                "Divida em partes e reenvie, por favor.",
            )

        parametros = interpretar_legenda(legenda)
        chave = nova_chave()
        await self._storage.guardar(
            chave=chave, conteudo=arquivo.conteudo, mime=arquivo.mime
        )

        await self._solicitacoes.criar(
            SolicitacaoImpressao(
                tenant_id=tenant_id,
                arquivo_nome=(arquivo.nome or nome_arquivo or "").strip() or "arquivo",
                professor_id=professor.id,
                professor_nome=professor.nome,
                copias=parametros.copias,
                colorido=parametros.colorido,
                frente_verso=parametros.frente_verso,
                observacao=legenda.strip(),
                origem=OrigemImpressao.WHATSAPP,
                chave_storage=chave,
                mime=arquivo.mime,
                tamanho=arquivo.tamanho,
                media_id=media_id,
            )
        )

        # Saldo apurado **depois** de gravar: é o que faz a resposta já refletir o débito
        # deste envio, em vez de mostrar o saldo anterior e confundir quem está no limite.
        saldo = await self._saldo.executar(tenant_id=tenant_id, professor_id=professor.id)
        return await self._responder(
            conversa.id, self._confirmar(arquivo, parametros, saldo)
        )

    async def orientar(
        self, *, tenant_id: UUID, professor: Professor, contato: str, texto: str
    ) -> str:
        """Resposta a um professor que mandou **texto** neste canal.

        O canal do professor com a escola é o portal (mural, canal interno §A2). Aqui a
        conversa não vai para o assistente dos responsáveis: ele responderia sobre
        matrícula e horário de secretaria a quem trabalha na escola — e ainda queimaria
        LLM para isso.
        """
        conversa = await self._conversas.obter_ou_criar(tenant_id=tenant_id, contato=contato)
        await self._conversas.adicionar_mensagem(
            conversa_id=conversa.id, autor="usuario", texto=texto
        )
        return await self._responder(
            conversa.id,
            f"Olá, {professor.nome.split()[0]}! Este número recebe os seus arquivos para "
            "impressão: envie o PDF ou a foto e, na legenda, o número de cópias "
            "(ex.: *30 cópias, frente e verso*).\n\n"
            "Para recados, pedidos à secretaria e o mural, use o portal do professor.",
        )

    def _confirmar(
        self, arquivo: ArquivoBaixado, parametros: ParametrosDeImpressao, saldo: SaldoImpressao
    ) -> str:
        linhas = [
            f"Recebi *{arquivo.nome or 'o arquivo'}* ({_tamanho_legivel(arquivo.tamanho)}) "
            "e coloquei na fila de impressão da secretaria.",
            f"• {parametros.descrever()}",
        ]
        if not parametros.copias_informadas:
            linhas.append(
                "Como você não indicou a quantidade, registrei *1 cópia*. Se forem mais, "
                "reenvie escrevendo a quantidade na legenda."
            )
        if saldo.ilimitado:
            linhas.append("Sua franquia de impressão não tem limite definido.")
        elif saldo.excedeu:
            linhas.append(
                f"⚠️ Atenção: você já passou da franquia do mês "
                f"({saldo.consumido} de {saldo.limite_mensal} cópias). "
                "A secretaria vai avaliar o pedido."
            )
        else:
            linhas.append(
                f"Franquia do mês: {saldo.consumido} de {saldo.limite_mensal} cópias "
                f"({saldo.restante} restantes)."
            )
        return "\n".join(linhas)

    async def _responder(self, conversa_id: UUID, texto: str) -> str:
        await self._conversas.adicionar_mensagem(
            conversa_id=conversa_id, autor="bot", texto=texto
        )
        return texto
