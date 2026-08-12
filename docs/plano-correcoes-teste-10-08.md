# Plano de correções — apontamentos do teste de 10/08/2026

> Fonte: `Apontamentos testes 10.txt` + a ficha de matrícula física em anexo
> (`ficha_cadastro_aluno.png`, `ficha_cadastro_aluno_2.png`).
>
> Cada item traz **o que foi apontado**, **o diagnóstico no código** (arquivo:linha) e **a
> correção proposta**. Onde a decisão muda a forma do trabalho, ela está marcada como
> **⚠️ decisão** e listada no final.
>
> **Além dos apontamentos**, entrou nesta rodada uma decisão de infraestrutura que não veio
> do teste: mover os arquivos dos responsáveis para um **bucket S3 da AWS** (Fase 0).
>
> **Estado em 11/ago/2026 — decisões A–G respondidas.** Ver a tabela no fim. A **Fase 0 está
> adiada**: o bucket ainda não existe, então só as variáveis de ambiente entram agora
> (comentadas e documentadas no `.env.example`) e o armazenamento segue no Postgres. As
> decisões F e G ficam registradas para quando a fase for retomada.

---

## Leitura geral

Os 24 apontamentos não são 24 bugs. Eles se dividem em três naturezas muito diferentes, e
tratá-los como uma lista única seria o erro de planejamento aqui:

| Natureza | Quantos | Custo | Exemplo |
|---|---|---|---|
| **Bug / ajuste de tela** | 8 | horas | menu "Turmas", sininho decorativo, refresh dos atendimentos |
| **Modelo de dados incompleto** | 9 | dias, com migration | campos de aluno, responsável, professor, turma, usuário |
| **Funcionalidade nova** | 7 | dias | OCR, blacklist anti-spam, sessão de conversa de 24h, automação do ciclo de vida |

O bloco do meio é o caminho crítico: **quase toda a Fase 2 é migration + entidade + rota +
tela**, e várias delas se cruzam (o responsável do aluno é o mesmo `Contato` que a turma
vincula, que o broadcast dispara e que o atendimento nomeia). Por isso elas vão juntas, num
único PR de cadastro, e não item a item.

Uma constatação que vale destacar: **a `FichaMatricula` (§6i do CLAUDE.md) já existe no
back-end com quase todos os campos da ficha em anexo — e não tem nenhuma tela.**
`grep -rn "ficha" web/` só encontra a *ficha financeira* do super admin. Ou seja, boa parte
do apontamento "//Alunos — ver ficha em anexo" é **expor o que já está pronto**, não
construir do zero.

---

## Fase 0 — Arquivos em bucket S3 da AWS · **ADIADA** (só as envs entram agora)

> **Decidido em 11/ago/2026: adiada.** O bucket ainda não foi criado, e escrever o adaptador
> sem credencial para testá-lo contra o serviço real seria repetir exatamente o impasse que
> já deixou o adaptador de object storage sem sair do papel (§0.6). **O que entra agora:** as
> variáveis de ambiente no `.env.example`, comentadas e com o efeito de cada uma explicado,
> para que ligar o bucket depois seja preencher valores — não redescobrir o desenho. O
> armazenamento continua em `PostgresArquivoStorage`.
>
> **Consequência para a Fase 2:** a foto do aluno nasce no Postgres e será migrada junto com
> os documentos quando esta fase for retomada. É um custo aceitável — a foto é opcional
> (decisão D) e o volume inicial é pequeno —, mas fica registrado que **a migração de bytes
> ganhou um segundo tipo de arquivo** para mover.

Não veio do teste: é a troca de casa dos bytes dos documentos. Entraria **antes da Fase 2**
por uma razão prática — a Fase 2 acrescenta a **foto do aluno**, e fazer isso com o storage
antigo significa gravar as fotos no Postgres para migrá-las de novo depois.

### 0.0 · Por que agora, e o que muda em relação ao que está escrito

Hoje o único adaptador de produção é o Postgres (`bytea`), e o próprio código já declara que
isso é provisório (`backend/app/infrastructure/storage.py:1-17`). A porta `ArquivoStorage`
(`ports.py:747-763`) foi desenhada exatamente para esta troca: três métodos —
`guardar`/`ler`/`remover` — e nenhum vazamento de detalhe de armazenamento para o negócio.
**A arquitetura já está pronta; o que falta é o adaptador e a conta.**

Uma correção de registro: o código e o CLAUDE.md recomendam **Cloudflare R2**, pelo egress
gratuito. Com S3 a AWS cobra egress (~US$ 0,09/GB), e como o §6k proíbe URL pública, todo
download passa pela API — ou seja, **paga-se egress duas vezes** (S3 → Render → navegador).
Dito o senão: **na escala do TI-Escolar isso é irrelevante.** Uma escola em fevereiro sobe
algo como 1 GB; o armazenamento sai por centavos e o egress, por poucos dólares ao mês. Em
troca, o S3 entrega três coisas que pesam mais que essa diferença aqui:

- **Lifecycle** nativo, que vira a rede de segurança do prazo de retenção (§6k);
- **SSE-KMS** com chave própria — auditoria por objeto no CloudTrail e a possibilidade de
  destruir a chave (*crypto-shredding*) se um dia for preciso inutilizar o acervo;
- **Object Lock e versionamento** maduros, para o dia em que a política de backup (item 10
  do checklist) sair do papel.

R2 volta a fazer sentido se o egress virar linha de custo real. Enquanto não for, S3 é uma
escolha defensável — e é a que está decidida.

### 0.1 · A peça que falta: fábrica de storage

**Diagnóstico:** `PostgresArquivoStorage(session)` está **instanciado à mão em quatro
lugares** de `backend/app/interfaces/deps.py` (linhas 119, 149 e 158, mais
`get_recepcao_documentos`). Não existe `criar_arquivo_storage(settings)` — ao contrário de
`criar_canal`, `criar_llm` e `criar_email_sender`, que moram em
`infrastructure/factories.py`. Trocar de storage hoje é editar quatro chamadas.

