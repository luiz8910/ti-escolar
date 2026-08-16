# Templates, contas do WhatsApp e disparo ativo

> Parte do guia do TI-Escolar — índice em [`CLAUDE.md`](../../CLAUDE.md).
> A numeração das seções (§6a, §9c, …) é a original: as referências cruzadas
> espalhadas pelos outros documentos continuam valendo.

### 9a. Mensagens ativas para pais (outbound via Meta Cloud API)

Disparo de notificações/avisos a pais/responsáveis. Pontos obrigatórios de projeto:

- **Templates (HSM):** mensagens enviadas **fora da janela de atendimento de 24h** exigem
  **template aprovado** pela Meta. Modelar `MessageTemplate` com **categoria** (utility / marketing /
  authentication) e status de aprovação; documentar o fluxo de submissão/aprovação.
- **Limites diários por tier:** a Meta limita o número de **destinatários únicos por 24h** por número
  de telefone, em tiers (**1K → 10K → 100K → ilimitado**), com escala automática conforme a
  **qualidade** do número. Modelar `MessageQuota` por **tenant/número**, contar destinatários e
  definir o comportamento ao **atingir o limite** (enfileirar para a próxima janela, recusar, alertar).
- **Rate limiting & fila:** porta **`RateLimiter`/`QuotaPolicy`** + **fila de envio** com
  **throttling**, **retry com backoff** e **agendamento** de broadcasts — para não estourar nem a
  **cota diária** nem a **taxa por segundo** da API.
- **Consentimento e status:** registrar **opt-in/opt-out**, respeitar a **janela de 24h**, e atualizar
  **status de entrega** (`sent` / `delivered` / `read` / `failed`) a partir dos **webhooks** da Meta.

### 9a-bis. Catálogo de templates (criação no painel + submissão à Meta)

Criar template era passo manual no WhatsApp Manager **mais** `INSERT` na tabela `templates`.
Desde 12/ago/2026 o painel (`web/app/admin/templates/`) cria, submete e acompanha, pela
**WhatsApp Business Management API** (`/{waba_id}/message_templates`).

- **Dois escopos, e o global é o caso comum.** `MessageTemplate.tenant_id` **nulo = global**:
  um `aviso_geral` por escola seriam N revisões da Meta para o mesmo texto e — pior — N
  chances de rejeição num ativo compartilhado. Então o padrão é **um texto com o nome da
  escola em `{{1}}`**, e o escopo por escola fica para o que é mesmo específico dela, com o
  nome **prefixado pelo slug** (`rosacury_festa_junina`) para não colidir na conta. Global só
  o super admin cria/remove; da escola, o admin dela.
- **⚠️ A WABA deixou de ser uma só** (13/ago/2026, migration `0042_wabas_multiplas`, §9a-ter).
  O catálogo nasceu sobre a premissa de uma conta única numa env — e ela não se sustenta,
  porque o cadastro de números tem teto (§9e.3). **Template é aprovado por conta**, então o
  mesmo texto precisa ser replicado em cada uma, com status próprio em cada.
- **Porta `CatalogoTemplates`** (`submeter`/`listar`/`remover`), separada de `MessageChannel`
  porque é **outra API e outro escopo de token**: enviar usa `whatsapp_business_messaging` em
  `/{phone_number_id}/messages`; gerir template usa `whatsapp_business_management` em
  `/{waba_id}/message_templates`. A conta é **parâmetro de cada chamada**, não estado do
  adaptador. Adaptador `MetaCatalogoTemplates`
  (`app/infrastructure/channel/meta_templates.py`) + `CatalogoTemplatesAusente`, que falha
  **no uso** com a causa por extenso (canal em demo) em vez de derrubar o boot.
