# Observabilidade — histórico, auditoria e painel de logs

> Parte do guia do TI-Escolar — índice em [`CLAUDE.md`](../../CLAUDE.md).
> A numeração das seções (§6a, §9c, …) é a original: as referências cruzadas
> espalhadas pelos outros documentos continuam valendo.

## 13. Observabilidade / histórico (admin da escola)

Três visões consultáveis no painel da escola (e pelo super admin, via `_exige_acesso_tenant`),
sob a seção **HISTÓRICO** da sidebar (`web/app/admin/historico/`). Tudo escopado por `tenant_id`.

- **Histórico de conversas** (`/historico/conversas`): lista as **sessões** de conversa e abre o
  diálogo completo (mensagens **recebidas** dos responsáveis + **respostas da LLM**, com as fontes
  RAG citadas). Reusa `ListarConversasDaEscola`/`ObterConversaDaEscola`
  (`GET /api/admin/escolas/{tenant_id}/conversas[/{conversa_id}]`).
  - **A conversa é uma sessão, não o fio eterno do responsável** (migration
    `0037_conversa_sessao`). Havia uma `Conversa` por `(tenant, contato)`, para sempre,
    garantida por um UNIQUE — que precisou sair, porque era ele que impedia a segunda
    sessão. A sessão **viva** é a não encerrada cuja última mensagem está dentro de
    `CONVERSA_JANELA_HORAS` (24, alinhado à janela da Meta — o relógio que o responsável
    percebe); fora disso a próxima mensagem abre outra. `0` desliga o recorte, como
    válvula.
  - **O sintoma visível era o histórico ilegível; o caro era invisível:** o contexto
    enviado à LLM crescia sem limite, carregando meses de assunto encerrado a cada
    mensagem — encarecendo a chamada e piorando a resposta (o modelo responde sobre a
    matrícula de março quando perguntam do uniforme de agosto). Como `historico()` já era
    por conversa, o recorte da sessão resolve isso sozinho.
  - **Resolver um atendimento (§6j) encerra a sessão.** Assunto fechado não deve carregar
    contexto para o próximo. Se o responsável voltar no mesmo assunto,
    `RegistrarRetornoDoResponsavel` reabre o atendimento.
  - A janela é renovada **a cada mensagem**, não a partir da primeira: uma conversa que
    dura a tarde inteira se partiria ao meio. A sessão vencida é encerrada **na hora em
    que se descobre** (dentro de `obter_ou_criar`), e não por job — o projeto não tem
    scheduler, e conversas mortas ficariam abertas até ele rodar.
- **Histórico de mensagens em massa** (`/historico/disparos`): lista os broadcasts com **template**,
  total de destinatários, **status de entrega** agregado e data; o detalhe mostra a entrega **por
  responsável** (nome, telefone, status `sent`/`delivered`/`read`/`failed`, atualizado em).
  `ListarBroadcastsDaEscola` resolve o nome do template em lote; `ObterBroadcastDaEscola` monta o
  detalhe (`GET /api/admin/escolas/{tenant_id}/broadcasts[/{broadcast_id}]`). Conecta-se à
  confirmação de recebimento (§9b: `.../nao-entregues`).
- **Auditoria de ações** (`/historico/auditoria`): log de **quem fez o quê e quando**, para
  rastreabilidade/compliance. A entidade `RegistroAuditoria` (`ator` ∈ {`usuario`, `llm`,
  `sistema`}, `acao`, `descricao`, `metadados` JSON) é persistida em `auditoria`
  (migration `0007_auditoria`) via porta `AuditLogRepository`. **Instrumentado:** ações de
  usuários logados no `app/interfaces/api/admin.py` (`login`, `usuario.criar`, `grupo.criar`,
  `broadcast.grupo.enviar`). Casos de uso `RegistrarAuditoria`/`ListarAuditoria`
  (`app/application/auditoria_use_cases.py`); auditar é **tolerante a falhas** (nunca derruba
  a ação auditada). Endpoint: `GET /api/admin/escolas/{tenant_id}/auditoria?limite=`.
  - **O ator é reidentificado na leitura** (12/ago/2026). `RegistroAuditoria.ator_nome` é
    um retrato do momento da ação e virou **fallback histórico**: `ListarAuditoria` recebe
    o `UsuarioRepository` e resolve o nome atual **em lote** (`por_ids`, uma consulta por
    página). Sem isso, um nome corrigido depois faria a mesma pessoa aparecer com dois
    nomes no log, e registro anterior ao campo ficaria anônimo para sempre.
  - **`ator_perfil_id` (não persistido) é o que autoriza o link** para `/admin/usuarios`.
    Só quem **ainda tem conta** o recebe: linkar para uma conta que não existe mais
    entregaria um 404 no lugar da resposta, e para LLM/sistema não há perfil nenhum. O
    `ator_id` é texto livre na porta (a LLM guarda telefone ali), então um valor que não
    é UUID simplesmente não tem perfil — não é erro.
  - **[Roadmap]** cobertura: as mutações de cadastro (alunos, responsáveis, professores,
    turmas) ainda **não** são auditadas, então a tela mostra pouco do que a secretaria
    faz no dia a dia.
  - ✅ **Ações da LLM auditadas no inbound real** (10/ago/2026): o inbound passou a usar
    `AtenderConversa`, que grava `llm.resposta` (pergunta/resposta resumidas, fontes,
    documentos) com `ator="llm"`. As ações da secretaria na fila de atendimento humano
    (§6j) também entram, como `atendimento.assumir` / `.responder` / `.resolver`.

