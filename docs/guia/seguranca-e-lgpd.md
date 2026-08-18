# Segurança, checklist de pré-deploy e auditoria LGPD

> Parte do guia do TI-Escolar — índice em [`CLAUDE.md`](../../CLAUDE.md).
> A numeração das seções (§6a, §9c, …) é a original: as referências cruzadas
> espalhadas pelos outros documentos continuam valendo.

## 14. Postura de segurança (auditoria interna do super admin)

Painel **exclusivo do super admin** (`/admin/seguranca`) que lista as **medidas protetivas** da
plataforma e o **status real de cada uma no ambiente em execução**. É material de **auditoria
interna** (sócios) — não é conteúdo para a escola nem peça de venda, e por isso a página
redireciona quem não é super admin.

- **Quatro status, não dois.** `ATIVA` (existe no código e a configuração não a enfraquece),
  `ATENCAO` (existe, mas está desligada ou com segredo default), `PENDENTE` (ainda não
  implementada) e `NAO_APLICAVEL` (não faz sentido no produto como ele é hoje — ex.: expirar
  link de redefinição de senha quando não há fluxo de redefinição; conta separado para não
  virar alarme falso). A distinção `ATIVA`×`ATENCAO` é o ponto da tela: um relatório que só
  respondesse "implementado sim/não" esconderia exatamente o caso perigoso — a medida que
  existe no código e está desligada em produção.
- **Honestidade obrigatória.** Medida planejada e não implementada aparece como `PENDENTE`.
  Um painel de auditoria que dourasse a pílula não serviria para auditar nada. Hoje é o item
  10 (**política de backup**) que está nesse estado: existe PITR do Neon, não existe política.
- **Cada medida declara o risco que cobre**, não só o que faz — é o que permite priorizar.
- **Nenhum segredo é exposto:** a API devolve apenas *se* um segredo continua com o valor de
  exemplo (`JWT_SECRET`, `META_WEBHOOK_VERIFY_TOKEN`), nunca o valor.

**Arquitetura.** O caso de uso `AvaliarPosturaSeguranca`
(`app/application/seguranca_use_cases.py`) **não lê variáveis de ambiente**: recebe um
`ConfiguracaoSeguranca` com sinais booleanos, montado na camada de interface a partir das
`Settings`. Assim a regra que classifica cada medida fica testável sem tocar em config, e o
domínio segue sem conhecer o framework. Value objects `MedidaSeguranca`/`PosturaSeguranca` +
enum `StatusMedida` em `entities.py`.

- **Endpoint:** `GET /api/admin/seguranca` (`app/interfaces/api/seguranca.py`, guarda
  `_exige_super_admin`).
- **Painel:** `web/app/admin/seguranca/` — contadores por status, faixa de veredito
  (`pronto_para_producao`), o **checklist de pré-deploy** (abaixo) e as medidas agrupadas por
  categoria (Integridade de dados, Autenticação, Isolamento, Rastreabilidade, Exposição).
  Entrada na sidebar sob **ADMINISTRAÇÃO**, ao lado de "Escolas".
- **Medidas acrescentadas em 29/jul/2026:** `rate_limit_login`, `rate_limit_inbound` (deixou
  de ser `PENDENTE`), `seed_producao` (alerta se `SEED_DEMO` estiver ligado com
  `APP_ENV=production`) e `observabilidade` (logs persistidos e consultáveis).
- **Medida acrescentada em 13/ago/2026:** `conta_whatsapp_por_escola` — acusa escola ativa
  sem `Tenant.waba_id`, cujo disparo **por template** é recusado (e template é o que sai
  fora da janela de 24h, ou seja, todo aviso ativo). O sinal é contagem de **banco**, feita
  na rota; o caso de uso segue recebendo um retrato pronto, sem saber de onde veio. Escola
  cancelada não conta — não dispara de qualquer forma, e viraria alarme que nunca fecha.
