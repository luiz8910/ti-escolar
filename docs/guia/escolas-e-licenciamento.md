# Escolas (tenants), licenciamento e ficha financeira

> Parte do guia do TI-Escolar — índice em [`CLAUDE.md`](../../CLAUDE.md).
> A numeração das seções (§6a, §9c, …) é a original: as referências cruzadas
> espalhadas pelos outros documentos continuam valendo.

### 6d. Gestão de escolas (super admin)

- **CRUD de escolas (`Tenant`):** apenas o **super admin** cria/edita/remove escolas
  (`app/application/tenant_use_cases.py`: `CriarEscola`, `ListarEscolas`, `ObterEscola`,
  `AtualizarEscola`, `RemoverEscola`). `Tenant` é único por `slug`. A **remoção é em cascata
  explícita** (`SqlTenantRepository.remover` apaga, na mesma transação, mensagens → conversas →
  conhecimento → broadcasts → grupos/contatos → usuários → tenant, pois as FKs não têm
  `ON DELETE CASCADE`).
- **Visão cross-tenant:** `ListarEscolas` devolve `ResumoEscola` (totais de conversas, contatos e
  broadcasts por escola); o super admin também inspeciona **conversas + mensagens**
  (`ObterConversaDaEscola`) e **broadcasts** de cada escola.
- **Número de WhatsApp por escola (`Tenant.whatsapp_numero`, E.164):** cada escola atende/dispara
  pelo seu próprio número (multi-tenant). `CriarEscola`/`AtualizarEscola` recebem o número,
  **normalizam** para E.164 (`normalizar_whatsapp`, aceita DDI internacional) e **validam a
  unicidade** entre escolas (`TenantRepository.por_whatsapp`; dois tenants com o mesmo número
  tornariam o inbound ambíguo). Vazio = usa o número padrão do canal (`META_PHONE_NUMBER_ID`).
  Migration `0009_tenant_whatsapp`. Hoje é sobretudo a **referência humana** do número: quem
  roteia o inbound e assina o outbound é o `meta_phone_number_id` (abaixo). **Modelo
  operacional:** cada escola opera com um **número dedicado** à plataforma, **adquirido e
  registrado por nós** (o número antigo da secretaria segue livre para o atendimento manual) —
  ver §9e.3.
- **`phone_number_id` da Meta por escola (`Tenant.meta_phone_number_id`):** o identificador do
  número **na Meta** — o que a Graph API exige na URL de envio (`/{phone_number_id}/messages`) e
  o que o webhook devolve em `value.metadata.phone_number_id`. **É o que faz o multi-tenant
  funcionar de verdade:** roteia o inbound para a escola certa (`por_meta_phone_number_id`) e é
  o remetente do outbound (via `Tenant.remetente_canal`). `CriarEscola`/`AtualizarEscola`
  normalizam (`normalizar_meta_phone_number_id`, só dígitos) e **validam a unicidade** entre
  escolas. Vazio = a escola **não recebe** inbound (a mensagem é descartada) e dispara pelo
  número padrão da env. Migration `0024_tenant_meta_phone_number_id` (índice UNIQUE parcial).
  Ver §9e.1.
- **Conta do WhatsApp por escola (`Tenant.waba_id` → `Waba`):** em qual **WABA** o número
  desta escola está cadastrado. Não é o mesmo que `meta_phone_number_id`: o número roteia a
  mensagem, a conta responde pelo **catálogo de templates**. É o que diz onde criar o
  template da escola e onde conferir a aprovação antes de um disparo — template é aprovado
  por conta, e uma conta não comporta todas as escolas (§9a-ter, §9e.3). Nulo = a escola
  dispara pelo número mas tem o disparo **por template** recusado. Migration
  `0042_wabas_multiplas`.
- **Telefone de contato por escola (`Tenant.telefone_contato`, E.164):** o número **público** que
  a secretaria já usa no dia a dia — apenas **informativo** (referência de contato). É
  **obrigatório** no cadastro/edição (`CriarEscola`/`AtualizarEscola` via
  `normalizar_telefone_contato`), mas **não roteia inbound**, **não é remetente do outbound** e
  **não exige unicidade** entre escolas (duas escolas podem compartilhá-lo). Migration
  `0011_tenant_telefone_contato`. Distinto de `whatsapp_numero` (o número operado pela plataforma).
- **Rotas** em `app/interfaces/api/admin.py` (guard `_exige_super_admin`): `/api/admin/escolas`
  (POST/GET), `/escolas/{tenant_id}` (GET/PUT/DELETE), `/escolas/{tenant_id}/conversas`,
  `/escolas/{tenant_id}/conversas/{conversa_id}` e `/escolas/{tenant_id}/broadcasts`. `EscolaEntrada`
  e `Escola(Resumo)Saida` carregam `whatsapp_numero` e `telefone_contato`.