- **⚠️ O catálogo não pode afirmar aprovação que a Meta não deu** (14/ago/2026). O primeiro
  disparo real falhou nos dois destinatários porque o `aviso_reuniao` constava "Aprovado" e
  **não existia na WABA**: ele entrou pelo seed de demonstração, que cravava
  `status="aprovado"`, e o seed rodou contra homolog, onde o canal é real. Três correções,
  cada uma numa camada diferente:
  - **`SincronizarTemplates` passou a desmentir.** A reconciliação era de mão única — só
    aplicava o que a Meta devolvia — então um template marcado aprovado que nunca chegou lá
    permanecia aprovado para sempre. Agora o que consta aqui e não existe na conta volta a
    `RASCUNHO`, com o motivo escrito. **Falha de listagem não desmente nada**: uma conta
    fora do ar não pode zerar o catálogo de quem está no ar.
  - **O seed só crava `aprovado` com o canal em demo** (`canal_efetivo(settings)`). Ali nada
    é enviado, a aprovação fictícia é inofensiva e é o que torna a vitrine demonstrável; com
    canal real, nunca.
  - **A falha de envio passou a registrar o motivo** (§9a-quater).
- **Submeter não é aprovar.** O `POST` devolve `PENDING`; quem muda para aprovado é o webhook
  `message_template_status_update` (§9c). `SincronizarTemplates` é a **rede de segurança**:
  webhook perdido é indistinguível de revisão em curso, e sem reconciliação alguém esperaria
  para sempre por uma aprovação que já saiu. Template que existe na Meta e não no catálogo é
  **contado, não importado** — sem saber se é global ou de uma escola, o palpite erraria o
  isolamento.
- **Validação local antes de gastar uma submissão** (`app/application/validacao_template.py`).
  Não é preciosismo: **rejeição conta contra a conta compartilhada**, então uma escola que
  apanhe três vezes respinga em todas as que operam nela. Recusa corpo que começa ou termina em variável (a
  recusa que já levamos no `retomada_atendimento`), corpo que é só variável (a Meta o proíbe
  justamente para impedir template genérico), numeração fora de sequência (os parâmetros são
  posicionais), falta de exemplo (obrigatório quando há variável) e `authentication`.
- **Estados da Meta além do nosso enum:** `PAUSED`/`DISABLED` são aprovados-e-caídos-por-
  qualidade e **enviar com eles falha**, então mapeiam para `rejeitado` — com o motivo no
  `motivo_rejeicao` — em vez de `aprovado`. Status desconhecido vira `pendente`, nunca
  `aprovado`: falhar fechado evita liberar disparo com template que a Graph API recusa.
- **Reclassificação é registrada em `warning`:** a Meta pode virar `utility` em `marketing`, o
  que **muda o preço do disparo** — sem o log, isso só aparece na fatura.
- **Rotas** `app/interfaces/api/templates.py` (`/api/admin/templates`): listar, obter, criar,
  remover, `POST /sincronizar` e `POST /replicar` (super admin). Migrations
  `0040_templates_catalogo` (`tenant_id` anulável, `exemplos`, UNIQUE `(nome, idioma)`) e
  `0042_wabas_multiplas` (status por conta). Cobertura: `tests/test_templates.py` (40 testes).
- **O disparo escolhe o template** (13/ago/2026). Até aqui ele usava um UUID cravado em
  `web/lib/admin.ts` (`DEMO_TEMPLATE_ID`, do seed de demonstração) e montava **2
  parâmetros fixos** — contagem que ficou defasada quando o `aviso_reuniao` ganhou o nome
  da escola em `{{2}}`. Em produção, onde o seed não roda, o id não existe; e onde existia,
  a Meta recusaria por número de parâmetros, **destinatário a destinatário, depois de a
  cota do dia ter sido consumida**.
  - `TemplateSaida.enviavel_aqui` responde "aprovado **na conta desta escola**?" — a única
    pergunta da tela de disparo. É resolvido no **servidor**, que conhece o vínculo escola
    → conta; deixar o painel cruzar `contas[]` espalharia a regra por duas camadas.
  - **`ParametroTemplate` (`origem` ∈ {`responsavel`, `escola`, `texto`})** diz como
    preencher cada `{{n}}`. São as três coisas disponíveis no envio a um grupo: quem
    recebe, quem assina, e o que a secretaria escreveu. Um campo livre para tudo obrigaria
    a digitar o nome de cada responsável; um valor fixo para tudo mandaria o mesmo nome
    para a turma inteira.
  - **A contagem é conferida no servidor** contra os `{{n}}` do corpo, com erro em
    português — em vez de descoberta como "não entregue" na Graph API. Origem desconhecida
    cai em `texto`, que é inerte: cair em `responsavel` mandaria o nome de outra pessoa.
  - A tela mostra o corpo do template e, para cada variável, o **trecho em volta dela**
    (`trechoDoPlaceholder`) — sem isso o formulário pede "parâmetro 2" e a secretaria
    adivinha.

