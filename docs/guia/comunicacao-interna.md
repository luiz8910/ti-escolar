# Comunicação interna — Ondas 1, 2 e 3

> Parte do guia do TI-Escolar — índice em [`CLAUDE.md`](../../CLAUDE.md).
> A numeração das seções (§6a, §9c, …) é a original: as referências cruzadas
> espalhadas pelos outros documentos continuam valendo.

### 6g. Comunicação interna e atendimento — Onda 1 (cliente-âncora EM Rosa Cury)

Quatro features que reduzem a carga da secretaria e o atrito secretaria↔professor. **Não exigem
LLM novo:** reusam o RAG existente (que já chama o `LLMProvider`).

- **C1 · Respostas rápidas → RAG (`RespostaRapida`):** os "atalhos" da secretaria (chave +
  conteúdo), únicos por `(tenant_id, chave)`. Cada uma é **ingerida no RAG** (reusa
  `IngerirDocumento`; `fonte_id` liga à `FonteConhecimento` gerada) para o bot responder
  automaticamente; `ativo` controla a indexação. Casos de uso em
  `app/application/respostas_rapidas_use_cases.py` (criar/listar/obter/atualizar/remover; editar
  reindexa, remover/desativar apaga os trechos). Repositório `SqlRespostaRapidaRepository`
  (`repositories_conhecimento.py`). Rotas `app/interfaces/api/respostas_rapidas.py`
  (`/api/admin/respostas-rapidas`). Migration `0012_respostas_rapidas`. Seed com os 19 atalhos reais
  da Rosa Cury. Painel `web/app/admin/respostas-rapidas/`.
- **C2 · Aviso geral temporizado (`AvisoTemporizado`):** recado do dia com **janela de vigência**
  opcional (`inicia_em`/`expira_em`) e `ativo`. Enquanto **vigente** (`vigente_em`), é **anexado à
  resposta do bot** a quem inicia a conversa (integrado em `AtenderConversa`, via
  `AvisoTemporizadoRepository` opcional) — "sem mexer no celular". Casos de
  uso em `app/application/avisos_use_cases.py`. Repositório `SqlAvisoTemporizadoRepository`
  (`repositories_comunicacao.py`). Rotas `app/interfaces/api/avisos.py` (`/api/admin/avisos`).
  Migration `0013_avisos_temporizados`. Painel `web/app/admin/avisos/`.