**Correção:** `criar_arquivo_storage(settings)` na fábrica, escolhendo pelo
`ARQUIVO_STORAGE` (`postgres` | `s3`), e as quatro chamadas passam a consumi-la.

> **E, junto, `storage_efetivo(settings)`** — espelhando o `canal_efetivo` do §9c. A lição
> ali foi cara e é idêntica aqui: `MESSAGE_CHANNEL=meta` **sem token** caía no canal demo
> **sem erro nenhum**, e o WhatsApp simplesmente não estava no ar. Um
> `ARQUIVO_STORAGE=s3` sem credencial que caísse no Postgres em silêncio repetiria a falha
> — só que com atestado médico de criança indo para o banco errado. O storage efetivo
> aparece no `/health` e no painel de segurança, e o boot loga em `error` quando o pedido
> diverge do efetivo.

### 0.2 · O adaptador `S3ArquivoStorage`

- Vive em `app/infrastructure/storage.py` (ou `storage/s3.py`), como manda a convenção —
  **SDK só em `infrastructure/`**.
- Implementa só `PutObject`, `GetObject` e `DeleteObject`. ⚠️ **decisão G** (SDK).
- **Sem URL pré-assinada, de propósito.** É a tentação óbvia do S3 e vai contra o §6k: uma
  presigned URL *é* uma URL pública com prazo, e passaria por fora da autenticação, do
  escopo por tenant e da **auditoria de download** — que hoje registra `documento.baixar`
  para cada acesso. Os bytes continuam saindo pelo endpoint da API.
- **Layout da chave:** `doc/{tenant_id}/{ano}/{mes}/{token}`. Hoje `nova_chave`
  (`storage.py:34-41`) gera `doc/YYYY/MM/token`, sem tenant. Pôr o tenant no prefixo dá
  três coisas de graça: lifecycle e inventário por escola, e a remoção de tenant
  (`SqlTenantRepository.remover`) vira uma exclusão por prefixo em vez de uma varredura.
  O UUID do tenant não é dado pessoal — a regra do docstring (nada de nome de aluno ou
  responsável na chave) continua valendo.

### 0.3 · A atomicidade que se perde — e o que fazer com ela

Este é o ponto que não aparece num "troque o adaptador". Hoje o `PostgresArquivoStorage`
recebe **a mesma `AsyncSession` da requisição**: bytes e metadado entram na **mesma
transação**, e ou os dois existem ou nenhum existe. Com o S3 isso acaba.

- **Ordem obrigatória:** grava no S3 **e depois** commita o metadado. O inverso deixaria
  `documentos_recebidos` apontando para um objeto que não existe — a secretaria veria
  "documento recebido" e o download daria 404, que é o pior dos dois erros.
- **Sobra o órfão:** objeto no S3 cujo metadado não chegou a commitar (rollback depois do
  PUT). Não vaza — a chave é imprevisível e o bucket é fechado — mas acumula.
  **Varredor de órfãos** comparando o `ListObjectsV2` por prefixo com
  `documentos_recebidos.chave_storage`, rodando junto do expurgo. Objeto órfão com mais de
  24 h e sem metadado é apagado.
- O expurgo (`ExpurgarDocumentosVencidos`, `documentos_use_cases.py:325-365`) **não precisa
  mudar**: já é tolerante a falha item a item, que é exatamente o comportamento certo
  quando o `remover` passa a ser uma chamada de rede.

### 0.4 · Configuração do bucket — é aqui que a LGPD mora

| Item | Valor | Por quê |
|---|---|---|
| **Região** | `sa-east-1` (São Paulo) | ⚠️ **decisão F** — ver abaixo |
| **Block Public Access** | ligado na conta **e** no bucket | o conteúdo é dado de saúde de menor |
| **Object Ownership** | `BucketOwnerEnforced` (ACLs desligadas) | ACL é a forma clássica de abrir um bucket sem perceber |
| **Bucket policy** | `Deny` quando `aws:SecureTransport = false` | recusa qualquer acesso fora de TLS |
| **Criptografia** | SSE-KMS com CMK própria | auditoria por objeto no CloudTrail + *crypto-shredding* |
| **Versionamento** | **desligado** — ou ligado com expiração de versões antigas em ≤ 7 dias | ver o alerta abaixo |
| **Lifecycle** | expiração em `DOCUMENTO_RETENCAO_DIAS + 30` | **rede de segurança**, nunca o mecanismo principal |
| **IAM** | usuário dedicado; só `PutObject`/`GetObject`/`DeleteObject`/`ListBucket` no ARN do bucket | nada de `s3:*` |
| **Ambientes** | buckets separados para homolog e produção | hoje o Render é homolog e produção não existe |

> ⚠️ **A armadilha do versionamento.** Com versionamento ligado e sem regra de expiração de
> versões não-correntes, o `DeleteObject` do expurgo **não apaga nada**: cria um *delete
> marker* e os bytes do atestado continuam no bucket, indefinidamente. O expurgo relataria
> sucesso, o painel mostraria a retenção em dia e o dado sensível seguiria lá. É exatamente
> o tipo de falha silenciosa que o §14 existe para acusar.

**Sobre o lifecycle:** ele expira por idade do objeto, enquanto o `expira_em` do §6k é por
documento. Se um dia uma escola tiver prazo diferente, o lifecycle estaria errado. Por isso
ele é folgado (`+30`) e serve só para varrer o que a aplicação não varreu — quem apaga de
verdade é o `ExpurgarDocumentosVencidos`, porque ele apaga **o metadado junto**, e manter
"havia um atestado do aluno X" sem o arquivo seria tratamento sem utilidade.

