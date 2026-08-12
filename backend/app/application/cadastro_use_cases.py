"""Casos de uso de cadastro escolar: pais/responsáveis (CRUD), salas (CRUD),
vínculo pai↔sala e relatório de pais por sala.

A camada de aplicação apenas orquestra as portas ``ContatoRepository`` e
``SalaRepository``; nenhuma dependência de framework ou ORM.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from uuid import UUID

from app.application.paginacao import (
    POR_PAGINA_PADRAO,
    Pagina,
    normalizar_paginacao,
)
from app.application.validacao import (
    data_nao_futura,
    normalizar_cpf,
    normalizar_data,
    normalizar_email,
    normalizar_telefone,
)
from app.domain.entities import Aluno, CoberturaContatosSala, Contato, Professor, Sala
from app.domain.ports import (
    AlunoRepository,
    ContatoRepository,
    MessageChannel,
    ProfessorRepository,
    SalaRepository,
)
from app.infrastructure.security import hash_senha


# --------------------------------------------------------------------------- #
# Pais / responsáveis (CRUD)
# --------------------------------------------------------------------------- #
class CadastrarPai:
    """Cadastra um pai/responsável e, opcionalmente, já o vincula a salas.

    O telefone é único por tenant (E.164). Vincular a salas na criação atende ao
    fluxo "cadastrar o pai e relacionar com uma sala" em uma única ação.
    """

    def __init__(self, *, contatos: ContatoRepository, salas: SalaRepository) -> None:
        self._contatos = contatos
        self._salas = salas

    async def executar(
        self,
        *,
        tenant_id: UUID,
        nome: str,
        telefone: str,
        sala_ids: Sequence[UUID] = (),
    ) -> Contato:
        if await self._contatos.por_telefone(tenant_id=tenant_id, telefone=telefone):
            raise ValueError("Já existe um responsável com este telefone neste tenant.")

        contato = await self._contatos.criar(
            Contato(tenant_id=tenant_id, nome=nome, telefone=telefone)
        )
        for sala_id in sala_ids:
            await self._salas.vincular_pai(
                tenant_id=tenant_id, sala_id=sala_id, contato_id=contato.id
            )
        return contato


class ListarPais:
    def __init__(self, *, contatos: ContatoRepository) -> None:
        self._contatos = contatos

    async def executar(
        self, *, tenant_id: UUID, pagina: int = 1, por_pagina: int = POR_PAGINA_PADRAO
    ) -> Pagina[Contato]:
        pagina, por_pagina = normalizar_paginacao(pagina, por_pagina)
        itens = await self._contatos.listar(
            tenant_id=tenant_id, pagina=pagina, por_pagina=por_pagina
        )
        total = await self._contatos.contar(tenant_id=tenant_id)
        return Pagina(itens=itens, total=total, pagina=pagina, por_pagina=por_pagina)


class AtualizarPai:
    def __init__(self, *, contatos: ContatoRepository) -> None:
        self._contatos = contatos

    async def executar(
        self, *, tenant_id: UUID, contato_id: UUID, nome: str, telefone: str
    ) -> Contato:
        atual = await self._contatos.obter(tenant_id=tenant_id, contato_id=contato_id)
        if atual is None:
            raise ValueError("Responsável não encontrado para o tenant.")

        # Telefone só pode mudar para um valor ainda não usado por outro responsável.
        if telefone != atual.telefone:
            existente = await self._contatos.por_telefone(tenant_id=tenant_id, telefone=telefone)
            if existente is not None and existente.id != contato_id:
                raise ValueError("Já existe um responsável com este telefone neste tenant.")

        atual.nome = nome
        atual.telefone = telefone
        return await self._contatos.atualizar(atual)


class RemoverPai:
    def __init__(self, *, contatos: ContatoRepository) -> None:
        self._contatos = contatos

    async def executar(self, *, tenant_id: UUID, contato_id: UUID) -> bool:
        return await self._contatos.remover(tenant_id=tenant_id, contato_id=contato_id)


# --------------------------------------------------------------------------- #
# Salas / turmas (CRUD)
# --------------------------------------------------------------------------- #
class CriarSala:
    def __init__(self, *, salas: SalaRepository) -> None:
        self._salas = salas

    async def executar(self, *, tenant_id: UUID, nome: str, descricao: str = "") -> Sala:
        return await self._salas.criar(Sala(tenant_id=tenant_id, nome=nome, descricao=descricao))


class ListarSalas:
    def __init__(self, *, salas: SalaRepository) -> None:
        self._salas = salas

    async def executar(self, *, tenant_id: UUID) -> list[Sala]:
        return await self._salas.listar(tenant_id=tenant_id)


class ObterSala:
    def __init__(self, *, salas: SalaRepository) -> None:
        self._salas = salas

    async def executar(self, *, tenant_id: UUID, sala_id: UUID) -> Sala:
        sala = await self._salas.obter(tenant_id=tenant_id, sala_id=sala_id)
        if sala is None:
            raise ValueError("Sala não encontrada para o tenant.")
        return sala


class AtualizarSala:
    def __init__(self, *, salas: SalaRepository) -> None:
        self._salas = salas

    async def executar(
        self, *, tenant_id: UUID, sala_id: UUID, nome: str, descricao: str = ""
    ) -> Sala:
        return await self._salas.atualizar(
            tenant_id=tenant_id, sala_id=sala_id, nome=nome, descricao=descricao
        )


class RemoverSala:
    """Remove uma série/sala, transferindo os alunos dela.

    Como ``Aluno.sala_id`` é obrigatório, a exclusão precisa de um destino explícito:
    ``mover_para=<sala_id>`` **transfere** os alunos para outra série (que deve existir no
    tenant e ser diferente da removida) e só então remove a original.

    **Uma série com alunos não pode ser removida sem destino.** Antes, ``mover_para=None``
    apagava os alunos junto — o caminho mais fácil da tela destruía o histórico de quem
    estudou na escola. Série vazia continua removível sem cerimônia.
    """

    def __init__(self, *, salas: SalaRepository, alunos: AlunoRepository) -> None:
        self._salas = salas
        self._alunos = alunos

    async def executar(
        self, *, tenant_id: UUID, sala_id: UUID, mover_para: UUID | None = None
    ) -> bool:
        sala = await self._salas.obter(tenant_id=tenant_id, sala_id=sala_id)
        if sala is None:
            return False

        alunos_da_sala = await self._alunos.listar(tenant_id=tenant_id, sala_id=sala_id)
        if alunos_da_sala and mover_para is None:
            raise ValueError(
                f"A série tem {len(alunos_da_sala)} aluno(s). Informe a série destino para "
                "transferi-los — alunos não são apagados junto com a série, porque o "
                "registro de que estudaram aqui precisa ser preservado."
            )
        if mover_para is not None:
            if mover_para == sala_id:
                raise ValueError("A série destino deve ser diferente da que está sendo removida.")
            await _validar_sala(self._salas, tenant_id=tenant_id, sala_id=mover_para)
            for aluno in alunos_da_sala:
                aluno.sala_id = mover_para
                await self._alunos.atualizar(aluno)

        return await self._salas.remover(tenant_id=tenant_id, sala_id=sala_id)


# --------------------------------------------------------------------------- #
# Vínculo pai ↔ sala e relatório
# --------------------------------------------------------------------------- #
class VincularPaiASala:
    def __init__(self, *, salas: SalaRepository) -> None:
        self._salas = salas

    async def executar(self, *, tenant_id: UUID, sala_id: UUID, contato_id: UUID) -> None:
        await self._salas.vincular_pai(
            tenant_id=tenant_id, sala_id=sala_id, contato_id=contato_id
        )


class DesvincularPaiDaSala:
    def __init__(self, *, salas: SalaRepository) -> None:
        self._salas = salas

    async def executar(self, *, tenant_id: UUID, sala_id: UUID, contato_id: UUID) -> None:
        await self._salas.desvincular_pai(
            tenant_id=tenant_id, sala_id=sala_id, contato_id=contato_id
        )


class RelatorioPaisDaSala:
    """Lista (relatório) dos pais/responsáveis vinculados a uma sala específica."""

    def __init__(self, *, salas: SalaRepository) -> None:
        self._salas = salas

    async def executar(self, *, tenant_id: UUID, sala_id: UUID) -> list[Contato]:
        return await self._salas.pais(tenant_id=tenant_id, sala_id=sala_id)


# --------------------------------------------------------------------------- #
# Cobertura de contatos: alunos sem responsável com telefone vinculado
# --------------------------------------------------------------------------- #
def _cobertura(sala: Sala, alunos: list[Aluno]) -> CoberturaContatosSala:
    """Monta a cobertura de uma turma considerando apenas os alunos **ativos**.

    Um aluno conta como "sem contato" quando nenhum de seus responsáveis tem
    telefone (WhatsApp) cadastrado. Ex-alunos (``ativo=False``) são ignorados.
    """
    ativos = [a for a in alunos if a.ativo]
    return CoberturaContatosSala(
        sala_id=sala.id,
        sala_nome=sala.nome,
        total_alunos=len(ativos),
        alunos_sem_contato=[a for a in ativos if not a.tem_contato],
    )


class CoberturaDeContatosDaSala:
    """Cobertura de contatos de uma turma específica (com a lista de alunos sem contato)."""

    def __init__(self, *, salas: SalaRepository, alunos: AlunoRepository) -> None:
        self._salas = salas
        self._alunos = alunos

    async def executar(self, *, tenant_id: UUID, sala_id: UUID) -> CoberturaContatosSala:
        sala = await self._salas.obter(tenant_id=tenant_id, sala_id=sala_id)
        if sala is None:
            raise ValueError("Sala não encontrada para o tenant.")
        alunos = await self._alunos.listar(tenant_id=tenant_id, sala_id=sala_id)
        return _cobertura(sala, alunos)


class ResumoCoberturaDasSalas:
    """Cobertura de contatos de todas as turmas do tenant, para o painel de salas.

    Carrega os alunos uma única vez e os agrupa por sala (evita um N+1 por turma).
    """

    def __init__(self, *, salas: SalaRepository, alunos: AlunoRepository) -> None:
        self._salas = salas
        self._alunos = alunos

    async def executar(self, *, tenant_id: UUID) -> list[CoberturaContatosSala]:
        salas = await self._salas.listar(tenant_id=tenant_id)
        todos = await self._alunos.listar(tenant_id=tenant_id)
        por_sala: dict[UUID, list[Aluno]] = {}
        for aluno in todos:
            por_sala.setdefault(aluno.sala_id, []).append(aluno)
        return [_cobertura(sala, por_sala.get(sala.id, [])) for sala in salas]


def _montar_aviso_professor(cobertura: CoberturaContatosSala, mensagem: str = "") -> str:
    """Texto enviado ao professor pedindo os contatos de responsáveis faltantes."""
    linhas = [
        f"• {a.nome}" + (f" (mat. {a.matricula})" if a.matricula else "")
        for a in cobertura.alunos_sem_contato
    ]
    corpo = (
        f"⚠️ Turma {cobertura.sala_nome}: {cobertura.total_sem_contato} de "
        f"{cobertura.total_alunos} aluno(s) sem contato de responsável (WhatsApp).\n\n"
        "Alunos sem contato:\n"
        + "\n".join(linhas)
        + "\n\nPor favor, colete o WhatsApp de um responsável e repasse à secretaria "
        "para cadastro."
    )
    prefixo = mensagem.strip()
    return f"{prefixo}\n\n{corpo}" if prefixo else corpo


class NotificarProfessorContatosFaltantes:
    """Dispara ao professor uma notificação pedindo os contatos faltantes de uma turma.

    Envia um texto livre pelo ``MessageChannel`` para o telefone informado do professor,
    listando os alunos sem contato de responsável. Falha se não há nenhum faltante.
    """

    def __init__(
        self,
        *,
        salas: SalaRepository,
        alunos: AlunoRepository,
        canal: MessageChannel,
    ) -> None:
        self._salas = salas
        self._alunos = alunos
        self._canal = canal

    async def executar(
        self,
        *,
        tenant_id: UUID,
        sala_id: UUID,
        telefone_professor: str,
        mensagem: str = "",
    ) -> tuple[CoberturaContatosSala, str]:
        if not telefone_professor.strip():
            raise ValueError("Informe o telefone (WhatsApp) do professor.")
        cobertura = await CoberturaDeContatosDaSala(
            salas=self._salas, alunos=self._alunos
        ).executar(tenant_id=tenant_id, sala_id=sala_id)
        if cobertura.total_sem_contato == 0:
            raise ValueError(
                "Todos os alunos da turma já têm um responsável com telefone cadastrado."
            )
        texto = _montar_aviso_professor(cobertura, mensagem)
        id_externo = await self._canal.enviar_texto(
            contato=telefone_professor.strip(), texto=texto
        )
        return cobertura, id_externo


# --------------------------------------------------------------------------- #
# Alunos (CRUD + vínculo com responsáveis e série)
# --------------------------------------------------------------------------- #
async def _validar_sala(salas: SalaRepository, *, tenant_id: UUID, sala_id: UUID) -> None:
    """Garante que a série/sala informada pertence ao tenant."""
    if await salas.obter(tenant_id=tenant_id, sala_id=sala_id) is None:
        raise ValueError("Série/sala não encontrada para o tenant.")


class CadastrarAluno:
    """Cadastra um aluno, opcionalmente já com série e responsáveis vinculados."""

    def __init__(self, *, alunos: AlunoRepository, salas: SalaRepository) -> None:
        self._alunos = alunos
        self._salas = salas

    async def executar(
        self,
        *,
        tenant_id: UUID,
        nome: str,
        sala_id: UUID,
        matricula: str = "",
        responsavel_ids: Sequence[UUID] = (),
    ) -> Aluno:
        await _validar_sala(self._salas, tenant_id=tenant_id, sala_id=sala_id)
        aluno = await self._alunos.criar(
            Aluno(tenant_id=tenant_id, nome=nome, sala_id=sala_id, matricula=matricula)
        )
        for contato_id in responsavel_ids:
            await self._alunos.vincular_responsavel(
                tenant_id=tenant_id, aluno_id=aluno.id, contato_id=contato_id
            )
        return await self._alunos.obter(tenant_id=tenant_id, aluno_id=aluno.id)


class ListarAlunos:
    def __init__(self, *, alunos: AlunoRepository) -> None:
        self._alunos = alunos

    async def executar(
        self, *, tenant_id: UUID, sala_id: UUID | None = None,
        apenas_ativos: bool | None = None,
        pagina: int = 1,
        por_pagina: int = POR_PAGINA_PADRAO,
    ) -> Pagina[Aluno]:
        """``apenas_ativos=None`` traz matriculados e ex-alunos; ``True``/``False`` filtra."""
        pagina, por_pagina = normalizar_paginacao(pagina, por_pagina)
        itens = await self._alunos.listar(
            tenant_id=tenant_id,
            sala_id=sala_id,
            apenas_ativos=apenas_ativos,
            pagina=pagina,
            por_pagina=por_pagina,
        )
        total = await self._alunos.contar(
            tenant_id=tenant_id, sala_id=sala_id, apenas_ativos=apenas_ativos
        )
        return Pagina(itens=itens, total=total, pagina=pagina, por_pagina=por_pagina)


class ObterAluno:
    def __init__(self, *, alunos: AlunoRepository) -> None:
        self._alunos = alunos

    async def executar(self, *, tenant_id: UUID, aluno_id: UUID) -> Aluno:
        aluno = await self._alunos.obter(tenant_id=tenant_id, aluno_id=aluno_id)
        if aluno is None:
            raise ValueError("Aluno não encontrado para o tenant.")
        return aluno


class AtualizarAluno:
    def __init__(self, *, alunos: AlunoRepository, salas: SalaRepository) -> None:
        self._alunos = alunos
        self._salas = salas

    async def executar(
        self,
        *,
        tenant_id: UUID,
        aluno_id: UUID,
        nome: str,
        sala_id: UUID,
        matricula: str = "",
        ativo: bool = True,
    ) -> Aluno:
        atual = await self._alunos.obter(tenant_id=tenant_id, aluno_id=aluno_id)
        if atual is None:
            raise ValueError("Aluno não encontrado para o tenant.")
        await _validar_sala(self._salas, tenant_id=tenant_id, sala_id=sala_id)
        atual.nome = nome
        atual.sala_id = sala_id
        atual.matricula = matricula
        atual.ativo = ativo
        return await self._alunos.atualizar(atual)


class DesativarAluno:
    """"Exclusão" de aluno pelo painel — que é sempre **soft delete**.

    O aluno nunca é apagado: o registro de que ele estudou aqui é o lastro da escola
    (histórico escolar, declarações, prestação de contas). Marcar como ex-aluno preserva
    esse rastro, os vínculos com responsáveis e a ficha de matrícula, e ainda permite
    desfazer o clique errado (``ReativarAluno``).
    """

    def __init__(self, *, alunos: AlunoRepository) -> None:
        self._alunos = alunos

    async def executar(
        self, *, tenant_id: UUID, aluno_id: UUID, motivo: str = ""
    ) -> Aluno | None:
        aluno = await self._alunos.obter(tenant_id=tenant_id, aluno_id=aluno_id)
        if aluno is None:
            return None
        aluno.desativar(motivo=motivo)
        return await self._alunos.atualizar(aluno)


class ReativarAluno:
    """Volta o ex-aluno à condição de matriculado (rematrícula ou correção)."""

    def __init__(self, *, alunos: AlunoRepository) -> None:
        self._alunos = alunos

    async def executar(self, *, tenant_id: UUID, aluno_id: UUID) -> Aluno | None:
        aluno = await self._alunos.obter(tenant_id=tenant_id, aluno_id=aluno_id)
        if aluno is None:
            return None
        aluno.reativar()
        return await self._alunos.atualizar(aluno)


class VincularResponsavelAoAluno:
    def __init__(self, *, alunos: AlunoRepository) -> None:
        self._alunos = alunos

    async def executar(self, *, tenant_id: UUID, aluno_id: UUID, contato_id: UUID) -> None:
        await self._alunos.vincular_responsavel(
            tenant_id=tenant_id, aluno_id=aluno_id, contato_id=contato_id
        )


class DesvincularResponsavelDoAluno:
    def __init__(self, *, alunos: AlunoRepository) -> None:
        self._alunos = alunos

    async def executar(self, *, tenant_id: UUID, aluno_id: UUID, contato_id: UUID) -> None:
        await self._alunos.desvincular_responsavel(
            tenant_id=tenant_id, aluno_id=aluno_id, contato_id=contato_id
        )


# --------------------------------------------------------------------------- #
# Professores (CRUD) e atribuição à série (Sala.professor_id)
# --------------------------------------------------------------------------- #
@dataclass
class DadosProfessor:
    """Campos do cadastro funcional, agrupados para não estourar a lista de argumentos.

    Todos opcionais: o cadastro mínimo continua sendo **nome + telefone**, que é o que a
    escola tem no primeiro dia. Exigir CPF e matrícula de saída travaria o cadastro de
    quem já está dando aula.
    """

    cpf: str = ""
    data_nascimento: str = ""
    matricula: str = ""
    endereco: str = ""
    telefone_2: str = ""
    email: str = ""
    educacao_fisica: bool = False
    titular: bool = True


def _validar_dados_professor(dados: DadosProfessor) -> DadosProfessor:
    """Normaliza os formatos e recusa o que é erro de digitação, não escolha."""
    return DadosProfessor(
        cpf=normalizar_cpf(dados.cpf),
        data_nascimento=data_nao_futura(
            normalizar_data(dados.data_nascimento, campo="Data de nascimento"),
            campo="Data de nascimento",
        ),
        matricula=dados.matricula.strip(),
        endereco=dados.endereco.strip(),
        # O segundo telefone é de emergência e não roteia nada, mas guardar "(15) 9 9999"
        # e "+5515999990000" na mesma coluna torna a busca por número inútil.
        telefone_2=_e164_ou_erro(dados.telefone_2, campo="Telefone 2"),
        email=normalizar_email(dados.email),
        educacao_fisica=dados.educacao_fisica,
        titular=dados.titular,
    )


def _e164_ou_erro(bruto: str, *, campo: str) -> str:
    e164, aviso = normalizar_telefone(bruto)
    if aviso:
        raise ValueError(f"{campo}: {aviso}")
    return e164


class CadastrarProfessor:
    """Cadastra um professor. Telefone e CPF únicos por tenant."""

    def __init__(self, *, professores: ProfessorRepository) -> None:
        self._professores = professores

    async def executar(
        self,
        *,
        tenant_id: UUID,
        nome: str,
        telefone: str,
        senha: str = "",
        dados: DadosProfessor | None = None,
    ) -> Professor:
        if await self._professores.por_telefone(tenant_id=tenant_id, telefone=telefone):
            raise ValueError("Já existe um professor com este telefone neste tenant.")
        validos = _validar_dados_professor(dados or DadosProfessor())
        if validos.cpf and await self._professores.por_cpf(
            tenant_id=tenant_id, cpf=validos.cpf
        ):
            raise ValueError("Já existe um professor com este CPF neste tenant.")
        # Senha opcional habilita o login do professor no mural (§A1).
        senha_hash = hash_senha(senha) if senha else ""
        return await self._professores.criar(
            Professor(
                tenant_id=tenant_id,
                nome=nome,
                telefone=telefone,
                senha_hash=senha_hash,
                **asdict(validos),
            )
        )


class ListarProfessores:
    def __init__(self, *, professores: ProfessorRepository) -> None:
        self._professores = professores

    async def executar(
        self, *, tenant_id: UUID, apenas_eventuais: bool = False
    ) -> list[Professor]:
        return await self._professores.listar(
            tenant_id=tenant_id, apenas_eventuais=apenas_eventuais
        )


class ListarEventuaisDisponiveis:
    """Professores que podem cobrir uma falta (§I1) — ``titular=False`` e com telefone.

    Existe para tirar da mão da secretaria a lista de telefones que ela redigita a cada
    aviso de falta. É consulta, não disparo: quem chama continua sendo ``ChamarEventual``,
    e a escolha de quem chamar segue humana.
    """

    def __init__(self, *, professores: ProfessorRepository) -> None:
        self._professores = professores

    async def executar(self, *, tenant_id: UUID) -> list[Professor]:
        return await self._professores.listar(tenant_id=tenant_id, apenas_eventuais=True)


class ObterProfessor:
    def __init__(self, *, professores: ProfessorRepository) -> None:
        self._professores = professores

    async def executar(self, *, tenant_id: UUID, professor_id: UUID) -> Professor:
        professor = await self._professores.obter(tenant_id=tenant_id, professor_id=professor_id)
        if professor is None:
            raise ValueError("Professor não encontrado para o tenant.")
        return professor


class AtualizarProfessor:
    def __init__(self, *, professores: ProfessorRepository) -> None:
        self._professores = professores

    async def executar(
        self,
        *,
        tenant_id: UUID,
        professor_id: UUID,
        nome: str,
        telefone: str,
        senha: str | None = None,
        dados: DadosProfessor | None = None,
    ) -> Professor:
        atual = await self._professores.obter(tenant_id=tenant_id, professor_id=professor_id)
        if atual is None:
            raise ValueError("Professor não encontrado para o tenant.")
        if telefone != atual.telefone:
            existente = await self._professores.por_telefone(tenant_id=tenant_id, telefone=telefone)
            if existente is not None and existente.id != professor_id:
                raise ValueError("Já existe um professor com este telefone neste tenant.")
        atual.nome = nome
        atual.telefone = telefone
        if dados is not None:
            validos = _validar_dados_professor(dados)
            if validos.cpf and validos.cpf != atual.cpf:
                duplicado = await self._professores.por_cpf(
                    tenant_id=tenant_id, cpf=validos.cpf
                )
                if duplicado is not None and duplicado.id != professor_id:
                    raise ValueError("Já existe um professor com este CPF neste tenant.")
            for campo, valor in asdict(validos).items():
                setattr(atual, campo, valor)
        # ``senha=None`` mantém a atual; string vazia limpa o acesso; texto define nova senha.
        if senha is not None:
            atual.senha_hash = hash_senha(senha) if senha else ""
        return await self._professores.atualizar(atual)


class RemoverProfessor:
    """Remove um professor. As séries que ele conduzia ficam **sem professor**."""

    def __init__(self, *, professores: ProfessorRepository) -> None:
        self._professores = professores

    async def executar(self, *, tenant_id: UUID, professor_id: UUID) -> bool:
        return await self._professores.remover(tenant_id=tenant_id, professor_id=professor_id)


class AtribuirProfessorASala:
    """Define (ou troca) o professor responsável por uma série.

    Uma série tem **no máximo um** professor; reatribuir substitui o anterior. O
    professor precisa pertencer ao tenant (validado no repositório).
    """

    def __init__(self, *, salas: SalaRepository) -> None:
        self._salas = salas

    async def executar(self, *, tenant_id: UUID, sala_id: UUID, professor_id: UUID) -> Sala:
        return await self._salas.definir_professor(
            tenant_id=tenant_id, sala_id=sala_id, professor_id=professor_id
        )


class RemoverProfessorDaSala:
    """Desvincula o professor de uma série (``Sala.professor_id`` volta a ser nulo)."""

    def __init__(self, *, salas: SalaRepository) -> None:
        self._salas = salas

    async def executar(self, *, tenant_id: UUID, sala_id: UUID) -> Sala:
        return await self._salas.definir_professor(
            tenant_id=tenant_id, sala_id=sala_id, professor_id=None
        )


class ListarSeriesDoProfessor:
    """Lista as séries (salas) sob responsabilidade de um professor (um professor → N séries)."""

    def __init__(self, *, salas: SalaRepository) -> None:
        self._salas = salas

    async def executar(self, *, tenant_id: UUID, professor_id: UUID) -> list[Sala]:
        salas = await self._salas.listar(tenant_id=tenant_id)
        return [s for s in salas if s.professor_id == professor_id]