- **Medida acrescentada em 09/ago/2026:** `canal_efetivo` — acusa o caso híbrido
  `MESSAGE_CHANNEL=meta` **sem** `META_ACCESS_TOKEN`, em que `criar_canal` cai no
  `DemoMessageChannel` **sem erro** e o WhatsApp simplesmente não está no ar. Rodar em `demo`
  de propósito (desenvolvimento local) segue `ATIVA`, para não virar alarme falso. O campo `canal` da
  resposta passou a ser o **efetivo**, não o valor da env. Ver §9c e `docs/producao-whatsapp.md`
  §6.1.1.
- **Checklist de pré-deploy embutido:** os 9 itens da §15 são servidos pelo mesmo endpoint
  (`ItemChecklist`, com `numero`/`exigencia`/`situacao` e as `medidas_relacionadas`), com a
  **numeração e a ordem da fonte preservadas** para conferência 1:1 — quem audita precisa
  cruzar item a item sem reinterpretar. Itens nossos, além da lista de origem, só entram
  **depois** do 9 (hoje: o 10, política de backup). Os itens 4 (CORS), 5 (rate limiting) e 8
  (logging) derivam da configuração viva; os demais são fatos sobre o código. O painel linka a fonte original. `pronto_para_producao` só é
  verdadeiro quando **nem as medidas nem o checklist** exigem ação.
- **Testes:** `backend/tests/test_seguranca.py` cobre a validação de assinatura (incluindo
  corpo adulterado e segredo errado) e a classificação das medidas.

---

## 15. Checklist de pré-deploy

