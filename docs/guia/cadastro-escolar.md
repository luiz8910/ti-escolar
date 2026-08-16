# Cadastro escolar — turmas, alunos, responsáveis e professores

> Parte do guia do TI-Escolar — índice em [`CLAUDE.md`](../../CLAUDE.md).
> A numeração das seções (§6a, §9c, …) é a original: as referências cruzadas
> espalhadas pelos outros documentos continuam valendo.

### 6c. Turmas (`Sala`), pais/responsáveis e relatório

> **Nome no painel:** a seção se chama **Turmas** desde 11/ago/2026 — é o vocabulário da
> escola ("sala" lá é o espaço físico). A rota `/admin/salas` redireciona para
> `/admin/turmas` porque a secretaria guarda link em favorito. **No domínio a entidade
> segue `Sala`**, e as rotas da API seguem `/api/admin/salas`: renomear tudo por causa de
> um rótulo seria um diff enorme sem ganho. Dívida anotada.

- **`Sala`** (turma) por tenant, **estruturada** desde 12/ago/2026 (migration
  `0036_turma_estruturada`): `ano_letivo`, `etapa`, `turma`, `numero_sala`, `periodo` e
  `grade_horario`. `nome` virou **derivado** (`etapa` + `turma`) e a unicidade é
  `(tenant_id, ano_letivo, etapa, turma)`.
  - **O UNIQUE antigo em `(tenant_id, nome)` foi removido**, e não é detalhe: o nome
    derivado **se repete legitimamente entre anos letivos** — a "4ª série B" de 2026 e a de
    2027 são turmas diferentes, e o índice antigo recusava a segunda. Só apareceu ao
    exercitar a criação de turma do ano seguinte.
  - **Os responsáveis da turma são derivados dos alunos ativos**, não vinculados à mão. A
    tabela `sala_contatos` e as rotas `POST/DELETE /salas/{id}/pais` **deixaram de
    existir**: elas permitiam um pai ligado a uma turma **sem nenhum filho lá** — o estado
    que fazia a cobertura de contatos (§6c-ter) contar errado. O `downgrade` da migration
    **recria a tabela já populada** a partir da derivação.
  - **Grade de horário em dois formatos** (decisão B do plano de 10/08), sobre a mesma
    coluna JSON: `turno` (entrada, saída e intervalo) e `aulas` (bloco por dia/horário,
    com o **intervalo como bloco** — tratá-lo à parte faria a carga horária ignorá-lo).
    A disciplina do bloco escolhe de um **catálogo do ensino fundamental**
    (`DISCIPLINAS_FUNDAMENTAL`, em `web/lib/admin.ts`) — inclusive Educação Física. É
    `datalist` e **não** `select`: escola tem "Robótica", "Xadrez", "Reforço", e uma
    lista fechada exigiria um deploy nosso para cada uma. O campo gravado segue sendo o
    `rotulo` livre.
    Validação em `app/application/grade_horario.py`, compartilhada por painel e seed:
    recusa hora fora de formato, fim antes do início, intervalo fora do turno e **aulas
    sobrepostas no mesmo dia**. Como o formato gravado é o mesmo, descartar um deles
    depois é apagar componente de tela, não migrar dado.
  - Casos de uso em `app/application/cadastro_use_cases.py`.
- **CRUD completo** de pais e de salas, vínculo/desvínculo pai↔sala e **relatório de pais por
  sala** (`RelatorioPaisDaSala`). `Contato` continua único por `(tenant_id, telefone)`.
- **Rotas** em `app/interfaces/api/cadastro.py` (prefixo `/api/admin`, reaproveitando
  `usuario_autenticado` e `_exige_acesso_tenant`): `pais` (POST/GET/PUT/DELETE),
  `salas` (POST/GET/PUT/DELETE), `salas/{id}/pais` (GET relatório · POST vincular) e
  `salas/{id}/pais/{contato_id}` (DELETE desvincular).
- **Painel:** `web/app/admin/turmas/` — CRUD de salas e pais, vínculo e **relatório imprimível**
  (PDF). O seed cria salas demo ("4ª série B", "5ª série A") com responsáveis vinculados.

### 6c-bis. Alunos (CRUD)

