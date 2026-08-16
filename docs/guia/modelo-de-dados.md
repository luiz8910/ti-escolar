# Modelo de dados (multi-tenant)

> Parte do guia do TI-Escolar — índice em [`CLAUDE.md`](../../CLAUDE.md).
> A numeração das seções (§6a, §9c, …) é a original: as referências cruzadas
> espalhadas pelos outros documentos continuam valendo.

## 6. Modelo de dados (multi-tenant)

- **Isolamento por `tenant_id`** (escola) em todas as tabelas relevantes.
- Entidades principais: `Tenant` (escola), `Usuario` (admin), `Conversa`, `Mensagem`,
  `Documento`, `Conhecimento` (FAQ/aviso/procedimento), `MessageTemplate` (+ `TemplateNaWaba`,
  o status dele em cada conta), `Waba` (conta do WhatsApp Business), `Broadcast`/Campanha,
  `MessageQuota`, `Contato` (pai/responsável), `Grupo` + associação `grupo_contatos`,
  `Sala` (turma) + associação `sala_contatos`, `Professor` (vinculado à série por
  `Sala.professor_id`; `ativo` marca o vínculo vivo — desligado, o número deixa de ser
  reconhecido no inbound), `FonteConhecimento` (documento da escola),
  `PromptTenant` (system prompt da escola), `ResumoEscola` (visão agregada do super admin),
  `SolicitacaoInterna` (canal professor→escola), `MensagemMediada` (canal pai↔professor),
  `CotaImpressao` (franquia mensal de impressão), `AvisoFalta` (falta de professor +
  chamada de eventual), `FichaMatricula` (ficha de matrícula digital, 1:1 com `Aluno`) e
  `SolicitacaoMatricula` (matrícula self-service pelo WhatsApp) e
  `AtendimentoHumano` (fila da secretaria quando o assistente encaminha a conversa) e
  `DocumentoRecebido` (arquivo que o responsável enviou pelo WhatsApp).
  `Contato` tem flag `ativo` (responsável inativo — todos os alunos já são ex-alunos).
- **Embeddings:** tabela `conhecimento` com coluna `vector` (pgvector) + metadados para RAG;
  `fonte_id` liga cada trecho à `FonteConhecimento` que o originou.
- **Migrations:** `0001_initial` → `0002_admins_grupos` → `0003_salas` →
  `0004_conhecimento_prompt` → `0005_alunos` → `0006_licenciamento_tenant` →
  `0006_destinatario_entrega` → `0007_auditoria` → `0007_ficha_financeira_tenant` →
  `0008_professores` → `0009_tenant_whatsapp` → `0010_template_content_sid` →
  `0011_tenant_telefone_contato` → `0012_respostas_rapidas` → `0013_avisos_temporizados` →
  `0014_solicitacoes_impressao` → `0015_mural_professor` → `0016_solicitacoes_internas` →
  `0017_mensagens_mediadas` → `0018_cota_impressao` → `0019_contato_ativo` →
  `0020_avisos_falta` → `0021_ficha_matricula` → `0022_solicitacoes_matricula` →
  `0023_remover_content_sid` → `0024_tenant_meta_phone_number_id` → `0025_controle_taxa` →
  `0026_inbound_atendimento` → `0027_logs_aplicacao` → `0028_aluno_soft_delete` →
  `0029_atendimento_humano` → `0030_documentos_recebidos` →
  `0031_fonte_conhecimento_conteudo` → `0032_professor_cadastro_completo` →
  `0033_usuario_cargo_hierarquia` →
  `0034_contato_responsavel` → `0035_aluno_foto` →
  `0036_turma_estruturada` →
  `0037_conversa_sessao` → `0038_impressao_whatsapp` → `0040_templates_catalogo` →
  `0041_anti_spam_documentos` → `0042_wabas_multiplas` → `0043_destinatario_erro`.
  ⚠️ **O `0039` não existe, e o `0041` já se chamou `0038`.** Três migrations foram
  escritas em paralelo apontando para a `0037`; a ordem de merge decidiu o resto. A do
  anti-spam quase se perdeu: o PR #55 foi mergeado numa branch de feature que **já tinha
  ido para a `main` por squash**, e o trabalho ficou órfão em
  `feat/documentos-busca-preview-ocr` por um dia, com o GitHub exibindo o PR como
  mergeado. **Merge verde não é prova de que o código está na `main`** — confira o
  `baseRefName` quando o PR sair de uma branch que não é a `main`.
  O número é rótulo: quem define o grafo é o `down_revision`. O CI passou a recusar mais
  de um head, então o esquecimento falha o build em vez de quebrar o deploy — que ali
  significa **o container não subir**, porque o `alembic upgrade head` roda no `CMD`.
  ⚠️ **O id da revisão cabe em 32 caracteres** — `alembic_version.version_num` é
  `VARCHAR(32)`. Estourar dá `StringDataRightTruncation` **só na hora de aplicar**, nunca
  ao escrever, e três migrations do projeto estão em exatamente 32. Conte antes.
  **Cadeia linear obrigatória:** ao criar uma migration, encadeie no head atual
  (`down_revision` = último head) para evitar **multiple heads** no `alembic upgrade head`
  do deploy.
- Toda consulta deve ser **escopada por tenant**; nunca vazar dados entre escolas.
