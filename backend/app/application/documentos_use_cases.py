"""Documentos que os responsáveis enviam pelo WhatsApp (§6k).

A dor é de época de matrícula, e ela é concreta: hoje a foto do atestado, do RG e do
comprovante de endereço chega **no celular pessoal de alguém da secretaria**. O documento
vira responsabilidade daquela pessoa — se ela falta, tira férias ou troca de aparelho, o
documento some, e a escola não tem nem como saber que ele existiu.

Aqui o arquivo passa a pertencer à escola: entra pela mesma conversa que o originou, fica
no tenant, e a secretaria classifica, vincula a um aluno e marca como processado.

**Este módulo lida com dado sensível de criança** (LGPD arts. 11 e 14): atestado é dado de
saúde. Três decisões vêm daí e não são negociáveis —

- **prazo de retenção desde o nascimento** (`expira_em`): sem prazo, um repositório de
  atestados de menores vira passivo permanente;
- **nada de URL pública**: o download passa pela API autenticada e escopada por tenant,
  nunca por link assinado eterno;
- **todo download é auditado**: quem baixou o quê, quando (§13).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.application.paginacao import (
    POR_PAGINA_PADRAO,
    Pagina,
    normalizar_paginacao,
)
from app.domain.entities import (
    DESCARTES_PARA_SUGERIR_BLOQUEIO,
    JANELA_DESCARTES_DIAS,
    MIMES_ACEITOS,
    TAMANHO_MAXIMO_DOCUMENTO,
    ArquivoBaixado,
    CategoriaDocumento,
    DocumentoLido,
    DocumentoRecebido,
    NumeroBloqueado,
    StatusDocumento,
    SugestaoBloqueio,
)
from app.application.atendimento_humano_use_cases import MesaDeAtendimento
from app.domain.ports import (
    AlunoRepository,
    ArquivoStorage,
    ContatoRepository,
    ConversaRepository,
    DocumentoRecebidoRepository,
    FonteMidia,
    LeitorDocumento,
    NumeroBloqueadoRepository,
)
from app.infrastructure.storage import nova_chave

logger = logging.getLogger("documentos.recebidos")

# Retenção padrão dos arquivos recebidos. Um ano cobre o ciclo letivo inteiro (a matrícula
# de fevereiro ainda é consultável em dezembro) sem virar arquivo morto permanente.
RETENCAO_PADRAO_DIAS = 365

# Palavras que sugerem a finalidade a partir da legenda que o responsável escreveu. É
# **palpite**, exibido como sugestão no painel — quem confirma é a secretaria, porque
# classificar um atestado como "outro" é problema de prontuário, não de UX.
_PISTAS = {
    CategoriaDocumento.ATESTADO: ("atestado", "médic", "medic", "consulta", "declaração médica"),
    CategoriaDocumento.MATRICULA: (
        "matríc", "matric", "rematríc", "rg", "cpf", "certidão", "certidao",
        "nascimento", "residên", "residen", "comprovante de endereço", "vacina",
    ),
    CategoriaDocumento.COMPROVANTE: ("comprovante", "pagamento", "pix", "recibo", "boleto"),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def sugerir_categoria(texto: str) -> CategoriaDocumento | None:
    """Palpite de finalidade pela legenda. ``None`` quando nada é evidente.

    Deliberadamente burro: heurística de palavra, sem LLM. Chamar o modelo para adivinhar
    o que a secretaria vai confirmar em um clique não paga a latência nem o custo — e um
    palpite errado com ar de certeza é pior que nenhum palpite.
    """
    normalizado = (texto or "").lower()
    if not normalizado:
        return None
    for categoria, pistas in _PISTAS.items():
        if any(p in normalizado for p in pistas):
            return categoria
    return None


@dataclass(frozen=True)
class ResultadoRecepcao:
    """O que aconteceu com uma mídia recebida — o inbound loga isso."""

    documento: DocumentoRecebido | None = None
    duplicado: bool = False
    # Recusado pela allowlist de MIME ou pelo teto de tamanho.
    recusado: str = ""

    @property
    def aceito(self) -> bool:
        return self.documento is not None and not self.duplicado


class ReceberDocumentoDoResponsavel:
    """Persiste um arquivo que chegou pelo WhatsApp e o liga à conversa.

    Recebe o arquivo **já baixado** (`ArquivoBaixado`): quem fala com a Graph API é o
    adaptador ``FonteMidia``, e este caso de uso não deve saber que a Meta existe.
    """

    def __init__(
        self,
        *,
        documentos: DocumentoRecebidoRepository,
        storage: ArquivoStorage,
        contatos: ContatoRepository | None = None,
        bloqueios: NumeroBloqueadoRepository | None = None,
        retencao_dias: int = RETENCAO_PADRAO_DIAS,
    ) -> None:
        self._documentos = documentos
        self._storage = storage
        self._contatos = contatos
        self._bloqueios = bloqueios
        self._retencao_dias = retencao_dias

    async def executar(
        self,
        *,
        tenant_id: UUID,
        conversa_id: UUID,
        contato: str,
        arquivo: ArquivoBaixado,
        media_id: str = "",
        legenda: str = "",
        atendimento_id: UUID | None = None,
    ) -> ResultadoRecepcao:
        # Revalida aqui, e não só no adaptador: o caso de uso é o último ponto antes do
        # banco, e um adaptador futuro pode não ter as mesmas defesas.
        if arquivo.mime not in MIMES_ACEITOS:
            return ResultadoRecepcao(recusado=f"tipo não aceito: {arquivo.mime}")
        if arquivo.tamanho > TAMANHO_MAXIMO_DOCUMENTO:
            return ResultadoRecepcao(recusado=f"arquivo grande demais: {arquivo.tamanho} bytes")
        if not arquivo.conteudo:
            return ResultadoRecepcao(recusado="arquivo vazio")

        # Anti-spam camada 2 (§4.5): número bloqueado não manda arquivo. **Antes** do
        # download já ter custado — e antes de gravar bytes de quem a escola recusou.
        if self._bloqueios is not None and await self._bloqueios.bloqueado(
            tenant_id=tenant_id, telefone=contato
        ):
            return ResultadoRecepcao(recusado="número bloqueado para envio de arquivos")

        if media_id:
            existente = await self._documentos.por_media_id(
                tenant_id=tenant_id, media_id=media_id
            )
            if existente is not None:
                # Reentrega do webhook: não baixa nem grava de novo.
                return ResultadoRecepcao(documento=existente, duplicado=True)

        chave = nova_chave(tenant_id)
        await self._storage.guardar(
            chave=chave, conteudo=arquivo.conteudo, mime=arquivo.mime
        )

        sugerida = sugerir_categoria(f"{legenda} {arquivo.nome}")
        # Anti-spam camada 1 (§4.5): origem desconhecida vai para **quarentena** — fora da
        # fila de trabalho, mas guardada. Descartar de saída perderia o documento de um pai
        # que trocou de número, que é justamente quem mais precisa dele.
        nome_contato = await self._nome_do_contato(tenant_id=tenant_id, telefone=contato)
        conhecido = bool(nome_contato) or self._contatos is None
        documento = DocumentoRecebido(
            tenant_id=tenant_id,
            conversa_id=conversa_id,
            contato=contato,
            contato_nome=nome_contato,
            status=StatusDocumento.RECEBIDO if conhecido else StatusDocumento.QUARENTENA,
            chave_storage=chave,
            mime=arquivo.mime,
            tamanho=arquivo.tamanho,
            nome_arquivo=arquivo.nome,
            observacao=legenda.strip(),
            # A categoria confirmada nasce igual à sugerida quando há palpite — poupa o
            # clique no caso comum sem esconder que foi um palpite (``categoria_sugerida``
            # fica registrada).
            categoria=sugerida or CategoriaDocumento.OUTRO,
            categoria_sugerida=sugerida,
            atendimento_id=atendimento_id,
            media_id=media_id,
            expira_em=_now() + timedelta(days=self._retencao_dias),
        )
        return ResultadoRecepcao(documento=await self._documentos.criar(documento))

    async def _nome_do_contato(self, *, tenant_id: UUID, telefone: str) -> str:
        if self._contatos is None:
            return ""
        contato = await self._contatos.por_telefone(tenant_id=tenant_id, telefone=telefone)
        return contato.nome if contato else ""


class ListarDocumentosRecebidos:
    def __init__(self, *, documentos: DocumentoRecebidoRepository) -> None:
        self._documentos = documentos

    async def executar(
        self,
        *,
        tenant_id: UUID,
        categoria: CategoriaDocumento | None = None,
        status: StatusDocumento | None = None,
        aluno_id: UUID | None = None,
        pagina: int = 1,
        por_pagina: int = POR_PAGINA_PADRAO,
    ) -> Pagina[DocumentoRecebido]:
        pagina, por_pagina = normalizar_paginacao(pagina, por_pagina)
        filtros = {
            "tenant_id": tenant_id,
            "categoria": categoria,
            "status": status,
            "aluno_id": aluno_id,
        }
        total = await self._documentos.contar(**filtros)
        itens = await self._documentos.listar(**filtros, pagina=pagina, por_pagina=por_pagina)
        return Pagina(itens=itens, total=total, pagina=pagina, por_pagina=por_pagina)


class ObterDocumentoRecebido:
    def __init__(self, *, documentos: DocumentoRecebidoRepository) -> None:
        self._documentos = documentos

    async def executar(
        self, *, tenant_id: UUID, documento_id: UUID
    ) -> DocumentoRecebido | None:
        return await self._documentos.obter(tenant_id=tenant_id, documento_id=documento_id)


@dataclass(frozen=True)
class ArquivoParaDownload:
    nome: str
    mime: str
    conteudo: bytes


class BaixarDocumentoRecebido:
    """Entrega os bytes ao painel — sempre pela API autenticada.

    Não existe URL pública nem link assinado de longa duração: o conteúdo é dado sensível
    de menor, e um link que vaza é um link que funciona para sempre. Quem chama é
    responsável por auditar (§13) e por já ter verificado o acesso ao tenant.
    """

    def __init__(
        self, *, documentos: DocumentoRecebidoRepository, storage: ArquivoStorage
    ) -> None:
        self._documentos = documentos
        self._storage = storage

    async def executar(
        self, *, tenant_id: UUID, documento_id: UUID
    ) -> ArquivoParaDownload | None:
        documento = await self._documentos.obter(
            tenant_id=tenant_id, documento_id=documento_id
        )
        if documento is None:
            return None
        conteudo = await self._storage.ler(chave=documento.chave_storage)
        if conteudo is None:
            # Metadado sem arquivo: o expurgo já passou, ou o storage perdeu o objeto.
            logger.warning(
                "Documento %s sem conteúdo no storage (chave %s)",
                documento.id,
                documento.chave_storage,
            )
            return None
        return ArquivoParaDownload(
            nome=documento.nome_arquivo or f"documento-{documento.id}",
            mime=documento.mime,
            conteudo=conteudo,
        )


class ClassificarDocumento:
    """A secretaria confirma a finalidade, vincula a um aluno e conclui o tratamento."""

    def __init__(
        self,
        *,
        documentos: DocumentoRecebidoRepository,
        alunos: AlunoRepository | None = None,
    ) -> None:
        self._documentos = documentos
        self._alunos = alunos

    async def executar(
        self,
        *,
        tenant_id: UUID,
        documento_id: UUID,
        categoria: CategoriaDocumento | None = None,
        status: StatusDocumento | None = None,
        aluno_id: UUID | None = None,
        observacao: str | None = None,
    ) -> DocumentoRecebido:
        documento = await self._documentos.obter(
            tenant_id=tenant_id, documento_id=documento_id
        )
        if documento is None:
            raise ValueError("Documento não encontrado.")

        if categoria is not None:
            documento.categoria = categoria
        if observacao is not None:
            documento.observacao = observacao.strip()
        if aluno_id is not None:
            aluno = (
                await self._alunos.obter(tenant_id=tenant_id, aluno_id=aluno_id)
                if self._alunos
                else None
            )
            if self._alunos is not None and aluno is None:
                # Vincular a um aluno de outra escola seria vazamento entre tenants.
                raise ValueError("Aluno não encontrado nesta escola.")
            documento.aluno_id = aluno_id
            documento.aluno_nome = aluno.nome if aluno else ""
        if status is not None:
            documento.status = status
            documento.processado_em = (
                _now() if status is StatusDocumento.PROCESSADO else None
            )
        return await self._documentos.atualizar(documento)


@dataclass(frozen=True)
class ResultadoExpurgo:
    removidos: int = 0
    falhas: int = 0


class ExpurgarDocumentosVencidos:
    """Apaga os arquivos cujo prazo de retenção venceu (LGPD).

    Apaga **os bytes e o metadado**: manter a linha "havia um atestado do aluno X" depois
    do prazo continuaria sendo tratamento de dado sensível, só que sem o arquivo — o pior
    dos dois mundos.

    Tolerante a falha por item: um arquivo que o storage não consegue remover não pode
    interromper o expurgo dos outros, senão um objeto problemático congela a rotina
    inteira e o passivo cresce em silêncio.
    """

    def __init__(
        self, *, documentos: DocumentoRecebidoRepository, storage: ArquivoStorage
    ) -> None:
        self._documentos = documentos
        self._storage = storage

    async def executar(self, *, limite: int = 500) -> ResultadoExpurgo:
        vencidos = await self._documentos.expirados(limite=limite)
        removidos = falhas = 0
        for documento in vencidos:
            try:
                await self._storage.remover(chave=documento.chave_storage)
                await self._documentos.remover(
                    tenant_id=documento.tenant_id, documento_id=documento.id
                )
                removidos += 1
            except Exception:  # noqa: BLE001 — um item ruim não trava a rotina
                falhas += 1
                logger.warning(
                    "Falha ao expurgar o documento %s (tenant %s)",
                    documento.id,
                    documento.tenant_id,
                    exc_info=True,
                )
        if removidos or falhas:
            logger.info(
                "Expurgo de documentos: %d removidos, %d falhas", removidos, falhas
            )
        return ResultadoExpurgo(removidos=removidos, falhas=falhas)


class ReceberMidiaDoResponsavel:
    """Orquestra a chegada de um arquivo pelo WhatsApp, do webhook até a confirmação.

    Junta as três pontas que o inbound precisa e que não deveriam viver no adaptador da
    Meta: baixar a mídia, guardá-la e **dizer ao responsável que chegou**.

    Essa confirmação não é gentileza — é o que impede o reenvio em série. Quem manda a
    foto do atestado e não ouve nada manda de novo, e mais uma vez, e a secretaria recebe
    o mesmo documento três vezes. Por isso ela sai **mesmo quando a conversa já está com
    uma pessoa** (§6j): é recibo de entrega, não resposta ao assunto.
    """

    def __init__(
        self,
        *,
        fonte: FonteMidia,
        recepcao: ReceberDocumentoDoResponsavel,
        conversas: ConversaRepository,
        mesa: MesaDeAtendimento | None = None,
    ) -> None:
        self._fonte = fonte
        self._recepcao = recepcao
        self._conversas = conversas
        self._mesa = mesa

    async def executar(
        self,
        *,
        tenant_id: UUID,
        contato: str,
        media_id: str,
        legenda: str = "",
        nome_arquivo: str = "",
    ) -> str:
        """Devolve o texto a enviar ao responsável (``""`` = não responder)."""
        conversa = await self._conversas.obter_ou_criar(tenant_id=tenant_id, contato=contato)

        # O arquivo entra no fio da conversa antes de qualquer download: se a Graph API
        # falhar, o histórico ainda mostra que o responsável tentou enviar algo — que é a
        # informação que a secretaria precisa para cobrar o reenvio.
        rotulo = nome_arquivo or "arquivo"
        await self._conversas.adicionar_mensagem(
            conversa_id=conversa.id,
            autor="usuario",
            texto=f"📎 {rotulo}" + (f"\n{legenda}" if legenda.strip() else ""),
        )

        atendimento_id = await self._atendimento_da_conversa(conversa.id)

        arquivo = await self._fonte.baixar(media_id)
        if arquivo is None:
            return await self._responder(
                conversa.id,
                "Não consegui abrir o arquivo que você enviou. Por gentileza, reenvie "
                "como **foto** ou **PDF** — são os formatos que a secretaria consegue "
                "receber por aqui.",
            )

        resultado = await self._recepcao.executar(
            tenant_id=tenant_id,
            conversa_id=conversa.id,
            contato=contato,
            arquivo=arquivo,
            media_id=media_id,
            legenda=legenda,
            atendimento_id=atendimento_id,
        )

        if resultado.duplicado:
            # Reentrega do webhook: o arquivo já está guardado e o responsável já foi
            # avisado. Confirmar de novo o faria pensar que enviou duas vezes.
            return ""
        if resultado.documento is None:
            logger.info(
                "Documento recusado de %s (tenant %s): %s",
                contato,
                tenant_id,
                resultado.recusado,
            )
            return await self._responder(
                conversa.id,
                "Não consegui receber esse arquivo. Envie uma foto ou um PDF de até 16 MB.",
            )

        return await self._responder(
            conversa.id,
            f"Recebemos o seu arquivo ({resultado.documento.tamanho_legivel}). "
            "A secretaria vai conferir e, se faltar algum documento, entramos em contato "
            "por aqui.",
        )

    async def _atendimento_da_conversa(self, conversa_id: UUID) -> UUID | None:
        """Amarra o arquivo ao atendimento aberto, se houver (§6j).

        Sem isso, quem está atendendo o responsável veria a conversa pedindo um documento
        e teria de procurá-lo em outra tela.
        """
        if self._mesa is None:
            return None
        atendimento = await self._mesa.vivo_na_conversa(conversa_id)
        if atendimento is None:
            return None
        if atendimento.na_fila:
            # O envio conta como atividade do responsável: renova a janela de 24h de quem
            # vai responder.
            await self._mesa.registrar_retorno(atendimento)
        return atendimento.id

    async def _responder(self, conversa_id: UUID, texto: str) -> str:
        await self._conversas.adicionar_mensagem(
            conversa_id=conversa_id, autor="bot", texto=texto
        )
        return texto


# --------------------------------------------------------------------------- #
# §4.5 — anti-spam: quarentena, sugestão de bloqueio e bloqueio (sempre humano)
# --------------------------------------------------------------------------- #
class SugerirBloqueios:
    """Números que cruzaram o limiar de descartes e **merecem uma olhada** (decisão C).

    Sugere, não bloqueia. Três documentos descartados do mesmo número em sete dias é sinal
    de spam — mas também é o que faz um pai que mandou três fotos tremidas do mesmo
    atestado. Um contador não distingue os dois, e bloquear em silêncio quem estava
    tentando entregar um documento é exatamente a falha que o produto existe para evitar.
    """

    def __init__(
        self,
        *,
        documentos: DocumentoRecebidoRepository,
        bloqueios: NumeroBloqueadoRepository,
    ) -> None:
        self._documentos = documentos
        self._bloqueios = bloqueios

    async def executar(self, *, tenant_id: UUID) -> list[SugestaoBloqueio]:
        desde = _now() - timedelta(days=JANELA_DESCARTES_DIAS)
        sugestoes = await self._documentos.descartados_por_numero(
            tenant_id=tenant_id, desde=desde, minimo=DESCARTES_PARA_SUGERIR_BLOQUEIO
        )
        # Quem já está bloqueado não vira sugestão de novo — seria pedir à secretaria que
        # decidisse duas vezes a mesma coisa.
        ja_bloqueados = {
            b.telefone for b in await self._bloqueios.listar(tenant_id=tenant_id)
        }
        return [s for s in sugestoes if s.telefone not in ja_bloqueados]


class BloquearNumero:
    """Recusa **mídia** daquele número. O texto continua sendo atendido.

    Sempre disparado por uma pessoa: a sugestão é da aplicação, a decisão é da escola.
    """

    def __init__(self, *, bloqueios: NumeroBloqueadoRepository) -> None:
        self._bloqueios = bloqueios

    async def executar(
        self, *, tenant_id: UUID, telefone: str, motivo: str = "", por: str = ""
    ) -> NumeroBloqueado:
        telefone = telefone.strip()
        if not telefone:
            raise ValueError("Informe o número a bloquear.")
        return await self._bloqueios.bloquear(
            NumeroBloqueado(
                tenant_id=tenant_id,
                telefone=telefone,
                motivo=motivo.strip(),
                bloqueado_por=por,
            )
        )


class DesbloquearNumero:
    def __init__(self, *, bloqueios: NumeroBloqueadoRepository) -> None:
        self._bloqueios = bloqueios

    async def executar(self, *, tenant_id: UUID, telefone: str) -> bool:
        return await self._bloqueios.desbloquear(tenant_id=tenant_id, telefone=telefone)


class ListarNumerosBloqueados:
    def __init__(self, *, bloqueios: NumeroBloqueadoRepository) -> None:
        self._bloqueios = bloqueios

    async def executar(self, *, tenant_id: UUID) -> list[NumeroBloqueado]:
        return await self._bloqueios.listar(tenant_id=tenant_id)


class LerDocumentoPorIA:
    """Lê um documento já recebido e devolve **sugestões** para a secretaria revisar (§4.3).

    Prévia, não gravação — o mesmo fluxo da importação em massa (§6c-quater) e da leitura
    de ficha (§D3): a LLM sugere, o código valida, a pessoa confirma. Nada é persistido
    aqui; quem grava é ``ClassificarDocumento``, com o que a secretaria aprovou.

    Roda **sob demanda**, e não em todo upload: em época de matrícula o volume é alto e a
    maioria dos documentos a secretaria classifica de olho.
    """

    def __init__(
        self,
        *,
        documentos: DocumentoRecebidoRepository,
        storage: ArquivoStorage,
        leitor: LeitorDocumento,
    ) -> None:
        self._documentos = documentos
        self._storage = storage
        self._leitor = leitor

    async def executar(
        self, *, tenant_id: UUID, documento_id: UUID
    ) -> DocumentoLido | None:
        documento = await self._documentos.obter(
            tenant_id=tenant_id, documento_id=documento_id
        )
        if documento is None:
            return None
        conteudo = await self._storage.ler(chave=documento.chave_storage)
        if conteudo is None:
            # Arquivo já expurgado: o metadado sobrevive aos bytes por desenho (§6k).
            return DocumentoLido(erro="O arquivo não está mais disponível.")
        return await self._leitor.ler(conteudo=conteudo, mime=documento.mime)