- **`Aluno`** por tenant, com **série 1:1 obrigatória** (`sala_id` → `Sala`, FK restritiva) e
  **responsáveis N:N** (`Contato`s via `aluno_responsaveis`, `ON DELETE CASCADE`). Campos: `nome`,
  `matricula` (opcional), `ativo` (marca **ex-aluno**), `desativado_em`,
  `motivo_desativacao` e `foto_chave` (migration `0035_aluno_foto`).
  **A foto é opcional** (decisão D do plano de 10/08): foto de criança eleva o risco LGPD
  e um campo obrigatório travaria o cadastro de quem não a tem no dia da matrícula. Só a
  **chave** fica no aluno — os bytes vão para o `ArquivoStorage` (§6k), com allowlist de
  imagem e teto de 5 MB (`MIMES_FOTO`/`TAMANHO_MAXIMO_FOTO`). Trocar a foto **apaga a
  anterior**: imagem de criança que ninguém referencia é dado pessoal sem finalidade. Os
  bytes saem por `GET /alunos/{id}/foto`, autenticado, escopado por tenant e com
  `no-store` — **nunca por URL pública**. Casos de uso em
  `app/application/foto_aluno_use_cases.py`; cobertura em `tests/test_foto_aluno.py`.
  **O aluno nunca é apagado pelo painel:** "excluir" é `DesativarAluno` (soft delete), porque o
  registro de que ele estudou na escola sustenta histórico escolar, declarações e prestação de
  contas. `ReativarAluno` desfaz (rematrícula ou clique errado); desativar duas vezes não
  reescreve a data de saída. `sala_nome` é denormalizado só para exibição.
- **CRUD completo** + vínculo/desvínculo de responsáveis e filtro por série. Casos de uso em
  `app/application/cadastro_use_cases.py` (`CadastrarAluno`, `ListarAlunos`, `ObterAluno`,
  `AtualizarAluno`, `RemoverAluno`, `VincularResponsavelAoAluno`, `DesvincularResponsavelDoAluno`);
  a série informada é validada como pertencente ao tenant. Repositório `SqlAlunoRepository`.
- **Exclusão de série com alunos:** como `sala_id` é obrigatório, `RemoverSala` exige
  `mover_para=<sala_id>`, que **transfere** os alunos para outra série (validada no tenant,
  diferente da removida) antes de apagar a original; série vazia é removida sem cerimônia.
  **Não existe mais a opção de apagar os alunos junto** — era o caminho mais fácil da tela
  destruindo histórico. No painel, o diálogo permite **criar a série destino** na hora
  (reusando `POST /salas`).
- **Rotas** em `app/interfaces/api/cadastro.py`: `alunos` (POST · GET `tenant/{tenant_id}` com
  `?sala_id=` opcional), `alunos/{id}` (GET/PUT/DELETE), `alunos/{id}/responsaveis`
  (POST vincular · DELETE `/{contato_id}` desvincular) e `DELETE /salas/{id}?mover_para=` para a
  exclusão de série com transferência.
- **Painel:** `web/app/admin/alunos/` — cadastro, edição (série + situação ativo/ex-aluno),
  gestão de responsáveis e filtro por série. O seed cria um aluno por sala demo.
- A remoção de tenant (`SqlTenantRepository.remover`) apaga `aluno_responsaveis` → `alunos` na
  cascata explícita.

### 6c-ter. Cobertura de contatos da turma (alerta + aviso ao professor)

- **Cobertura:** uma turma (`Sala`) informa quantos **alunos ativos** estão **sem nenhum
  responsável (`Contato`) com telefone** vinculado — `Aluno.tem_contato` é falso quando nenhum
  responsável tem telefone preenchido. Ex-alunos (`ativo=False`) são ignorados. O value object
  `CoberturaContatosSala` (`total_alunos`, `alunos_sem_contato`, `total_sem_contato`) consolida o
  alerta "X alunos na turma, Y sem contato de responsável".
- **Casos de uso** em `app/application/cadastro_use_cases.py`: `CoberturaDeContatosDaSala` (uma
  turma, com a lista de alunos descobertos), `ResumoCoberturaDasSalas` (todas as turmas do tenant,
  carregando os alunos uma vez para evitar N+1) e `NotificarProfessorContatosFaltantes`, que envia
  um **texto livre pelo `MessageChannel`** ao WhatsApp do professor listando os faltantes (falha se
  não há nenhum). **Dor de campo:** hoje pedem ao professor para coletar os contatos e ele esquece.