- **Painel:** `web/app/admin/escolas/` (lista com campo de WhatsApp no cadastro/edição + detalhe por
  `[tenantId]`).

### 6e. Licenciamento, cobrança e bloqueio (super admin)

- **Estado no `Tenant`:** `status` ∈ {`ativo`, `bloqueado`, `cancelado`} + `motivo_bloqueio`/
  `bloqueado_em` e `motivo_cancelamento`/`cancelado_em`; a licença `plano` ∈ {`mensal`, `anual`}
  + `licenca_expira_em`; e a cobrança `valor_mensal_centavos`/`valor_anual_centavos`. Propriedades
  de domínio: `bloqueado`, `cancelado`, `acesso_suspenso`, `motivo_suspensao`, `mrr_centavos`,
  `arr_centavos`, `dias_para_expirar`, `licenca_expirada`, `licenca_a_vencer(dias_aviso)`.
  Migrations `0006_licenciamento_tenant` e `0007_ficha_financeira_tenant`.
- **Bloqueio e cancelamento:** `BloquearEscola`/`DesbloquearEscola` (suspensão reversível) e
  `CancelarEscola`/`ReativarEscola` (churn, com `motivo_cancelamento`/`cancelado_em`), em
  `app/application/tenant_use_cases.py`, só super admin. Tanto a escola **bloqueada** quanto a
  **cancelada** (`acesso_suspenso`) perdem acesso ao painel (`POST /login` recusa o
  `tenant_admin` com 403 + motivo) **e aos disparos** (guard `_exige_tenant_ativo` em
  `/grupos/{id}/enviar` e em `POST /api/broadcasts`). O super admin segue entrando.
- **Licença e preços:** `DefinirLicenca` ajusta plano, data de expiração e (opcionalmente) os
  preços por ciclo (`valor_*_centavos`; só altera quando informados). O contador "quanto falta
  para expirar" é `dias_para_expirar` (exposto em `LicencaSaida`).
- **Aviso por e-mail:** `NotificarLicencasAVencer` avisa os `tenant_admin` das escolas com
  **plano anual** dentro da janela `LICENSE_WARNING_DAYS` (default 30) do vencimento. Porta
  `EmailSender` no domínio; adaptadores `LogEmailSender` (mock/log) e **`ResendEmailSender`**
  (envio real via API HTTP do resend.com), escolhidos por `EMAIL_PROVIDER`
  (`app/infrastructure/messaging/email.py`, fábrica `criar_email_sender`). Com
  `EMAIL_PROVIDER=resend` e `RESEND_API_KEY` vazia, cai no log em vez de derrubar o deploy.
  Falha do provedor é registrada e engolida: o aviso percorre várias escolas e a recusa de uma
  não pode interromper as demais. Disparável pelo super admin via
  `POST /api/admin/licencas/notificar-vencimento` (ou por um job agendado).
- **Rotas** (super admin, `app/interfaces/api/admin.py`): `/escolas/{tenant_id}/bloquear`,
  `/escolas/{tenant_id}/desbloquear`, `/escolas/{tenant_id}/cancelar`,
  `/escolas/{tenant_id}/reativar`, `PUT /escolas/{tenant_id}/licenca` e
  `/licencas/notificar-vencimento`.
- **Painel:** `web/app/admin/escolas/` (badge de status/expiração, modais de bloqueio, cancelamento
  e licença — esta com os preços por ciclo —, botão "Avisar vencimentos") e o detalhe `[tenantId]`
  (faixa de licença). Badge reutilizável em `web/components/admin/LicencaBadge.tsx`. Login
  bloqueado/cancelado mostra o motivo.

### 6f. Ficha financeira / histórico da escola (super admin)

- **Visão derivada (sem ledger de faturas):** `ObterFichaFinanceira`
  (`app/application/tenant_use_cases.py`, só super admin) monta o value object
  `FichaFinanceiraEscola` a partir do `Tenant` + `MetricasUsoEscola` (contadores via
  `TenantRepository.metricas_uso`) + a cota diária Meta (`META_DAILY_TIER_LIMIT`). Consolida:
  **ciclo de vida** (`criado_em` = data de início, `dias_de_casa`, `cancelado_em`/motivo),
  **cobrança** (preços, `mrr_centavos`/`arr_centavos`, `receita_acumulada_centavos` = LTV estimado
  por `meses_ativos × MRR`, `status_pagamento` derivado da licença), **próxima renovação**
  (`licenca_expira_em`), **uso** (usuários ativos, contatos, alunos, conversas, broadcasts) e um
  **`health_score`** heurístico (licença + bloqueio + tier de envio).
- **Endpoint:** `GET /api/admin/escolas/{tenant_id}/ficha-financeira` (`FichaFinanceiraSaida`).
- **Painel:** card "Ficha financeira" no detalhe `web/app/admin/escolas/[tenantId]/` (métricas de
  cobrança, uso e saúde); preços editáveis no modal de licença da lista `web/app/admin/escolas/`.