### 9a-quinquies. Retomada do disparo na janela seguinte

O teto da Meta é de **destinatários únicos por 24h**, e hoje vale **250 no portfólio
inteiro** (§9e.3). Uma escola de 600 responsáveis não cabe num dia — e o produto já sabia
disso: `EnviarBroadcast` conta os excedentes em `bloqueados_por_limite`, deixa os
destinatários em `PENDENTE` e marca o broadcast como `PARCIAL_LIMITE`.

**O que faltava era alguém voltar no dia seguinte.** "Espera a próxima janela" significava,
na prática, alguém lembrar de re-disparar à mão — e o aviso da reunião chegava a metade da
escola. Enquanto o teto era teoricamente 1000 dava para adiar; com 250 real, virou requisito
para o disparo funcionar como vendido.

- **A retomada é barata porque a idempotência já existia:** `EnviarBroadcast` pula quem está
  em `ENVIADO`/`ENTREGUE`/`LIDO`, então reexecutar o mesmo broadcast continua de onde parou
  sem reenviar para ninguém. `RetomarBroadcastsPendentes` só precisa achar os
  `PARCIAL_LIMITE` (`BroadcastRepository.listar_retomaveis`) e chamá-lo de novo.
- **`BROADCAST_RETOMADA_JANELA_DIAS` (7) é prazo de validade, não otimização.** Aviso de três
  semanas atrás entregue hoje é **pior** que aviso não entregue: a reunião já passou e o
  responsável recebe da escola uma mensagem sem sentido. Vencido o prazo, o disparo é
  abandonado onde está — o histórico segue mostrando quem recebeu e quem não.
- **A cota é por escola, então a fila não para por inteiro.** Uma escola que estoure a cota
  entra num conjunto de "sem cota" e é pulada no resto da passada; as outras continuam. Parar
  tudo faria uma escola grande calar o aviso das demais.
- **Tarefa de fundo com advisory lock** (`app/infrastructure/retomada.py`), no mesmo desenho
  do gravador de logs — o projeto não tem scheduler e subir um só por isto seria caro. Com
  mais de uma réplica no Render, dois processos acordariam juntos e enviariam **duas vezes
  para o mesmo responsável**: o destinatário só vira `ENVIADO` depois da chamada à Graph API,
  então nada impede a corrida. `pg_try_advisory_lock` resolve em uma linha — quem pega roda,
  quem não pega volta a dormir (`try`, e não `pg_advisory_lock`, porque esperar na trava só
  empilharia réplicas para fazer o mesmo trabalho). Verificado entre sessões distintas: a
  segunda recebe `False`.
- **Rota manual** `POST /api/admin/broadcasts/retomar` (super admin) para não depender só do
  ciclo — roda na hora em que a cota virar.

### 9a-quater. O motivo da falha de envio (`DestinatarioBroadcast.erro`)

`EnviarBroadcast` captura a exceção por destinatário para **não derrubar o lote** — o que
está certo — e a descartava junto, o que não estava. No primeiro disparo real o painel
mostrou "Falhou" nos dois responsáveis e a causa não existia em lugar nenhum: nem log, nem
campo. Descobri-la exigiu consultar a Graph API à mão.

Agora a exceção vai para o log (`warning`, com template, contato e broadcast) **e** para
`DestinatarioBroadcast.erro` (migration `0043_destinatario_erro`), que o painel exibe sob o
selo "Falhou".

**Guardar o erro não bastou: o texto precisava ser legível.** Na primeira tentativa depois
da correção, o painel exibiu `Client error '404 Not Found' for url .../messages` — o
`HTTPStatusError` cru do httpx, que esconde a única frase que importa. **O status HTTP
engana aqui:** template inexistente responde **404**, não 400, e o motivo real
(`(#132001) … template name (aviso_reuniao) does not exist in pt_BR`) está no **corpo**.
`MetaMessageChannel` passou a levantar `EnvioRecusado` com `error.message` +
`error_data.details` extraídos do corpo — o mesmo que `MetaCatalogoTemplates` já fazia para
a submissão, e que faltava no envio.