**Config nova** (`app/config.py` + `.env.example`): `ARQUIVO_STORAGE`, `AWS_REGION`,
`S3_BUCKET_DOCUMENTOS`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_KMS_KEY_ID` e
`S3_ENDPOINT_URL` (só para o MinIO local — ver 0.6).

### 0.5 · Migrar os bytes que já estão no Postgres

Em **dois tempos**, para ser reversível. O runbook (`docs/runbook-rollback.md`) é explícito:
*rollback de aplicação não desfaz migration*, e o `CMD` do container roda
`alembic upgrade head` a cada restart.

1. **Tempo 1 — `ArquivoStorageComFallback`** (sem migration): escreve **só no S3**; lê do S3
   e, não encontrando, cai no Postgres. Os arquivos antigos continuam servindo, e um
   contador de quantas vezes o fallback foi acionado vai para o log. Reversível por deploy:
   basta voltar o `ARQUIVO_STORAGE`.
2. **Backfill:** script que percorre `arquivos_armazenados`, sobe cada objeto com a **mesma
   chave**, confere o tamanho e segue. Idempotente e retomável — pode rodar em lotes, fora
   do horário.
3. **Tempo 2 — `DROP COLUMN`:** só quando o backfill estiver conferido *e* o contador de
   fallback estiver zerado há dias, a migration `0035_arquivo_sem_bytea` apaga
   `arquivos_armazenados.conteudo`. **É irreversível**, e é o primeiro momento em que a
   ausência de uma política de backup (item 10 do checklist, ainda "aguardando decisão")
   deixa de ser teórica. Não executar o tempo 2 sem um dump conferido.

### 0.6 · Como testar sem chave de produção

Vale registrar por quê: o adaptador de object storage **nunca foi escrito** justamente por
isso — o `storage.py:1-17` diz que sem credencial para testar contra o serviço real ele
"iria para produção sem nunca ter escrito um byte". Não repetir o impasse:

- **MinIO** (S3-compatível) no `docker-compose.yml` e no CI, via `S3_ENDPOINT_URL`. O
  adaptador passa a rodar contra um serviço real — não contra um mock — em **todo PR**.
- **Smoke test** contra o bucket de homolog, manual, na virada.

### 0.7 · Postura de segurança, saúde e privacidade

- **Medida `storage_efetivo`** no painel `/admin/seguranca` (§14): `ATENCAO` quando
  `ARQUIVO_STORAGE=s3` sem credencial (cairia no Postgres em silêncio) e quando a região
  configurada está fora do Brasil sem base legal declarada. `postgres` em desenvolvimento
  segue `ATIVA`, para não virar alarme falso — mesmo critério do `canal_efetivo`.
- **`/health`** reporta o storage **efetivo**, como já faz com o canal. Não vai tocar o
  bucket a cada checagem: um `HEAD` por health check gera custo e ruído sem informar nada
  que o boot já não tenha dito.
- **`site/privacidade/`** passa a nomear a **AWS como operadora** e a região de
  armazenamento. Se a região não for brasileira, isso vira **transferência internacional**
  (LGPD arts. 33–36) e exige base legal declarada — é o conteúdo da decisão F.
- O PR passa pelo agente `lgpd-auditor` (§17), como todo diff que toca dado pessoal.

---

## Fase 1 — Correções de tela e permissão (1 PR, ~1 dia)

Itens baratos, sem migration, que devolvem confiança na navegação.

### 1.1 · Menu: "Salas e pais" → "Turmas"
**Apontado:** trocar o rótulo.
**Diagnóstico:** `web/components/layout/Sidebar.tsx:40`.
**Correção:** rótulo → "Turmas"; rota `/admin/salas` → `/admin/turmas` (com redirect de
`/admin/salas` para não quebrar link salvo). Renomear o diretório
`web/app/admin/salas/` → `web/app/admin/turmas/`. **Não** renomear `Sala` no domínio nesta
fase — seria um diff enorme por um rótulo; fica como dívida anotada.

### 1.2 · "Instruções da escola" leva ao super admin e sai do admin da escola
**Apontado:** clicar em *Instruções da escola* tira o usuário do contexto da escola.
**Diagnóstico:** achado real, e é mais amplo que essa tela. Em
`web/lib/admin.ts:276-279`:

```ts
export function tenantEmFoco(): string {
  const s = getSessao();
  return s?.usuario.tenant_id ?? DEMO_TENANT_ID;   // ← super admin cai no tenant DEMO
}
```

O super admin tem `tenant_id = NULL`. Como o dropdown de escola foi removido do painel
(§12a, "Limpeza de UI"), **não sobrou nenhuma forma de o super admin dizer em qual escola
está operando** — toda tela de escola (instruções, base de conhecimento, alunos, turmas,
atendimentos, documentos) silenciosamente opera sobre a escola de demonstração. A tela de
instruções é só onde isso ficou visível, porque ela também troca o rótulo da sidebar para
"Plataforma · Super Admin" (`AppShell` → `isSuperAdmin`).

**Isto é pior que um bug de navegação: é um super admin editando a escola errada sem
nenhum aviso.**

**Correção:** introduzir **escola em foco** explícita para o super admin.
- `web/lib/admin.ts`: `tenantEmFoco()` passa a ler um `tenant_id` escolhido, guardado no
  `localStorage` ao lado da sessão. Sem escolha e sendo super admin → **não chuta**:
  lança e a página manda escolher.
- Componente `SeletorDeEscola` na `Topbar`, visível **só** para super admin (o
  `showTenant` já existe em `Topbar.tsx:49` e hoje é decorativo). Entrar em
  `/admin/escolas/[tenantId]` define o foco.
- Faixa de aviso no topo das telas de escola quando quem está logado é super admin:
  "Você está operando como **Escola X**".

### 1.3 · Base de conhecimento — remover só com super admin
**Apontado:** a exclusão não pode ficar na mão do admin da escola.
**Diagnóstico:** `backend/app/interfaces/api/conhecimento.py:108-119` — o `DELETE` só exige
`_exige_acesso_tenant`, isto é, qualquer `tenant_admin` apaga documento indexado da
própria escola.
**Correção:** trocar por `_exige_super_admin` na rota de remoção (mantendo
`_exige_acesso_tenant` para o escopo). No painel
(`web/app/admin/conhecimento/page.tsx:222-227`), o botão "Remover" só aparece para super
admin; para o admin da escola, oferecer **"Desativar"** — que tira do RAG sem apagar o
texto (é o comportamento que a escola realmente quer quando um procedimento muda).
⚠️ **decisão A**: se "desativar" não for desejado, o botão simplesmente some para o
`tenant_admin`.

### 1.4 · Base de conhecimento — visualizar / editar o documento
**Apontado:** só dá para enviar e remover.
**Diagnóstico:** a lista mostra nome, tipo, nº de trechos (`page.tsx:207-228`) e nunca o
conteúdo. Não existe `GET /conhecimento/{id}` nem `PUT`.
**Correção:**
- back-end: `GET /api/admin/conhecimento/{fonte_id}` (devolve o texto original) e
  `PUT /api/admin/conhecimento/{fonte_id}` → caso de uso `AtualizarFonteConhecimento`, que
  **apaga os trechos antigos e reindexa** (o mesmo caminho já usado pelas respostas
  rápidas, §C1 — reusar `IngerirDocumento`). Guardar `conteudo` bruto na
  `FonteConhecimento`, hoje não persistido.
  → **migration `0031`** (coluna `fontes_conhecimento.conteudo`).
- painel: clicar no documento abre modal com o texto, editável, e botão "Salvar e
  reindexar".

### 1.5 · Atendimentos — refresh automático
**Apontado:** as conversas não se atualizam sozinhas.
**Diagnóstico:** `web/app/admin/atendimentos/page.tsx:120-128` — carrega uma vez no
`useEffect` e só recarrega após uma ação (`agir`, linha 141).
**Correção:** polling em dois níveis, no padrão que a `Sidebar.tsx:156-172` já usa
(falha silenciosa, sem toast):
- **lista da fila**: a cada 20 s;
- **conversa aberta**: a cada 10 s (é onde há alguém esperando do outro lado), com
  preservação do texto já digitado e do scroll.
Pausar o polling quando a aba está em `document.hidden` — senão o painel aberto a noite
inteira gera requisição por nada.

### 1.6 · Atendimentos — mostrar o nome do responsável
**Apontado:** aparece o telefone; deveria aparecer o nome se cadastrado.
**Diagnóstico:** a tela **já prefere o nome** (`page.tsx:267`,
`{item.contato_nome || item.contato}`). O furo é no back-end: `contato_nome` é gravado
**uma vez, no nascimento do atendimento**
(`atendimento_humano_use_cases.py:178` e `:265`) e nunca mais reconferido. Se o
responsável ainda não estava cadastrado quando escreveu — que é o caso comum — o card fica
com o telefone para sempre, mesmo depois de a secretaria cadastrá-lo.
**Correção:** resolver o nome **na leitura**, não na escrita. `ListarAtendimentos`
(linha 300) e `ObterAtendimento` (linha 343) passam a receber o `ContatoRepository` e
preencher `contato_nome` em lote (uma consulta por página, não N+1). O campo persistido
vira apenas fallback histórico.

---

## Fase 2 — Cadastro escolar completo (1 PR grande, ~4–6 dias)

O bloco pesado. Uma migration só (**`0032_cadastro_completo`**), porque as quatro entidades
se cruzam e migrations parciais deixariam o banco num estado que nenhuma tela sabe ler.

### 2.1 · Turmas — campos reais
**Apontado:** cadastrar ano, série (A, B, C, D), número da sala, período e **grade de
horário com intervalo**.
**Diagnóstico:** `backend/app/domain/entities.py:493-510` — `Sala` tem só `nome`,
`descricao`, `professor_id`. Hoje "4ª série B" é uma string livre, o que impede ordenar,
promover automaticamente e cruzar com a ficha (`FichaMatricula.ano_etapa`/`periodo`).
**Correção:** campos novos em `Sala`:

| Campo | Tipo | Nota |
|---|---|---|
| `ano_letivo` | `int` | ex.: 2026 — é o que a ficha em anexo chama de ANO |
| `etapa` | `str` | ex.: "1º", "4ª série" — a ETAPA da ficha |
| `turma` | `str` | A/B/C/D — a TURMA da ficha |
| `numero_sala` | `str` | sala física |
| `periodo` | enum `manha`/`tarde`/`integral`/`noite` | o PERÍODO (M) da ficha |
| `grade_horario` | JSON | lista de blocos `{dia, inicio, fim, tipo}`, `tipo ∈ aula/intervalo` |

`nome` passa a ser **derivado** (`f"{etapa} {turma}"`) para não quebrar as telas e os
relatórios existentes; unicidade migra para `(tenant_id, ano_letivo, etapa, turma)`.
Migration de dados: as salas existentes recebem `ano_letivo` = ano corrente e o `nome`
atual é quebrado em `etapa`/`turma` por regex, com fallback para `etapa = nome`.

⚠️ **decisão B — grade de horário:** um editor de grade é uma tela por si só. Proponho
**começar simples**: horário de início/fim do turno + horário e duração do intervalo (4
campos), que é o que a secretaria precisa hoje; a grade aula-a-aula fica para depois. A
coluna já nasce JSON, então subir de escopo não custa migration.

### 2.2 · Turmas — retirar o cadastro de pais da tela
**Apontado:** tirar o cadastro de pais de dentro de Turmas.
**Diagnóstico:** `web/app/admin/salas/page.tsx` (804 linhas) faz CRUD de sala **e** CRUD de
responsável **e** vínculo N:N `sala_contatos`.
**Correção — e aqui há uma consequência que precisa ser dita:** o vínculo pai↔turma é hoje
**manual** (`sala_contatos`), e é dele que dependem três coisas já em produção — o
`RelatorioPaisDaSala`, a cobertura de contatos (§6c-ter) e o disparo dirigido a uma turma.
Tirar o cadastro da tela sem substituir a fonte do vínculo **quebraria os três**.

Proposta: **o vínculo passa a ser derivado do aluno.** Um responsável pertence à turma
porque tem um aluno ativo nela (`aluno_responsaveis` + `Aluno.sala_id`, que já existem).
- `sala_contatos` deixa de ser editável e vira consulta derivada; os relatórios e a
  cobertura leem da derivação.
- A tela de Turmas perde as seções de responsável e fica com: dados da turma, professor,
  grade, **lista de alunos** e o alerta de cobertura.
- O cadastro do responsável vive **só** dentro de Alunos (§2.3).

Isso é mais correto que o estado atual: hoje é possível ter um pai vinculado à turma sem
nenhum filho nela, e a cobertura conta errado.

### 2.3 · Alunos — ficha completa
**Apontado (aluno):** Nome\*, CPF\*, RA\*, data nasc\*, endereço completo\*, sexo\*, cidade
de nascimento, cartão do SUS, **upload de foto\***.
**Apontado (responsável):** Nome\*, CPF\*, tipo de filiação, data nasc, telefone_1\*
(principal — usado nos disparos e na conversa com a IA), telefone_2, local de trabalho,
telefone do trabalho, e-mail.
**Apontado (termo de guarda):** os mesmos campos, para quando o responsável não é mãe/pai.
**Apontado (dados obrigatórios):** o bloco da ficha em anexo — cor/raça, Bolsa Família/NIS,
deficiência, necessidade especial, laudo médico/CID (com "em investigação"), restrição
alimentar, alergia.

**Diagnóstico — a maior parte disso já existe e está invisível:**

| Campo pedido | Onde já está | Falta |
|---|---|---|
| CPF, RA/RM, data nasc, sexo, endereço, cidade natal, cartão SUS | `FichaMatricula` (`entities.py:1470-1481`) | **tela** |
| cor/raça, NIS, deficiência, necessidade especial, laudo/CID, restrição, alergia | `FichaMatricula` (`:1500-1507`) | **tela** |
| autorizações (van, retirada, imagem), com quem mora, UBS, convênio | `FichaMatricula` (`:1491-1498`) | **tela** |
| termo de guarda | `FichaMatricula.termo_guarda` + `responsavel_legal` | modelagem correta (é uma pessoa, não um booleano) |
| responsável: CPF, filiação, tel_2, trabalho, e-mail | ✗ | `Contato` só tem nome + telefone (`entities.py:403-416`) |
| **foto do aluno** | ✗ | tudo |
| "em investigação" do laudo | ✗ | hoje `laudo_cid` é string livre |

**Correção — três frentes:**

**(a) `Contato` vira o responsável de verdade.** Campos novos: `cpf`, `tipo_filiacao`
(`mae`/`pai`/`responsavel_legal`/`outro`), `data_nascimento`, `telefone_2`,
`local_trabalho`, `telefone_trabalho`, `email`. `telefone` (já existente) é o **telefone_1
principal** — é a chave de roteamento do inbound e do outbound, e continua sendo a única
única por `(tenant_id, telefone)`; `telefone_2` **não** roteia nada (documentar isso na
tela, senão a secretaria vai supor que o bot responde nos dois).

O **termo de guarda** deixa de ser booleano: é um `Contato` com
`tipo_filiacao = responsavel_legal`, ligado ao aluno por `aluno_responsaveis` com a coluna
nova `parentesco` na associação. O botão "Cadastrar termo de guarda" do apontamento
adiciona esse terceiro responsável. Vantagem concreta: ele passa a receber disparo e a ser
reconhecido no WhatsApp como qualquer outro responsável — o que com um booleano na ficha
não acontecia.

**(b) A ficha ganha tela e vira parte do formulário de aluno.** Um formulário só, em abas
(*Aluno* · *Responsáveis* · *Dados obrigatórios* · *Autorizações*), salvando `Aluno` +
`FichaMatricula` na mesma transação via `SalvarFichaMatricula` (já existe,
`ficha_use_cases.py`). Obrigatoriedade validada **no caso de uso**, não só no HTML
(`cor_raca` já é; acrescentar CPF, RA, data nasc, endereço, sexo, foto).
`laudo_cid` ganha o par `laudo_status ∈ nao/sim/em_investigacao` + `laudo_cid`, para
representar o "( ) EM INVESTIGAÇÃO" da ficha.

**(c) Foto do aluno.** Reusa a porta `ArquivoStorage` — que na Fase 0 já estará apontando
para o **S3** — em `Aluno.foto_arquivo_id`. Mesma disciplina do §6k: allowlist de MIME (só
JPEG/PNG/WebP), teto de tamanho, download por endpoint autenticado e auditado, `no-store`,
**sem URL pública**.

> **Prefixo próprio no bucket:** `foto/{tenant_id}/…`, separado de `doc/`. Não é organização
> — é que os dois têm **ciclos de vida diferentes**: o documento vence em
> `DOCUMENTO_RETENCAO_DIAS` (365 por padrão), a foto do aluno vive enquanto ele estiver
> matriculado. Uma regra de lifecycle só sabe separá-los por prefixo, e sem isso a foto de
> um aluno ativo seria apagada no aniversário do upload.

> ⚠️ **LGPD.** Foto de criança + CPF + laudo médico no mesmo registro é o ponto mais
> sensível da base (arts. 11 e 14). Este PR **precisa** passar pelo agente `lgpd-auditor`
> (§17) e atualizar `site/privacidade/` com as categorias novas (imagem, CPF, filiação,
> dados de trabalho do responsável). Não é opcional nem posterior.

### 2.4 · Usuários do sistema — cargos e hierarquia
**Apontado:** login para secretaria, diretor, vice-diretor e coordenador, com WhatsApp,
endereço completo, e-mail, senha, nome, cargo e expediente/turno. Todos menos a secretaria
são admins da escola e podem adicionar/remover usuários, **respeitando a hierarquia**.
**Diagnóstico:** `entities.py:374-392` — `Papel` tem dois valores e `Usuario` tem
nome/e-mail/senha. Não há cargo, telefone, endereço nem turno.
**Correção:**
- `Usuario` ganha `cargo` (enum `diretor` > `vice_diretor` > `coordenador` > `secretaria`),
  `telefone` (E.164), `endereco`, `turno`.
- `Papel` **não muda** (é a fronteira de autorização técnica). Quem tem
  `cargo != secretaria` recebe `papel = tenant_admin`; a secretaria recebe um papel novo
  `SECRETARIA`, sem permissão de gerir usuários.
- **Hierarquia:** um usuário só cria/edita/remove quem está **estritamente abaixo** dele.
  Coordenador não mexe em vice-diretor; ninguém se promove (a regra de `AtualizarUsuario`
  que já impede trocar `papel`/`tenant_id` passa a valer também para `cargo`).
- Bônus que sai de graça: `Usuario.telefone` destrava o item de roadmap **"notificar o
  atendente por WhatsApp/e-mail"** (§6j), hoje bloqueado exatamente por falta desse campo.

### 2.5 · Professores — campos reais
**Apontado:** nome, CPF, data nasc, nº de matrícula, endereço completo, telefone_1,
telefone_2, e-mail, senha, `prof_educacao_fisica` (bool), `prof_titular` (bool — falso =
eventual).
**Diagnóstico:** `entities.py:436-450` — `Professor` é deliberadamente enxuto (nome +
telefone + `senha_hash`).
**Correção:** acrescentar os campos. `prof_titular = false` conecta direto com o §I1
(chamada de eventual): a lista de candidatos a substituto deixa de ser digitada à mão e
passa a ser **os professores com `prof_titular = false`** — hoje `ChamarEventual` recebe a
lista de telefones do painel.
`prof_educacao_fisica` fica registrado, sem consumidor ainda (a "chamada estilo Tinder" foi
marcada pelo próprio apontamento como funcionalidade futura — **fora deste plano**).

---

## Fase 3 — Sessão de conversa e notificações (1 PR, ~2–3 dias)

### 3.1 · Nova instância de conversa a cada reabertura / 24 h
**Apontado:** conversas do mesmo número devem virar uma nova instância ao reabrir ou após
24 h; o histórico deve ser só o da última.
**Diagnóstico:** `backend/app/infrastructure/db/repositories.py:70-83` —
`obter_ou_criar` casa por `(tenant_id, contato)` **sem nenhum recorte de tempo**. É uma
conversa eterna por telefone. Duas consequências reais, não cosméticas:
1. o painel de histórico (`/admin/historico/conversas`) vira um fio infinito ilegível;
2. **o contexto enviado à LLM cresce sem limite** — cada mensagem nova carrega meses de
   assunto encerrado, o que encarece a chamada e piora a resposta (o modelo responde sobre
   a matrícula de março quando perguntam do uniforme de agosto).

**Correção:** conceito de **sessão de conversa**.
- `Conversa` ganha `encerrada_em` e `ultima_mensagem_em` (**migration `0033`**).
- `obter_ou_criar` passa a devolver a conversa **viva**: a que tem `encerrada_em IS NULL`
  **e** `ultima_mensagem_em` dentro de `CONVERSA_JANELA_HORAS` (default **24**, alinhado à
  janela da Meta, que é o mesmo relógio que o responsável percebe). Fora disso: encerra a
  anterior e abre uma nova.
- Resolver um `AtendimentoHumano` **encerra a sessão** ("reabertura" do apontamento). Se o
  responsável voltar, abre sessão nova — e o `RegistrarRetornoDoResponsavel`, que hoje
  ressuscita o atendimento resolvido, passa a fazê-lo na sessão nova.
- `AtenderConversa` monta o contexto da LLM **só com a sessão corrente**.
- O histórico do painel lista **sessões** (data, nº de mensagens, se houve atendimento
  humano) e abre uma por vez.
- Migration de dados: cada conversa existente vira uma sessão encerrada com
  `ultima_mensagem_em` = data da última mensagem.

### 3.2 · Sininho de notificações + alerta em tela
**Apontado:** o alerta de novo atendimento humano deve aparecer no sininho e como alerta na
tela; o mesmo para documentos recebidos (§4.4).
**Diagnóstico:** `web/components/layout/Topbar.tsx:63-70` — o sininho é **decorativo**: um
`<button>` sem `onClick`, com a bolinha vermelha **fixa no JSX**. Ele já mente hoje (avisa
sempre, mesmo com fila zerada). A única notificação real do produto é o badge da sidebar
(`Sidebar.tsx:156-172`).
**Correção:**
- `CentralDeNotificacoes`: um hook único que consolida as fontes (atendimentos pendentes +
  documentos a conferir, extensível), com o polling de 20 s que hoje está solto na sidebar.
- Sininho vira popover real com a lista e link para a fila; a bolinha só acende com
  contagem > 0.
- **Alerta em tela** quando a contagem *sobe* enquanto a aba está aberta: toast persistente
  (o `useToast` já existe) com som opcional. Só na transição — um alerta que reaparece a
  cada polling vira ruído e a secretaria aprende a ignorar, que é o oposto do pedido.

---

## Fase 4 — Documentos recebidos (1 PR, ~3–4 dias)

### 4.1 · Busca instantânea de aluno (tirar o dropdown)
**Diagnóstico:** `web/app/admin/documentos/page.tsx:114` —
`listarAlunos(undefined, true, 1, 200)`: um `<select>` com **teto de 200 alunos**. Uma
escola de porte médio já estoura isso, e o aluno 201 simplesmente **não pode ser
vinculado** — é um bug de dados disfarçado de UX.
**Correção:** `GET /api/admin/alunos/tenant/{id}?q=` (busca por nome/matrícula/RA,
`ILIKE`, teto de 20 resultados) + componente `BuscaAluno` (input com debounce de 250 ms).
Reaproveitável no vínculo de responsável e na ficha.

### 4.2 · Preview do arquivo
**Diagnóstico:** `backend/app/interfaces/api/documentos.py` — o endpoint `/arquivo` devolve
sempre `Content-Disposition: attachment`. Não há como exibir sem baixar.
**Correção:** parâmetro `?inline=true` que troca para `inline`, mantendo **intactas** as
demais garantias (autenticação, escopo por tenant, `no-store` e **auditoria** — visualizar
é acessar o dado, e o §6k é explícito em auditar todo acesso; o registro passa a distinguir
`documento.baixar` de `documento.visualizar`). No painel, modal com `<img>`/`<embed>` a
partir de um **blob URL** revogado ao fechar — nunca um `src` direto para a API com token
na URL.

### 4.3 · OCR por LLM para identificar o tipo e pré-preencher
**Apontado:** usar LLM especialista em OCR.
**Diagnóstico:** hoje a sugestão é heurística de palavra sobre a legenda
(`sugerir_categoria`, §6k) — decisão consciente e correta *para texto*. Mas a porta
`LLMProvider` é **só texto**: não há caminho para mandar uma imagem ao modelo.
**Correção:**
- porta nova `LeitorDocumento` no domínio (`ler(bytes, mime) -> DocumentoLido`), com
  adaptador `ClaudeLeitorDocumento` em `infrastructure/` usando o bloco `image`/`document`
  da API da Anthropic. Porta separada de `LLMProvider` de propósito: a capacidade é
  diferente e nem todo provedor a tem.
- fluxo **prévia → confirmação**, o mesmo já usado na importação em massa (§6c-quater) e na
  leitura de ficha (§D3): a LLM **sugere**, o código valida, a secretaria confirma. A
  sugestão nunca grava sozinha.
- pré-preenche: categoria, aluno provável (cruzando nome extraído com a busca do §4.1),
  e — quando for ficha de matrícula — os campos da `FichaMatricula`, que já tem o fluxo
  `PrevisualizarFichaMatricula` pronto esperando um OCR de verdade.
- **custo:** roda **sob demanda** (botão "Ler documento"), não em todo upload. Documento
  chegando por WhatsApp em época de matrícula é volume alto e a maioria a secretaria
  classifica de olho.

### 4.4 · Alerta de novos documentos
Mesmo mecanismo do §3.2 — entra como fonte na `CentralDeNotificacoes`. Endpoint
`GET /api/admin/documentos/pendentes` espelhando o `/atendimentos/pendentes`.

### 4.5 · Anti-spam e blacklist
**Apontado:** filtrar documentos não relacionados e mandar o número para a blacklist em
caso de recorrência — *"falta definir recorrência"*.
**Diagnóstico:** o inbound é público e aceita imagem/PDF de **qualquer** número
(`ProcessarInboundMeta`). As defesas atuais são MIME + 16 MB (§6k) — nenhuma delas olha
*conteúdo* nem *reincidência*.
**Correção em três camadas, da mais barata para a mais cara:**
1. **Origem desconhecida** (telefone sem `Contato` no tenant): o arquivo entra com
   `status = quarentena`, fora da fila de trabalho, com aviso na tela. Custo zero, e
   resolve o caso mais comum — número aleatório.
2. **Reincidência:** entidade `NumeroBloqueado` (tenant, telefone, motivo, `bloqueado_em`,
   `bloqueado_por`). Bloqueio **manual em um clique** a partir do documento, e **sugestão
   automática** ao cruzar o limiar.
3. **Conteúdo:** só quando o §4.3 existir — o `LeitorDocumento` classificando como
   "não relacionado" alimenta o contador. Não antes: sem leitura, "não relacionado" seria
   chute.

⚠️ **decisão C — o limiar.** Proposta: **3 documentos descartados do mesmo número em 7
dias** → o painel *sugere* o bloqueio; o bloqueio efetivo é sempre humano. Bloqueio
automático é perigoso aqui — um pai que manda três fotos tremidas do mesmo atestado é
indistinguível de spam para um contador, e bloqueá-lo em silêncio é exatamente a falha que
o produto existe para evitar. Número bloqueado **continua sendo atendido em texto**; só a
mídia é recusada, com aviso ao remetente.

---

## Fase 5 — Automação do ciclo de vida do responsável (1 PR, ~1 dia)

**Apontado:** o ciclo de vida do responsável deve ser ativado por automação, não por
clique.
**Diagnóstico:** `backend/app/interfaces/api/progressao.py:61-78` —
`InativarResponsaveisSemAlunosAtivos` só existe como `POST` disparado pelo botão em
`web/app/admin/progressao/`. O caso de uso é idempotente e seguro (só inativa quem tem
**todos** os alunos como ex-alunos), então automatizar é baixo risco.

**Correção — e a escolha aqui importa:** o projeto **não tem scheduler** (o §12a lista três
jobs agendados pendentes: expurgo de documentos, não-entrega, aviso de licença). Introduzir
um agendador só para este item seria desproporcional; não introduzir nenhum deixa quatro
itens travados.

Proposta em dois tempos:
1. **Agora, sem infra:** rodar a inativação **como passo final da promoção de turmas**, na
   mesma transação de `PromoverTurmas`, e também no `DesativarAluno` (limitado aos
   responsáveis daquele aluno). É nesses dois momentos que um responsável *de fato* deixa
   de ter aluno ativo — um cron diário estaria, 364 dias por ano, recalculando nada. Isto
   já entrega o apontamento: deixa de depender de clique.
2. **Depois, como item próprio:** um `APScheduler` no processo do back-end (ou um Cron Job
   no Render) rodando a rede de jobs pendentes — inativação de segurança, expurgo de
   documentos (§6k), não-entrega (§9b) e aviso de licença (§6e). **Fora deste plano**, mas
   fica registrado que os quatro esperam a mesma peça.

O botão manual permanece, como reprocessamento.

---

## Fora de escopo (registrado, não planejado)

- **Chamada de alunos "estilo Tinder"** — o próprio apontamento marca como funcionalidade
  futura.
- **Renomear `Sala` → `Turma` no domínio** — dívida anotada em §1.1; hoje só o rótulo muda.
- **Scheduler geral** — §5, tempo 2.
- **Cloudflare R2** — substituído pelo S3 (Fase 0). O item do roadmap §12a
  ("Adaptador de object storage (Cloudflare R2)") deve ser reescrito para S3 no CLAUDE.md,
  junto com o docstring de `storage.py`, que hoje aponta R2 como próximo passo.

---

## Ordem, dependências e migrations

```
Fase 0 (S3) ──┬────────────────→ Fase 2 (cadastro) ──┬──→ Fase 4 (documentos)
              │                                       │
              └───────────────────────────────────────┘
                                  Fase 2 ──→ Fase 5 (automação)