Baseado no [pre-deployment checklist do cookbook](https://github.com/moalsayed95/cookbook/blob/main/topics/pre-deployment-checklist/README.md),
auditado contra o código em **27/jul/2026**. Legenda: ✅ feito · ⚠️ parcial · ❌ não feito ·
⬜ não aplicável.

> Estes 9 itens também aparecem **dentro do painel** `/admin/seguranca` (§14), servidos pelo
> endpoint com a numeração da fonte preservada. Esta seção é a versão narrativa; o painel é a
> versão viva, que reflete a configuração do ambiente em execução. **Ao mexer aqui, mexa
> também em `_checklist_pre_deploy`** (`app/application/seguranca_use_cases.py`), senão os dois
> divergem.

### 1. ✅ Autorização — cada usuário preso aos próprios dados

Os guardas existem e são consistentes: `_exige_acesso_tenant` (403 fora do tenant),
`_exige_super_admin`, `_exige_tenant_ativo` e `usuario_autenticado`/`professor_autenticado`
revalidando no banco.

**Furos fechados em 27/jul/2026** (eram rotas públicas que recebiam `tenant_id` no corpo/URL):
- ✅ **`POST /api/broadcasts`** — passou a exigir `usuario_autenticado` +
  `_exige_acesso_tenant`. Antes, quem soubesse a URL e um `tenant_id` **enviava WhatsApp aos
  responsáveis de qualquer escola**, pelo número dela, queimando a cota diária. A checagem de
  escola suspensa também foi trocada pelo guarda `_exige_tenant_ativo`, porque a versão inline
  só olhava `bloqueado` e **deixava passar escola cancelada**.
- ✅ **`GET /api/broadcasts/quota/{tenant_id}`** — mesma dupla de guardas (a cota revela o
  consumo da escola). O painel já mandava o token nessa chamada, então nada quebrou.
- ✅ **`POST /api/chat/mensagens` e `WS /api/chat/ws/{tenant_id}/{contato}`** — eram públicas
  por desenho (o demo era a vitrine e não tinha login) e foram **presas ao tenant de vitrine**
  em 27/jul. Em **10/ago/2026 foram removidas de vez** junto com o demo (§1): com o inbound
  real atendendo, a última superfície pública que gravava conversa e consumia LLM deixou de
  ter razão para existir. Não sobrou nenhuma rota sem autenticação que aceite `tenant_id`.

Cobertura em `backend/tests/test_rotas_publicas.py` (testes de borda HTTP, únicos da suíte —
o que se verifica é justamente o que o roteador exige antes do caso de uso).

### 2. ⬜ Expiração de link de redefinição de senha

**Não aplicável hoje: não existe fluxo de redefinição.** Senha é definida pelo super admin
(admins) ou pela secretaria (professores). Vira **obrigatório** no dia em que o reset existir —
token de uso único e TTL curto, nunca link permanente.

### 3. ✅ Validação de entrada — SQL injection e XSS

- **SQLi:** nenhuma query em SQL cru; tudo passa pelo SQLAlchemy 2.0, que parametriza.
- **Entrada:** DTOs Pydantic v2 em toda a borda HTTP (tipos, UUID, enums).
- **XSS:** React escapa por padrão e **não há nenhum `dangerouslySetInnerHTML`** no painel.

### 4. ✅ CORS restrito ao próprio domínio

Lista explícita em `BACKEND_CORS_ORIGINS`. O curinga `*` é aceito só como escape hatch e
**desabilita `allow_credentials`** (o painel usa Bearer no header, não cookie). O painel de §14
sinaliza quando está liberado. Falta **confirmar o valor em produção** no Render.

### 5. ✅ Rate limiting

Implementado em 29/jul/2026. Contador de **janela fixa no Postgres** (`controle_taxa`,
migration `0025`), não em memória: com mais de uma réplica no Render, um contador de processo
daria ao atacante uma cota por instância e seria zerado a cada deploy.
- **Login** (`/api/admin/login` e `/api/professor/login`) — conta por **IP e por
  identificador**. Só por IP, uma botnet distribuída passa livre; só por e-mail, qualquer um
  tranca a conta do diretor de propósito. Excedente recebe **429 + `Retry-After`**, sem revelar
  a régua do limite. Config: `RATE_LIMIT_LOGIN_TENTATIVAS` / `_JANELA_SEGUNDOS`.
- **Webhook inbound** — limite por **telefone remetente**, aplicado **depois** da idempotência
  (reentrega da Meta não consome franquia do responsável) e **antes** da LLM, que é o recurso
  caro. A mensagem excedente é descartada e o webhook segue devolvendo `200` à Meta — um 429
  faria a Meta reenviar e penalizar a saúde do endpoint.
- **Chat demo** — não existe mais (removido em 10/ago/2026); era a única entrada de LLM sem
  teto próprio. O inbound do webhook é hoje o único caminho até a LLM, e ele tem limite.

Código: `app/infrastructure/rate_limit.py` (adaptadores SQL e memória),
`app/interfaces/api/rate_limit.py` (aplicação no login), `ProcessarInboundMeta` (inbound).
Porta `ControleTaxa` no domínio. Cobertura: `tests/test_rate_limit.py`.

### 6. ✅ Tratamento de erro — telas próprias

Implementado em 29/jul/2026.
- **Front:** `web/app/error.tsx`, `global-error.tsx` e `not-found.tsx`. A mensagem técnica vai
  para o console do navegador; o usuário vê o **código de correlação** para relatar ao suporte.
- **Back:** `app/interfaces/middleware.py` — toda requisição recebe um id de correlação
  (herdado do `X-Request-Id` do proxy, se houver), devolvido no cabeçalho e no corpo de **todo**
  erro. O traceback vai para o log, nunca para a resposta. O handler de exceção não tratada lê
  o id do `request.state` e não do `ContextVar`, porque ele roda no `ServerErrorMiddleware` —
  mais externo que o middleware que popula o contexto.

### 7. ✅ Índices no banco

53 colunas com `index=True` nos modelos, cobrindo os `tenant_id` e as FKs quentes. Não é gargalo
conhecido; refinar com **índices compostos** (ex.: `(tenant_id, criado_em)` nas listagens
paginadas) é otimização, não pendência.

### 8. ⚠️ Logging e monitoramento

**Metade feita** (29/jul/2026): logging configurado, id de correlação por requisição,
persistência no Postgres e painel em `/admin/logs` (§16). **Falta a outra metade — alerta
ativo:** ninguém é avisado de um erro; é preciso alguém abrir o painel para descobrir. Segue
⚠️ até haver notificação (e-mail/push, ou Sentry) em falha crítica.

### 9. ⚠️ Estratégia de rollback

O procedimento passou a ser **documentado passo a passo** em `docs/runbook-rollback.md`
(Render, Vercel, Cloudflare Pages, `alembic downgrade` e restauração via Neon), mas **nunca foi
executado** — segue ⚠️ até o ensaio descrito no próprio runbook. Dois pontos específicos deste
projeto: **rollback de aplicação não desfaz migration** (a `0023_remover_content_sid` faz
`DROP COLUMN`), e o `CMD` do container roda `alembic upgrade head` a cada restart, de modo que
um `downgrade` é reaplicado se o serviço reiniciar antes de a aplicação ser revertida.

### 10. ❌ Política de backup (item nosso, além da lista de origem)

Existe apenas o **point-in-time recovery do Neon**, que cobre erro de operação recente mas mora
**dentro do mesmo provedor**: perda de conta ou corrupção descoberta depois da janela de
retenção não têm de onde voltar. Pesa mais aqui do que num sistema comum — a base guarda ficha
de matrícula de menor, com dado sensível que só existe aqui. Política proposta (dump diário
para armazenamento externo + teste trimestral de restauração) em `docs/backup.md`, **aguardando
decisão**.

### Ordem sugerida

1. ~~Autenticar `POST /api/broadcasts` e a rota de quota~~ · ~~decidir o destino do chat
   demo~~ — **feitos** em 27/jul/2026 (item 1).
2. ~~**Rate limit no login e no inbound**~~ (item 5) — **feito** em 29/jul/2026.
3. ~~**Telas de erro + handler com id de correlação**~~ (item 6) — **feito** em 29/jul/2026.
4. ~~**Logging estruturado**~~ (item 8) — **feito**; falta o **alerta ativo**.
5. **Testar o rollback** uma vez, com migration envolvida (item 9) — o runbook existe, o
   ensaio não.
6. **Decidir e implementar a política de backup** (item 10).

---

## 17. Auditoria LGPD contínua

A base do TI-Escolar é, na prática, um cadastro de **dados pessoais de crianças e
adolescentes com dado sensível junto** (§6i: `cor_raca`, `laudo_cid`, `nis`, alergia,
observações de saúde — tudo em JSON de texto claro na `fichas_matricula`). Isso põe o
produto no ponto mais exigente da LGPD (arts. 11 e 14), então a conformidade é verificada
por rotina, não por lembrança.

São **duas camadas, separadas pela natureza do risco** — e desde 13/ago/2026 elas rodam em
lugares diferentes:

- **Código, sob demanda, no Claude Code** — o agente **`lgpd-auditor`**
  (`.claude/agents/lgpd-auditor.md`, versionado) audita o diff ou a área que se pedir, e
  devolve achados com `arquivo:linha` e artigo da lei. É consultivo: **não bloqueia nada** e
  não substitui parecer jurídico. Roda **quando alguém pede**, na conversa — não há gatilho
  automático em lugar nenhum.
  - **Saiu do GitHub Actions em 13/ago/2026.** Disparava em todo PR que tocasse os caminhos
    de dado pessoal — entidades, rotas, migrations, ficha/matrícula/importação/exportação/
    inbound/conhecimento, política e termos —, o que é quase todo PR do projeto. Cada
    execução era uma sessão de agente lendo diff e repositório, cobrada em créditos de API,
    quase sempre para concluir que nada mudou para o titular. Rodando aqui, o custo é o da
    própria sessão e a auditoria acontece **junto da mudança**, enquanto ela ainda está
    sendo escrita — não depois, num comentário que ninguém releria.
  - **De quebra, fecha um problema que o próprio auditor havia levantado:** o diff deixa de
    ser enviado a uma API de terceiro. **A OpenAI não é mais operadora sobre ele** e sai do
    registro de subprocessadores por esta via — o que importava porque um diff pode carregar
    dado pessoal real, se alguém commitar fixture com CPF ou laudo.
  - **O frontmatter voltou a valer.** `tools` e `model` são sintaxe do Claude Code e estavam
    sendo descartados pelo workflow, que rodava na Codex CLI; agora o arquivo é lido inteiro
    por quem o executa. `tools: Read, Grep, Glob, Bash, WebSearch, WebFetch` é o que sustenta
    o **somente leitura** — no Actions isso dependia do mandato no prompt, porque o sandbox
    da Codex não subia em runner hospedado.
  - **A troca é o esquecimento.** Sem gatilho, uma mudança que mexe em dado pessoal só é
    auditada se alguém pedir. Desde 17/ago/2026 isso vale para **as duas camadas**: nem a
    de código nem a de ambiente têm gatilho. O único automático que sobrou é o painel §14,
    que mede a postura de dentro e não lê diff.
- **Configuração, sob demanda** — `.github/workflows/lgpd.yml`,
  `scripts/postura_ambiente.py` mede o **ambiente no ar**.
  O código é o mesmo em homolog e em produção; o que difere é a config, e ela muda **por
  fora do git** (alguém edita uma env var no painel do Render). É **determinístico e sem
  LLM** — pagar inferência para reler o mesmo repo seria caro e não repetível.
  - **Perdeu o gatilho em 17/ago/2026**, por decisão do responsável, até que exista um plano
    de execuções definido. Saíram o `push` na `main` e o `cron` semanal; ficou o
    `workflow_dispatch` (aba Actions → *Run workflow*), e o script segue rodável no terminal.
  - **O que se perde, dito em voz alta:** a configuração muda por fora do git, e era
    justamente essa janela que o cron cobria. Alguém desligar `META_VALIDATE_SIGNATURE` no
    painel do Render agora só é descoberto quando alguém for olhar. Em **produção** o risco
    é menor por outro caminho: a guarda de boot (§15) **recusa subir** com a assinatura
    desligada ou segredo de exemplo — mas ela não cobre homolog nem uma env alterada com o
    serviço já no ar.

**As verificações de ambiente são caixa-preta, sem nenhuma credencial**, e isso é decisão de
projeto: guardar um login de super admin num secret do CI abriria um caminho novo para a
base inteira — todas as escolas, todas as fichas — maior do que o risco que a checagem
cobre. O que ela mede, tudo observável de fora: `/health`; o handshake do webhook recusando
o `verify_token` de exemplo (`changeme`); `POST` no webhook sem `X-Hub-Signature-256`
devolvendo 403 (prova que `META_VALIDATE_SIGNATURE` está ligado); CORS não ecoando uma
origem forjada; rota administrativa exigindo token; e as **senhas versionadas no
`.env.example` não autenticando** — se autenticam, o seed de demonstração rodou ali e quem
leu o repositório entra.

**Ambientes.** O serviço do Render é **homolog**, e o job roda ali em **modo observação**
(relata sem reprovar). **Produção passou a existir** no Fly.io (`docs/producao-whatsapp.md`
§9b): para medi-la, acrescente um job igual apontando para a outra URL e com **`--estrito`**,
que faz a regressão de configuração falhar. A URL de homolog vem da variável de repositório
`HOMOLOG_BASE_URL`; sem ela, o job avisa e passa.

**Expurgo de documentos continua manual.** O caso de uso está pronto e a rota existe
(`POST /api/admin/documentos/expurgar`), mas **não há job agendado** e, pela mesma decisão
acima, não haverá até que o plano de execuções exista. A consequência precisa ficar escrita:
**a retenção prometida na política de privacidade não se cumpre sozinha** — documento de
menor vencido só sai da base quando alguém clicar. Ver §6k.

Distinto do painel `/admin/seguranca` (§14), que avalia a postura **de dentro** e serve à
auditoria interna dos sócios: aqui a leitura é **externa**, é a visão de quem está do lado
de fora da porta.