- **B1 · Fila de impressão (`SolicitacaoImpressao`):** o professor envia um arquivo com parâmetros
  (`copias`, `colorido`, `frente_verso`, `observacao`); cai numa fila (`status` ∈ {`pendente`,
  `em_processo`, `concluida`, `cancelada`}) para a secretaria processar. `professor_id` FK a
  `professores` (`ON DELETE SET NULL`). Casos de uso em `app/application/impressao_use_cases.py`.
  Repositório `SqlSolicitacaoImpressaoRepository`. Rotas `app/interfaces/api/impressao.py`
  (admin: `/api/admin/impressao`) e submissão pelo próprio professor em
  `/api/professor/impressao`. Migration `0014_solicitacoes_impressao`. Painel
  `web/app/admin/impressao/`.
  - **O caminho principal virou o WhatsApp** (12/ago/2026, migration
    `0038_impressao_whatsapp`). O portal exige abrir o navegador, lembrar a senha e
    preencher um formulário para mandar a mesma lista de chamada que já está no celular.
    Agora o professor manda o arquivo **para o número da escola** e ele cai na fila.
  - **Quem decide é o cadastro:** `ProcessarInboundMeta` consulta
    `ProfessorRepository.por_telefone` e, achando um professor **ativo**, desvia a
    mensagem — mídia vira `SolicitacaoImpressao`, texto recebe orientação. **Nada disso
    passa pela LLM**: o assistente é dos responsáveis, e mandar quem dá aula para ele o
    faria ouvir sobre matrícula e horário de secretaria, cobrando inferência por isso.
    O contador `ResultadoInboundMeta.impressoes` fica à parte de `respondidas`
    justamente para esse fato aparecer no painel de logs (§16).
  - **`Professor.ativo` nasceu aqui** e não é enfeite: sem ele, "cadastrado" e "trabalha
    aqui" são a mesma coisa, e quem saiu seguiria mandando material direto para a
    impressora. Apagar o cadastro não substitui — a fila e o relatório mensal dependem
    dele para o histórico.
  - **Os bytes ficam com a escola** (`chave_storage` → `ArquivoStorage`, §6k): fila sem
    arquivo não imprime. Saem por `GET /impressao/{id}/arquivo`, autenticado e escopado
    por tenant, **nunca por URL pública**. `media_id` deduplica a reentrega do webhook —
    sem ele a Meta faria a secretaria imprimir duas vezes e debitaria a franquia em dobro.
  - **Cópias, cor e frente-e-verso saem da legenda por heurística** (`interpretar_legenda`),
    não por LLM — mesma escolha de `sugerir_categoria` (§6k). Sem número explícito o
    pedido nasce com **1 cópia e a confirmação diz isso**, em vez de inventar tiragem; e
    número acima de `COPIAS_MAXIMAS_INFERIDAS` (500) é descartado, porque "Planejamento
    2026" na legenda não é pedido de 2.026 folhas. A fila marca `origem=whatsapp` para a
    secretaria saber que aquele número foi lido, não preenchido.
  - **Estourar a franquia avisa, não recusa** (`ConsultarSaldoImpressao` +
    `SaldoImpressao`): um bot barrando a impressão trava a aula, e quem decide é a
    secretaria. O saldo é **derivado** das solicitações do mês, nunca um contador
    guardado — um contador divergiria da fila no primeiro cancelamento. É apurado
    **depois** de gravar, senão a resposta mostraria o saldo anterior a quem está no
    limite. Cobertura: `tests/test_impressao_whatsapp.py`.
- **A1 · Mural do professor (`Recado` + `LeituraRecado`):** a secretaria publica recados; o
  professor tem **login próprio** e **confirma a leitura** ("ticado"). A secretaria vê quem leu /
  quem não leu e **re-notifica por WhatsApp** os não-lidos (`ReNotificarRecadoNaoLido` via
  `MessageChannel`). **Autenticação do professor:** `Professor.senha_hash` (PBKDF2, definida pela
  secretaria em `CadastrarProfessor`/`AtualizarProfessor` via `senha`); `AutenticarProfessor` +
  `POST /api/professor/login` emite JWT com `papel="professor"`; a dependência
  `professor_autenticado` revalida no banco. Casos de uso em `app/application/mural_use_cases.py`.
  Repositório `SqlMuralRepository` (`repositories_comunicacao.py`). Rotas: admin
  `app/interfaces/api/mural.py` (`/api/admin/recados` + `.../leitura`, `.../renotificar`) e
  professor `app/interfaces/api/professor.py` (`/api/professor/recados`, `.../leitura`).
  Migration `0015_mural_professor` (adiciona `professores.senha_hash` + `recados` +
  `leituras_recado`). Painel: secretaria `web/app/admin/mural/`; portal do professor
  `web/app/professor/` (login + mural + solicitar impressão). Seed: professor demo com senha
  (`DEMO_PROFESSOR_SENHA`, default `prof123`) e um recado.

### 6h. Consolidação interna — Onda 2 (cliente-âncora EM Rosa Cury)

Quatro features que consolidam a comunicação interna e o ciclo de vida escolar. Nenhuma
exige LLM novo. Todas escopadas por `tenant_id`.