Fase 1 (tela + permissão) ──→ Fase 3 (sessão + sininho) ──→ Fase 4
```

- **Fase 0 precede a Fase 2**: a Fase 2 acrescenta a foto do aluno. Com o storage antigo,
  seriam fotos gravadas no Postgres para migrar de novo semanas depois.
- **Fase 0 precede a Fase 4**: o preview (§4.2) e o OCR (§4.3) leem os bytes; melhor que já
  estejam na casa definitiva antes de mexer no caminho de leitura.
- **Fase 4 depende da Fase 2**: a busca instantânea (§4.1) e o pré-preenchimento por OCR
  (§4.3) só fazem sentido com os campos novos de aluno.
- **Fase 3 depende da Fase 1**: o sininho consolida o polling que a §1.5 vai reescrever.
- **Fase 5 depende da Fase 2**: o gatilho está dentro do `DesativarAluno`.

**Fase 0 e Fase 1 são independentes entre si** e podem correr em paralelo — a Fase 1 não
toca em arquivo.

**Migrations, encadeadas linearmente** a partir do head atual `0030_documentos_recebidos`
(§6 do CLAUDE.md — head único, senão o `alembic upgrade head` do deploy quebra):

| # | Migration | Fase |
|---|---|---|
| `0031` | `fonte_conhecimento_conteudo` | 1 |
| `0032` | `cadastro_completo` (sala, contato, aluno+foto, usuario, professor) | 2 |
| `0033` | `conversa_sessao` | 3 |
| `0034` | `numeros_bloqueados` | 4 |
| `0035` | `arquivo_sem_bytea` — `DROP COLUMN`, **só depois do backfill provado** | 0 · tempo 2 |

A Fase 0 é a única que **não tem migration no seu próprio PR**: o adaptador, a fábrica e o
fallback entram sem tocar no schema, e o `DROP COLUMN` vem num follow-up separado, quando os
bytes já estiverem no bucket. É de propósito — é o que torna a troca reversível por deploy.

---

## ✅ Decisões — respondidas em 11/ago/2026

| # | Decisão | Resposta | O que isso implica |
|---|---|---|---|
| **A** | Base de conhecimento: remover vs. desativar | **Desativar** | O `DELETE` passa a exigir super admin; o admin da escola ganha `PUT .../ativo`, que tira os trechos do RAG **sem apagar o texto**. Reversível num clique. |
| **B** | Grade de horário | **Os dois, para comparar** | Entram as **duas telas** sobre a mesma coluna JSON: o formulário simples (turno + intervalo) e o editor aula-a-aula. Alternáveis por um seletor na tela da turma, gravando no mesmo `grade_horario`. A escolha fica para depois de ver as duas funcionando — e, como o formato é o mesmo, descartar uma delas depois é apagar componente, não migrar dado. |
| **C** | Blacklist: a recorrência | **Recomendação aceita** | 3 documentos descartados do mesmo número em 7 dias → o painel **sugere** o bloqueio. O bloqueio é sempre humano. Número bloqueado continua sendo atendido em texto; só a mídia é recusada. |
| **D** | Foto do aluno | **Opcional** | Sem campo obrigatório e sem "dispensa registrada" — o formulário aceita aluno sem foto, e a tela não cobra. Simplifica a validação e reduz o dado sensível guardado por padrão, o que é bom para a LGPD. |
| **E** | `telefone_2` nos disparos | **Recomendação aceita** | Não entra. `telefone` segue sendo o único número que roteia inbound e recebe outbound; `telefone_2` é contato de emergência, e a tela diz isso em texto para a secretaria não supor o contrário. |
| **F** | Região do bucket | **`sa-east-1`** (registrado) | Fase adiada. A env `AWS_REGION` já nasce com `sa-east-1` como valor de exemplo, para que a escolha não se perca. |
| **G** | SDK da AWS | **`aioboto3`** (registrado) | Fase adiada. Nenhuma dependência entra no `pyproject.toml` agora — acrescentar SDK sem adaptador seria peso morto no build. |

---

## Estimativa

| Fase | Escopo | Estimativa |
|---|---|---|
| 0 | Arquivos em S3 (adaptador, fábrica, fallback, backfill, MinIO no CI, bucket) | ~2–3 dias |
| 1 | Tela, permissão, refresh, nome do responsável | ~1 dia |
| 2 | Cadastro completo (4 entidades + migration + telas) | ~4–6 dias |
| 3 | Sessão de conversa + notificações | ~2–3 dias |
| 4 | Documentos (busca, preview, OCR, anti-spam) | ~3–4 dias |
| 5 | Automação do ciclo de vida | ~1 dia |
| | **Total** | **~13–18 dias** |

A estimativa da Fase 0 **não inclui** o trabalho de conta: criar o bucket, a CMK do KMS, o
usuário IAM e as regras de lifecycle é meia hora de console, mas depende de alguém com
acesso à conta AWS — e, se a conta ainda não existir, do cadastro e da forma de pagamento.

Cada fase é um PR próprio, em branch a partir da `main`, com o CI (ruff + alembic + pytest
+ typecheck do `web/`) verde antes do merge. A Fase 2 exige, além disso, o parecer do
agente `lgpd-auditor` e a atualização de `site/privacidade/`.