- **Rotas** em `app/interfaces/api/cadastro.py`: `GET /salas/tenant/{tenant_id}/cobertura`
  (resumo de todas), `GET /salas/{id}/cobertura?tenant_id=` (detalhe) e
  `POST /salas/{id}/notificar-professor` (corpo: `telefone`, `mensagem` opcional).
- **Painel:** `web/app/admin/turmas/` — badge ⚠ na lista de turmas e, no detalhe da turma, um alerta
  com os alunos sem contato e o botão **"Notificar professor"** (modal pedindo o WhatsApp do
  professor + mensagem opcional). O seed cria um "Aluno Sem Contato" na primeira turma demo.

### 6c-quinquies. Professores (CRUD + atribuição à série)

- **`Professor`** por tenant. Nasceu enxuto — só `nome` e `telefone` — e ganhou o
  **cadastro funcional** em 12/ago/2026 (migration `0032_professor_cadastro_completo`):
  `cpf`, `data_nascimento`, `matricula`, `endereco`, `telefone_2`, `email`,
  `educacao_fisica` e `titular`. Único por `(tenant_id, telefone)`
  (migration `0008_professores`, tabela `professores`) **e** por `(tenant_id, cpf)` —
  este último num **índice UNIQUE parcial** (`WHERE cpf <> ''`), porque o default é `''`
  e um UNIQUE simples permitiria um só professor sem CPF cadastrado.
  - **`titular=False` significa eventual**, e não é rótulo: é a lista que a chamada de
    eventual (§I1) recebia digitada à mão a cada aviso de falta.
    `ListarEventuaisDisponiveis` (`GET /professores/tenant/{id}/eventuais`) devolve os
    eventuais **com telefone** — quem não tem número não é chamável, e listá-lo faria a
    secretaria "convocar" quem não recebe. A escolha de quem chamar segue humana.
  - **`ativo` é o vínculo vivo com a escola** (migration `0038_impressao_whatsapp`).
    Desligado, o professor sai das chamadas de eventual e **o número dele deixa de ser
    reconhecido no inbound** — deixa de mandar arquivo direto para a fila de impressão
    (§6g/B1). Não é o mesmo que remover: o cadastro sustenta o histórico da fila e o
    relatório mensal de cópias.
  - **`telefone` é o número da escola** (mural, recados, chamada de eventual);
    **`telefone_2` é emergência e não recebe disparo nenhum** — dois números ativos no
    canal entregariam a mesma mensagem duas vezes. A tela diz isso em texto.
  - **Só `nome` e `telefone` são obrigatórios.** Exigir CPF e matrícula de saída travaria o
    cadastro de quem já está dando aula; o bloco funcional é recolhido por padrão na
    criação e aberto na edição.
  - Formatos normalizados em `app/application/validacao.py` (CPF com dígitos
    verificadores conferidos e sequências repetidas recusadas, datas em ISO aceitando
    `DD/MM/AAAA`, e-mail e telefone em E.164). O módulo é compartilhado — responsáveis e
    alunos usam o mesmo.
  - **O telefone principal também é normalizado** desde 12/ago/2026. Ele escapava:
    `telefone_2` e `telefone_trabalho` passavam por `_e164_ou_erro`, mas o número que
    **é a chave da conversa** era gravado como foi digitado. "(15) 99999-0000" no banco
    faz o inbound não reconhecer a pessoa (o webhook entrega o remetente em E.164), a
    Graph API recusar o envio, e a checagem de duplicidade comparar formatos diferentes
    do mesmo número. A normalização vem **antes** da checagem, senão a mesma família
    entra duas vezes. Vazio segue aceito: professor sem número existe, e responsável sem
    telefone é o que a cobertura de contatos (§6c-ter) acusa.
  - **Máscara é conforto de digitação, não contrato de dado** (`web/lib/mascaras.ts` +
    `web/components/ui/campos.tsx`): CPF, telefone, RA e data ganham formato na tela,
    mas quem decide o que é gravado continua sendo o back-end. A **data deixou de ser
    `<input type="date">`** — ele desenha no formato do *sistema operacional*, e numa
    máquina em inglês a secretaria via `mm/dd/aaaa`; 03/04 vira 3 de abril ou 4 de março
    dependendo de quem olha, e data de nascimento trocada é matrícula errada. O RA fica
    **sem agrupamento** de propósito: o formato varia por estado, e pontuar no molde
    errado é pior do que não pontuar.