- **A2/A4 · Canal interno professor→secretaria + roteamento por assunto
  (`SolicitacaoInterna`):** o professor abre recados/pedidos pelo sistema (não pelo
  WhatsApp pessoal), com **`categoria`** ∈ {`secretaria`, `gestao`, `pedagogico`} que
  **roteia** o assunto (§A4) e **`status`** ∈ {`aberta`, `em_andamento`, `resolvida`,
  `cancelada`}. A escola responde no próprio registro (`resposta`/`respondido_em`) e pode
  **notificar o professor por WhatsApp** (`MessageChannel`). Casos de uso em
  `app/application/comunicacao_interna_use_cases.py`; repositório
  `SqlSolicitacaoInternaRepository` (`repositories_comunicacao.py`). Rotas: admin
  `app/interfaces/api/comunicacao_interna.py` (`/api/admin/solicitacoes-internas`) e
  professor em `professor.py` (`/api/professor/solicitacoes`). Migration
  `0016_solicitacoes_internas`. Painel: secretaria `web/app/admin/solicitacoes/`; professor
  em `web/app/professor/`.
- **A3 · Canal pai↔professor mediado (`MensagemMediada`):** o professor conversa com o
  responsável **sem expor o número pessoal** — ao responder, a mensagem sai pelo número da
  escola (`Tenant.whatsapp_numero` como `remetente` do `MessageChannel`) e é registrada; as
  mensagens do responsável entram pelo mesmo canal (`RegistrarMensagemDoResponsavel`, ponto
  de entrada para o webhook/secretaria) e aparecem no painel do professor. Uma "conversa" é
  o par (`professor_id`, `contato_telefone`). Casos de uso em
  `app/application/mediacao_use_cases.py`; repositório `SqlMediacaoRepository`. Rotas:
  professor `/api/professor/mensagens` (listar interlocutores/thread, enviar) e admin
  `app/interfaces/api/mediacao.py` (`/api/admin/mediacao` — registrar recebida + acompanhar).
  Migration `0017_mensagens_mediadas`. Painel: `web/app/professor/`.
- **B2 · Cota e relatório de impressões (`CotaImpressao`):** **franquia mensal por
  professor** (`limite_mensal`; `<= 0` = sem limite). O relatório mensal
  (`RelatorioImpressaoMensal`, competência `YYYY-MM`) agrega as `SolicitacaoImpressao` **não
  canceladas** por professor, cruza com a cota e sinaliza quem **excedeu** ("bateu a meta").
  Casos de uso em `app/application/impressao_use_cases.py` (estende a fila §B1); repositório
  `SqlCotaImpressaoRepository`. Rotas em `app/interfaces/api/impressao.py`
  (`/api/admin/impressao/cotas`, `/api/admin/impressao/relatorio`). Migration
  `0018_cota_impressao`. Painel: `web/app/admin/impressao/relatorio/`.
- **F1 · Progressão de série + ciclo de vida do responsável:** na virada de ano,
  `PromoverSerie`/`PromoverTurmas` movem os alunos **ativos** para a série seguinte (ou os
  marcam como ex-alunos na última série — `destino=None`), e
  `SincronizarSituacaoDosResponsaveis` alinha o `Contato.ativo` com a situação dos alunos.
  - **A regra é simétrica:** inativa quem tem alunos vinculados e **todos** já são
    ex-alunos; **reativa** quem estava inativo e voltou a ter algum aluno ativo. A
    reativação não é enfeite — sem ela a automação seria uma armadilha: a rematrícula
    devolveria o aluno e deixaria a família inativa, parando de receber aviso da escola
    sem ninguém perceber. É seguro porque `Contato.ativo` **só é mexido por este caso de
    uso** (não há desativação manual de responsável no painel). Responsáveis sem nenhum
    aluno vinculado são preservados; idempotente.
  - **Roda por automação, não por clique** (apontamento de 10/08). O gatilho está nos dois
    momentos em que a família de fato muda de estado: no fim de `PromoverTurmas` e em
    `DesativarAluno`/`ReativarAluno`. Um cron diário passaria 364 dias por ano
    recalculando nada — e o projeto ainda não tem scheduler.
  - `contato_ids` recorta o trabalho: a virada de ano varre a escola; a desativação de um
    aluno olha só os responsáveis dele.
  - A rota `POST /progressao/inativar-responsaveis` **permanece como reprocessamento** —
    para conferir a escola inteira depois de uma importação em massa ou de um ajuste feito
    fora do painel. A URL manteve o nome antigo, mas a operação é bidirecional.
  Casos de uso em `app/application/progressao_use_cases.py`. Rotas em
  `app/interfaces/api/progressao.py`.
  Migrations `0019_contato_ativo` (flag `contatos.ativo`). Painel:
  `web/app/admin/progressao/`.