---

## 16. Observabilidade — painel de Logs (super admin)

Painel **exclusivo do super admin** (`/admin/logs`), inspirado no Laravel Horizon: primeiro o
estado agregado da janela recente ("está tudo bem agora?"), depois a **fila de atendimentos do
WhatsApp**, e só então o log linha a linha. Distinto de §13 (auditoria), que registra **decisões
de negócio** e é escopado por escola; aqui é **operacional e cross-tenant** — traceback, rota,
latência —, material que não é para a secretaria.

- **Id de correlação por requisição** (`app/interfaces/middleware.py`): gerado ou herdado do
  `X-Request-Id`, guardado em `ContextVar` (para qualquer log emitido durante o atendimento
  carregá-lo) **e** no `request.state`. Devolvido no cabeçalho e no corpo de todo erro — é o
  código que o usuário informa ao suporte.
- **Coleta assíncrona** (`app/infrastructure/logs.py`): o `logging.Handler` apenas **enfileira**;
  uma tarefa de fundo drena em lote e grava em `logs_aplicacao` (migration `0027`). Gravar no
  caminho da requisição acoplaria a latência de cada resposta ao banco e, pior, um erro de banco
  durante o log de um erro de banco viraria recursão. Fila cheia **descarta o mais antigo** —
  perder log é ruim, travar o atendimento de um responsável para gravá-lo é pior.
- **Retenção** `LOG_RETENCAO_DIAS` (default 14), limpa a cada 6h pelo próprio gravador.
- **O que o painel mostra:** erros, alertas, requisições, taxa de erro, latência média e p95,
  rotas mais lentas, erros mais frequentes; a fila de `inbound_atendimento` (respondidas / em
  atendimento / falhas — §9e.1); e a listagem paginada com filtro por nível, módulo e texto,
  com o traceback expansível.
- **Saúde** (`ResumoLogs.saudavel`) exige zero erro **e** zero atendimento falho: um atendimento
  falho não aparece como erro HTTP, mas significa que um responsável escreveu e não foi
  respondido.
- **Endpoints** (`app/interfaces/api/logs.py`, guarda `_exige_super_admin`):
  `GET /api/admin/logs`, `/logs/resumo`, `/logs/atendimentos`.
- **Prontidão:** `GET /health/pronto` toca o banco (`SELECT 1`), separado do `/health`
  (liveness) — o `/health` respondia "ok" com o Neon inteiramente fora do ar.
- **Canal efetivo no `/health`:** o campo `canal` é o adaptador **realmente instanciado**
  (`canal_efetivo`, em `factories.py`), não o valor de `MESSAGE_CHANNEL`. Ecoar a env
  afirmaria de fora que o WhatsApp está no ar numa instância que subiu no canal demo por
  falta de token. Divergindo, o corpo ganha `canal_configurado` + `canal_alerta` e o boot
  loga o motivo em `error` — é o único momento em que alguém repara. Ver §9c e
  `docs/producao-whatsapp.md` §6.1.1.
- **[Roadmap] Alerta ativo:** ninguém é notificado de um erro; é preciso abrir o painel. É o que
  mantém o item 8 do checklist em ⚠️.

### 16a. Central de notificações do painel

O sininho da `Topbar` **não era um sininho**: um `<button>` sem `onClick`, com a bolinha
vermelha cravada no JSX — avisava sempre, inclusive com a fila zerada. Um alerta sempre
aceso é um alerta que ninguém olha.

- `web/components/admin/Notificacoes.tsx` consolida as fontes (`usePendencias`):
  responsáveis esperando (§6j) e documentos a conferir (§6k), via
  `GET .../atendimentos/tenant/{id}/pendentes` e `GET .../documentos/tenant/{id}/pendentes`.
- **Uma requisição por ciclo para o painel inteiro**: o polling saiu da `Sidebar` e o badge
  do menu passou a ler do mesmo hook, em vez de cada lugar que mostra número fazer o seu.
- **Alerta em tela só na subida** da contagem, com a aba aberta — e nunca na primeira
  leitura. Um toast que reaparece a cada polling vira ruído e a secretaria aprende a
  ignorar, que é o oposto do pedido. Aba escondida não gera requisição; voltar para ela
  reconfere na hora.