- **Vínculo professor ↔ série:** o relacionamento mora na **série**, via
  **`Sala.professor_id`** (FK `salas.professor_id` → `professores.id`, `ON DELETE SET NULL`).
  Assim uma **série tem no máximo um professor**, e um **professor pode conduzir várias séries**
  (1:N). Remover o professor apenas **desvincula** as séries (não as apaga). `Sala.professor_nome`
  é denormalizado só para exibição.
- **Casos de uso** em `app/application/cadastro_use_cases.py`: `CadastrarProfessor` (valida
  telefone único), `ListarProfessores`, `ObterProfessor`, `AtualizarProfessor`,
  `RemoverProfessor`; e a atribuição via `SalaRepository.definir_professor` —
  `AtribuirProfessorASala` (define/troca; valida que o professor é do tenant),
  `RemoverProfessorDaSala` (`professor_id` ← `NULL`) e `ListarSeriesDoProfessor`. Repositório
  `SqlProfessorRepository`.
- **Rotas** em `app/interfaces/api/cadastro.py`: `professores` (POST · GET `tenant/{tenant_id}`),
  `professores/{id}` (GET/PUT/DELETE), `professores/{id}/series` (GET) e
  `PUT /salas/{id}/professor` (corpo `professor_id`; `null` desvincula).
- **Painel:** `web/app/admin/professores/` — cadastro/edição/exclusão, atribuição do professor
  responsável por série e a lista das séries de cada professor. Os campos funcionais moram em
  `web/components/admin/CamposProfessor.tsx`, reusado pelo formulário e pelo modal de edição.
  O seed cria "Prof. Carla Mendes" (titular, atribuída às séries demo) e
  "Prof. Rita Alencar" (**eventual**), para a chamada de falta ter candidatos em vez de uma
  tela vazia na demonstração.
- A remoção de tenant (`SqlTenantRepository.remover`) apaga, na cascata explícita, `sala_contatos`
  → `salas` → `professores` (antes inexistente para `salas`; necessário pelas novas FKs).

### 6c-quater. Importação de alunos em massa (planilha/PDF + LLM)

- **Fluxo em duas etapas** (revisar antes de gravar), em
  `app/application/importacao_use_cases.py`:
  1. **Prévia** (`PrevisualizarImportacaoAlunos`): o texto bruto da planilha/PDF vai à
     `LLMProvider`, que **normaliza e estrutura** os alunos (nomes, telefones em E.164, série).
     O resultado é **validado em código** (a LLM não é fonte de verdade) e devolvido para
     revisão — **nada é persistido**. Telefones via `normalizar_telefone` (E.164 BR);
     séries citadas inexistentes no tenant são marcadas `serie_nova`.
  2. **Confirmação** (`ConfirmarImportacaoAlunos`): recebe as linhas revisadas e persiste de
     forma **determinística e sem LLM** — resolve/cria `Sala` (se `criar_series_ausentes`),
     reaproveita/cria `Contato` por telefone (dedupe) e cadastra os `Aluno`s com responsáveis.
     Linhas inválidas e séries ausentes (sem permissão de criar) são **ignoradas**.
- **Value objects** (`entities.py`): `ResponsavelImportado`, `LinhaImportacaoAluno`
  (`erros`/`avisos`/`serie_nova`/`valido`), `PreviaImportacaoAlunos`,
  `ResultadoImportacaoAlunos`. Tudo **escopado por tenant**.
- **LLM:** usa a porta `LLMProvider` existente (sem novo SDK). O prompt leva o marcador
  `IMPORTACAO_ALUNOS_JSON_V1`; o `FakeLLMProvider` (demo sem chaves) reconhece o marcador e
  converte CSV/TSV em JSON, mantendo o fluxo demonstrável.
- **Rotas** em `app/interfaces/api/cadastro.py`: `POST /alunos/importar/previa`
  (corpo: `tenant_id`, `conteudo`) e `POST /alunos/importar/confirmar`
  (corpo: `tenant_id`, `linhas`, `criar_series_ausentes`). A confirmação **revalida no
  servidor** (não confia no cliente).
- **Painel:** `web/app/admin/alunos/` — card "Importar alunos em massa" → modal com upload
  (`.csv/.tsv/.txt`) ou colar texto → tabela de prévia (badge "nova" para séries, status por
  linha, criar séries ausentes) → resultado.