- **J1 · Acesso web por link:** princípio transversal já atendido pelo painel Next.js (App
  Router) e pelo **portal do professor** (`web/app/professor/`), acessíveis por link direto —
  sem dependência de app nativo. Reforçado nesta onda com as novas páginas web.
- **Seed:** o tenant demo ganha uma `SolicitacaoInterna` de exemplo e uma `CotaImpressao`
  (3.000 cópias/mês) para o professor demo.

### 6i. Digitalização documental — Onda 3 (cliente-âncora EM Rosa Cury)

Cinco features de digitalização e resiliência documental. Nenhuma exige LLM novo (D3 reusa
a porta `LLMProvider`, como a importação em massa). Todas escopadas por `tenant_id`.

- **I1 · Aviso de falta + chamada de eventual (`AvisoFalta`):** o professor avisa a falta
  pelo sistema (`RegistrarFaltaProfessor`; também via portal `POST /api/professor/faltas`);
  a secretaria dispara o pedido de **substituto** para uma lista de candidatos
  (`ChamarEventual` — envia texto pelo `MessageChannel`, a partir do número da escola, e
  registra `eventuais_chamados`), confirma quem cobre (`ConfirmarEventual` → `coberta`) ou
  cancela (`CancelarFalta`). `status` ∈ {`aberta`, `coberta`, `cancelada`}; `professor_id`
  FK a `professores` (`ON DELETE SET NULL`). Casos de uso em
  `app/application/falta_use_cases.py`; repositório `SqlAvisoFaltaRepository`
  (`repositories_onda3.py`); rotas admin `app/interfaces/api/faltas.py`
  (`/api/admin/faltas`). Migration `0020_avisos_falta`.
- **H1 · Exportar conversa para fins legais (`ConversaExportada`):** `ExportarConversaLegal`
  monta um **documento textual** de uma conversa (opcionalmente recortada por período) com
  cabeçalho institucional e marca de exportação, para anexar a processo/prontuário. Reusa
  `ConversaRepository` (`obter_conversa`/`mensagens`) + `TenantRepository`. Rota
  `GET /api/admin/escolas/{tenant_id}/conversas/{conversa_id}/exportar?inicio=&fim=`
  (`app/interfaces/api/exportacao.py`, guard `_exige_acesso_tenant`). Sem migration.
