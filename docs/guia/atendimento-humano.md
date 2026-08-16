# Atendimento humano — a fila da secretaria

> Parte do guia do TI-Escolar — índice em [`CLAUDE.md`](../../CLAUDE.md).
> A numeração das seções (§6a, §9c, …) é a original: as referências cruzadas
> espalhadas pelos outros documentos continuam valendo.

### 6j. Atendimento humano — o assistente entrega a conversa à secretaria

O produto passou a **atender** com o inbound real (§9e.1), mas atender não é responder
tudo: matrícula específica, reclamação, ocorrência com aluno — há assunto que exige
decisão de gente. Esta é a ponte, e ela tem **três regras que valem mais que o código**:

1. **Nunca encaminhar de saída.** O assistente tenta responder primeiro. Encaminhamento na
   primeira mensagem transformaria o produto num formulário de contato caro.
2. **Perguntar antes.** Ao desistir, ele *oferece* ("quer que eu chame alguém da
   secretaria?") e só o "sim" do responsável abre o atendimento. Exceção: quem já pediu
   uma pessoa explicitamente — aí a pergunta é burocracia.
3. **Respeitar o expediente.** Fora do horário o atendimento **entra na fila mesmo assim**
   (recusar perderia justamente o recado de quem escreve à noite), mas o que se promete ao
   responsável é o próximo dia útil.

Do lado do responsável **não existe transferência**: é a mesma conversa de WhatsApp, com a
resposta saindo pelo mesmo número da escola. Quem muda é quem escreve do outro lado.

- **Quem atende:** não há entidade nova. É o `Usuario` com `papel = tenant_admin` — a mesma
  conta que entra no painel. O que faltava era a tela: `web/app/admin/usuarios/`
  (+ `AtualizarUsuario` e `PUT /api/admin/usuarios/{id}`), porque até aqui criar uma
  funcionária exigia bater na API à mão. **Não há "excluir":** quem sai é **desativada**
  (`ativo=False`), perde o acesso na requisição seguinte e mantém o histórico do que
  respondeu. Editar não muda `papel` nem `tenant_id` — seria a porta para um admin de
  escola se promover a super admin.
- **`AtendimentoHumano`** (migration `0029_atendimento_humano`, tabela
  `atendimentos_humanos`): `status` ∈ {`oferecido`, `aberto`, `em_atendimento`,
  `resolvido`, `descartado`}; só `aberto`/`em_atendimento` ocupam a fila. `OFERECIDO` é o
  estado que separa esta feature de um encaminhamento cego, e a razão
  **oferecido × descartado** é o termômetro de o assistente estar desistindo cedo demais.
  `ultima_mensagem_responsavel_em` é a base da **janela de 24h** da Meta: sem esse carimbo o
  atendente escreve, a Graph API recusa o texto livre e a resposta some.
- **Expediente da escola (`Tenant.expediente_dias/_inicio/_fim/_timezone`):** o horário da
  secretaria é **campo estruturado, não texto na base de conhecimento**. A base responde a
  quem *pergunta* o horário (RAG); aqui o horário **governa comportamento**, e se o recall
  falhasse o assistente prometeria atendimento imediato às 23h. Propriedades de domínio
  `dentro_do_expediente`, `proxima_abertura`, `descricao_expediente`, `hora_local`. Default
  = o da EM Rosa Cury (seg–sex, 7h30–17h). **Limitação declarada:** feriado e recesso não
  são modelados — emenda de feriado promete atendimento que não acontece.
- **As travas são código, não prompt.** `escalar_para_secretaria` valida em
  `EscalarParaSecretaria`: (a) mínimo de `MIN_RESPOSTAS_ANTES_DE_ENCAMINHAR` (2) respostas
  do assistente na conversa, salvo pedido explícito; (b) oferta registrada antes do
  encaminhamento. A recusa levanta `EncaminhamentoRecusado`, cuja mensagem **volta ao
  modelo como orientação** (não como erro) — ele então responde ou pergunta, em vez de
  encaminhar. Oferta sem resposta vence em `OFERTA_VALIDA_HORAS` (24) e vira `descartado`,
  senão uma oferta ignorada em março autorizaria encaminhamento direto em agosto.
- **Duas ferramentas** no `AtenderConversa`: `oferecer_atendimento_humano` (registra a
  intenção e manda perguntar) e `escalar_para_secretaria` (`motivo`, `pedido_explicito`).
  Diretrizes correspondentes em `montar_sistema_agente`.
- **O assistente cala quando a secretaria assume.** Com atendimento `na_fila`,
  `AtenderConversa` só registra a mensagem, renova a janela de 24h e devolve **texto
  vazio** — o inbound entende isso como "não responder" e conta em
  `ResultadoInboundMeta.silenciadas`, separado de `respondidas` para o silêncio deliberado
  não parecer falha no painel de logs (§16). Sem essa trava, o responsável receberia duas
  respostas da escola se contradizendo pelo mesmo número.
- **Responder** (`ResponderAtendimento`): envia **antes** de gravar — gravar primeiro
  deixaria no histórico uma resposta que o responsável nunca recebeu, e a escola acreditaria
  ter respondido. A mensagem entra na mesma `Conversa` como `Mensagem` de autor
  `atendente` (+ `autor_nome`, migration `0029`), pelo `Tenant.remetente_canal`. Responder é
  assumir; dois atendentes no mesmo caso é recusado.
- **Fora da janela de 24h (§A9):** a resposta sai por **template utility aprovado**
  (`TEMPLATE_RETOMADA_ATENDIMENTO`, buscado por `TemplateRepository.por_nome`). Sem template
  aprovado, o painel **recusa com erro explícito** em vez de deixar a mensagem sumir na
  Graph API. O seed cria `retomada_atendimento` como **pendente** de propósito: enquanto a
  Meta não aprovar, o comportamento honesto é recusar.
  - **O default da env deixou de ser vazio** em 12/ago/2026 (agora
    `"retomada_atendimento"`). O vazio era a trava de "não sabemos se está aprovado", e
    custava um preenchimento manual no Render a cada deploy. Com o catálogo (§9a-bis) quem
    responde "dá para enviar?" é o **status do template**, que vem da Meta pelo webhook ou
    pela sincronização — e `_template_de_retomada` já exige `APROVADO`. A trava ficou no
    lugar certo: um fato verificado, não uma variável que alguém precisa lembrar.
- **Casos de uso** em `app/application/atendimento_humano_use_cases.py`
  (`OferecerAtendimentoHumano`, `EscalarParaSecretaria`, `RegistrarRetornoDoResponsavel`,
  `ListarAtendimentos`, `ContarAtendimentosPendentes`, `Assumir`/`Responder`/`Resolver`/
  `ReabrirAtendimento`), com a fachada **`MesaDeAtendimento`** — que existe para não
  despejar cinco colaboradores no construtor de `AtenderConversa`. Repositório
  `SqlAtendimentoHumanoRepository` (`repositories_comunicacao.py`); rotas
  `app/interfaces/api/atendimento_humano.py` (`/api/admin/atendimentos`), com
  `_exige_tenant_ativo` na resposta (consome canal).
- **Nome do responsável resolvido na leitura.** `AtendimentoHumano.contato_nome` é um
  retrato do nascimento do atendimento — e o caso comum é a pessoa ainda não estar
  cadastrada quando escreve, então o card ficava com o telefone cru para sempre, mesmo
  depois de a secretaria cadastrá-la. `ListarAtendimentos`/`ObterAtendimento` recebem o
  `ContatoRepository` e renomeiam **em lote** (`ContatoRepository.por_telefones`, uma
  consulta por página); o campo persistido virou fallback histórico.
- **Painel:** `web/app/admin/atendimentos/` (fila Na fila / Meus / Resolvidos, **refresh
  automático** — 20 s na lista, 10 s na conversa aberta, pausado com a aba escondida e em
  falha silenciosa, sem toast —, **rolagem que acompanha a conversa** e **aviso sonoro**
  quando o responsável escreve, motivo já
  resumido pelo assistente, tempo de espera, selo de fora do expediente, contador da janela
  de 24h e a thread completa com caixa de resposta) e **badge de contagem no `Sidebar`**
  (polling de 20s em `/pendentes`) — é a notificação in-app. Expediente editável no
  cadastro de escola (`components/admin/CamposExpediente.tsx`).
- **A conversa aberta se comporta como conversa** (12/ago/2026). Duas correções na
  mesma tela:
  - **Rolagem só quando a leitura está no fim.** A cada 10 s o polling traz mensagem
    nova; rolar à força arrancaria do lugar quem subiu para reler o que o responsável
    disse. Abrir uma conversa cai no fim direto, sem animação.
  - **Aviso sonoro** (`web/lib/som.ts`), sintetizado em Web Audio — dois toques curtos,
    ganho baixo, cauda de 0,22 s. Toca **só** quando cresce o número de mensagens *do
    responsável*, nunca ao abrir a conversa (ali toda mensagem é "nova" para o
    componente) nem quando a própria atendente envia. **Desligável**, com a preferência
    por navegador: som que não se desliga no produto é desligado no sistema operacional,
    e aí nenhum aviso chega — o oposto do pedido.
- **Cobertura:** `tests/test_atendimento_humano.py` (28 testes: expediente e a armadilha do
  "amanhã" no sábado, as duas travas, oferta vencida, idempotência, trava do atendente,
  janela de 24h com e sem template, silêncio do assistente, isolamento entre escolas).
- **[Roadmap]** notificar o atendente por WhatsApp/e-mail (exige `Usuario.telefone`);
  feriados no expediente.

### 6l. Saída antecipada do aluno — a exceção declarada à regra de perguntar antes

O responsável escreve "preciso buscar minha filha às 11h". Isso **sempre** exige decisão
de gente: a escola precisa saber quem retira a criança e autorizar. E é sensível ao
relógio — perguntar "quer que eu chame alguém da secretaria?" gastaria justamente os
minutos que importam, para uma resposta que seria sempre "sim".

Por isso a ferramenta `registrar_saida_antecipada` **abre o chamado direto**, sem oferta e
sem esperar as duas respostas mínimas (§6j). A exceção é do domínio, não do prompt:
`EscalarParaSecretaria` ganhou `abertura_direta`, distinto de `pedido_explicito` —
naquele quem pede é o responsável, neste é a **regra da escola**. Deixá-la só no texto do
prompt significaria que o modelo pode ignorá-la, e a saída antecipada voltaria a ser uma
oferta.

- **O que não se dispensa são dois dados**: o **nome do aluno**, sempre; e o **nome de
  quem está pedindo**, quando `ContatoRepository.por_telefone` não reconhece o número.
  Sem eles o card chegaria como "alguém quer buscar alguém", e a secretaria teria de
  reabrir a conversa para perguntar o que o assistente já poderia ter perguntado. Faltando
  um deles, a ferramenta **não abre nada** — devolve ao modelo a orientação de perguntar.
- **Quem já está cadastrado não é interrogado sobre o próprio nome**: seria a escola
  fingindo não conhecer a família. O nome sai do `Contato`.
- O `motivo` do atendimento nasce **estruturado** (`aluno · responsável · horário ·
  motivo`), porque é o que a secretaria lê no card antes de abrir a conversa.
- Depois de aberto, o assistente **cala** (§6j): o responsável ansioso que reescreve não
  vira um segundo card.
- Cobertura: `tests/test_atendimento_humano.py` (6 testes de saída antecipada).