### 9a-ter. Várias contas do WhatsApp (`Waba`) — o teto que quebrava o catálogo

A premissa de "uma WABA para todas as escolas" **não se sustenta**: o teto de números
(§9e.3) garante que haverá uma segunda conta, e template é aprovado **por conta**. Com o
status numa coluna só do template, o produto respondia "aprovado" para uma escola cujo
número está em outra conta — e a Graph API recusava o envio **depois** de a trava já ter
dado o aval. A falha era do tipo pior: silenciosa, e no caminho do dinheiro.

- **`Waba`** (migration `0042_wabas_multiplas`): `meta_waba_id`, `nome`, `ativo` e
  **`meta_business_id`** — o portfólio, que é onde a Meta de fato mede o teto de números e o
  limite diário de envio. Só super admin (`/api/admin/wabas`, painel `web/app/admin/wabas/`),
  porque a conta é ativo compartilhado: quem a edita redireciona o catálogo de várias
  escolas.
- **`Tenant.waba_id`** diz **onde** o número da escola está — e portanto onde criar e
  conferir o template dela. Nulo = a escola dispara pelo número, mas o disparo **por
  template** é recusado, porque não há onde conferir a aprovação.
- **Um texto, N submissões** (`TemplateNaWaba`, tabela `template_wabas`): corpo, categoria e
  exemplos ficam no template, uma vez só; id na Meta, status e motivo ficam por conta.
  Duplicar a linha inteira faria de editar um texto o trabalho de manter N cópias em
  sincronia, e o painel mostraria o mesmo template várias vezes.
- **`MessageTemplate.status` virou derivado — o pior entre as contas.** A tela precisa de um
  selo só, e o selo otimista é o perigoso. Quem decide o envio é `aprovado_em(waba_id)`;
  nunca submetido numa conta é `RASCUNHO`, não `PENDENTE`.
- **Global replica; da escola, não.** `CriarTemplate` submete o global em toda conta ativa e
  o da escola só na conta dela — ocupar o nome nas outras multiplicaria por N o risco de
  rejeição num ativo compartilhado. **Falha numa conta não desfaz as outras** (desfazer
  gastaria outra submissão para voltar ao início): a conta sem entrada aparece como "não
  submetido", e `ReplicarTemplates` (`POST /templates/replicar`) reprocessa. É também o
  passo obrigatório ao **cadastrar uma conta nova** — sem ele as escolas dela ficam sem
  nenhum template aprovado, e a falha só aparece no primeiro disparo.
- **O webhook usa `entry[].id`**, que é o id da WABA, para saber em qual conta aplicar o
  status. Sem isso a aprovação na conta A marcaria aprovado o template da conta B — a mesma
  mentira que o modelo por conta veio corrigir. **Categoria é exceção**: vale para o texto
  em qualquer conta, então é aplicada mesmo quando o evento não diz de onde veio.
- **Não existe `META_WABA_ID`.** A conta é **cadastro, não configuração**: amarrá-la ao
  ambiente reintroduziria a premissa de conta única que esta seção existe para desfazer, e
  criaria uma ordem de deploy frágil (a env precisaria estar no lugar *antes* da migration
  rodar). A migration cria a conta **sem id**, com todas as escolas e todos os status
  existentes — nenhuma aprovação é perdida. O id chega por um dos dois caminhos, ambos
  visíveis:
  - **o painel** (Administração → Contas WhatsApp), que é o caminho que sempre existe; ou
  - **o próprio webhook** (`AdotarContaDoWebhook`), porque o `entry[].id` de todo evento
    carrega a conta. **A documentação da Meta não afirma isso em texto** — os exemplos
    mostram o número, a referência não descreve o campo —, então a adoção **não acredita
    na leitura do payload**: ela pergunta à Meta (`CatalogoTemplates.descrever` →
    `GET /{id}?fields=id,name`) e só grava se a resposta confirmar que aquele id é uma
    conta que enxergamos. Três condições, todas necessárias: id desconhecido, **exatamente
    uma** conta sem id (com duas, escolher seria chute) e confirmação da Meta. Falhando
    qualquer uma, nada acontece — o custo é um campo digitado, contra gravar um id
    inválido que faria toda submissão falhar. A escrita vai para o log em `warning`, por
    ser uma mudança de cadastro que ninguém pediu.