- **D1/D2/D3 · Ficha de matrícula digital (`FichaMatricula`):** ficha rica (frente + verso)
  1:1 com `Aluno`, com os campos **obrigatórios/sensíveis** (§D2): `cor_raca` (obrigatório,
  validado no caso de uso), Bolsa Família/NIS, deficiência/necessidade especial, laudo/CID,
  restrição alimentar, alergia; e as autorizações (van, retirada, imagem). Persistida como
  **JSON `conteudo`** (todos os campos, mais `dados_extra` para campos configuráveis por
  escola — §D1). CRUD em `app/application/ficha_use_cases.py` (`SalvarFichaMatricula` upsert,
  `ObterFichaMatricula`, `RemoverFichaMatricula`). **Leitura por IA (§D3):** fluxo
  prévia→confirmação — `PrevisualizarFichaMatricula` manda o texto/OCR à `LLMProvider`
  (marcador `FICHA_MATRICULA_JSON_V1`; o `FakeLLMProvider` o reconhece), **valida em código**
  e devolve para revisão; `ConfirmarFichaMatricula` persiste. Repositório
  `SqlFichaMatriculaRepository`; rotas `app/interfaces/api/fichas.py` (`/api/admin/fichas`,
  `.../importar/previa`, `.../importar/confirmar`). Migration `0021_ficha_matricula`.
  - **A ficha ganhou tela em 12/ago/2026** (`web/components/admin/FichaMatricula.tsx`,
    aberta pelo botão "Ficha" em `web/app/admin/alunos/`). Ela existia só como API desde a
    Onda 3 — dava para gravar por endpoint e nada mais.
  - **Obrigatórios ao salvar a ficha**, não ao cadastrar o aluno: `cor_raca`, `cpf`,
    `ra_rm`, `data_nascimento`, `endereco` e `sexo` (os campos com asterisco da ficha
    física). A importação em massa (§6c-quater) cria aluno só com nome e série, e exigir
    CPF ali travaria o caminho que a escola mais usa. O erro lista **todos os que faltam
    de uma vez** — uma mensagem por campo faria a secretaria salvar seis vezes.
  - **`laudo_status`** ∈ {`nao`, `sim`, `em_investigacao`} acompanha `laudo_cid`, como as
    três caixas da ficha física. Texto livre não distinguia "não tem laudo" de "está em
    investigação", e a segunda é pendência que a escola acompanha. Fora de `sim`, o CID é
    **limpo**: deixá-lo pendurado faria a ficha afirmar um diagnóstico recém-negado.
  - **A filiação é derivada**, não digitada. `filiacao1_*`/`filiacao2_*`/
    `responsavel_legal`/`termo_guarda` são preenchidos a partir dos `Contato`s vinculados
    ao aluno (mãe e pai nas duas primeiras linhas; o responsável legal na linha do termo
    de guarda). Eram uma segunda cópia dos mesmos dados, livre para divergir; o que vier
    no corpo da requisição é ignorado.
- **E1 · Matrícula self-service pelo WhatsApp (`SolicitacaoMatricula`):** o responsável
  inicia a matrícula; `IniciarMatricula` cria a solicitação (idempotente por telefone) e
  `montar_mensagem_documentos` devolve a **lista de documentos exigidos** (reusa os atalhos
  de inscrição). `AnexarDocumentoMatricula` registra os arquivos enviados (`documentos` em
  JSON) e avança para `documentos_enviados`; `AtualizarStatusMatricula` conduz até
  `concluida`/`cancelada`. `status` ∈ {`iniciada`, `documentos_enviados`, `em_analise`,
  `concluida`, `cancelada`}. Casos de uso em `app/application/matricula_use_cases.py`;
  repositório `SqlSolicitacaoMatriculaRepository`; rotas `app/interfaces/api/matricula.py`
  (`/api/admin/matriculas`). Migration `0022_solicitacoes_matricula`.
- **G1 · Limite de caracteres na mensagem do pai:** `AtenderConversa` recebe
  `max_chars` (config `MENSAGEM_PAI_MAX_CHARS`, default 1000; 0 desativa); acima do limite,
  o bot pede objetividade **sem acionar a LLM** (assunto de secretaria pede recado curto).
- **Seed:** o tenant demo ganha um `AvisoFalta` (professor demo), uma `FichaMatricula` do
  primeiro aluno demo (com `cor_raca`) e uma `SolicitacaoMatricula` de exemplo.
- **Remoção de tenant** (`SqlTenantRepository.remover`): a cascata explícita passa a apagar
  `fichas_matricula` e `solicitacoes_matricula` (antes dos alunos) e `avisos_falta` (antes
  dos professores), pois as FKs a `tenants` não têm `ON DELETE CASCADE`.
