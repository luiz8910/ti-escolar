# Documentos recebidos dos responsáveis

> Parte do guia do TI-Escolar — índice em [`CLAUDE.md`](../../CLAUDE.md).
> A numeração das seções (§6a, §9c, …) é a original: as referências cruzadas
> espalhadas pelos outros documentos continuam valendo.

### 6k. Documentos recebidos dos responsáveis pelo WhatsApp

A dor é de época de matrícula, e é concreta: hoje a foto do atestado, do RG e do
comprovante de residência chega **no celular pessoal de alguém da secretaria**. O
documento vira responsabilidade daquela pessoa — se ela falta, tira férias ou troca de
aparelho, o documento some, e a escola não tem nem como saber que ele existiu. Aqui o
arquivo passa a pertencer à escola, ligado à conversa que o originou.

- **`DocumentoRecebido`** (migration `0030_documentos_recebidos`): `categoria` ∈
  {`matricula`, `atestado`, `comprovante`, `outro`}, `status` ∈ {`recebido`, `processado`,
  `descartado`}, vínculos opcionais com `Aluno` e com o `AtendimentoHumano` aberto (§6j),
  `media_id` para deduplicar reentrega, e **`expira_em` preenchido no nascimento**.
- **Duas tabelas, de propósito.** `documentos_recebidos` é **negócio** (o que a secretaria
  consulta e classifica); `arquivos_armazenados` é **infraestrutura** — os bytes, hoje em
  `bytea`. A separação é o que permite trocar o armazenamento sem tocar nos metadados.
- **Porta `ArquivoStorage`** com `PostgresArquivoStorage` (produção hoje) e
  `ArquivoStorageMemoria` (testes). **Dito sem rodeio:** guardar atestado médico num banco
  cobrado por GB é aceitável para começar, não para sempre — uma escola em época de
  matrícula sobe centenas de fotos. O adaptador de object storage (Cloudflare R2, conta
  que já existe pela landing page, sem custo de egress) é **[Roadmap]**, e a porta existe
  para que ele entre barato. Não foi implementado às cegas: sem credencial para testar
  contra o serviço real, iria para produção sem nunca ter escrito um byte.
- **Porta `FonteMidia`** + `MetaFonteMidia`: na Meta o download tem **dois passos**
  (`GET /{media_id}` → URL **temporária**, que só entrega com o mesmo `Bearer`). Por isso o
  arquivo é baixado **na hora** — guardar a URL daria um registro que expira sozinho em
  minutos, e a secretaria descobriria isso no dia em que precisasse do atestado.
- **Duas defesas antes de qualquer byte entrar no banco:** allowlist de MIME
  (`MIMES_ACEITOS`: JPEG/PNG/WebP/PDF/DOC/DOCX) e teto de 16 MB, conferido **antes** pelo
  `content-length` e **depois** pelo tamanho real — o cabeçalho é declarado pela outra
  ponta. O inbound é público: quem descobre o número da escola manda o que quiser.
- **Áudio fica de fora**, declarado: sem transcrição é um arquivo que alguém precisa parar
  para ouvir, o oposto do que a feature promete.
- **Inbound** (`ProcessarInboundMeta`): `image` e `document` deixaram de ser ignorados
  (§9e.1). O arquivo entra no fio da conversa **antes** do download — se a Graph API
  falhar, o histórico ainda mostra que o responsável tentou enviar algo, que é o que
  permite cobrar o reenvio. A confirmação ("recebemos o seu arquivo") sai **mesmo com a
  conversa em atendimento humano**: é recibo de entrega, não resposta ao assunto, e sem ela
  o pai reenvia a mesma foto três vezes.
- **Sugestão de finalidade sem LLM:** `sugerir_categoria` é heurística de palavra sobre a
  legenda. Chamar o modelo para adivinhar o que a secretaria confirma em um clique não paga
  a latência nem o custo — e palpite errado com ar de certeza é pior que nenhum palpite.
  `categoria_sugerida` fica registrada à parte da confirmada.
- **Rotas** `app/interfaces/api/documentos.py` (`/api/admin/documentos`): listar, detalhar,
  **baixar**, classificar e `POST /expurgar` (super admin). Painel
  `web/app/admin/documentos/`, com filtro padrão "a conferir" — a tela é fila de trabalho,
  não arquivo morto.
- **⚠️ LGPD — este é o dado mais sensível da base.** Atestado médico é dado de saúde de
  criança (arts. 11 e 14). Quatro decisões vêm daí: **prazo de retenção**
  (`DOCUMENTO_RETENCAO_DIAS`, default 365) com expurgo que apaga **bytes e metadado**
  (manter "havia um atestado do aluno X" sem o arquivo seria tratamento sem utilidade);
  **nenhuma URL pública** — os bytes só saem pelo endpoint autenticado, com `no-store`;
  **todo download auditado** (`documento.baixar`, §13); e a **política de privacidade**
  (`site/privacidade/`) declarando a categoria e o prazo. A medida `retencao_documentos`
  entra no painel §14 e acusa `ATENCAO` se o prazo for 0.
- **Cobertura:** `tests/test_documentos_recebidos.py` (25 testes: allowlist, teto, dedupe,
  isolamento entre escolas, download de arquivo já expurgado, expurgo tolerante a falha,
  envelope de mídia do webhook, áudio ignorado, texto intacto).
- **[Roadmap]** adaptador R2; **job agendado** do expurgo (hoje depende de alguém clicar);
  ligação automática com a `SolicitacaoMatricula` (§E1) e a `FichaMatricula` (§D3).

#### 6k.1 Buscar o aluno, ver o arquivo, ler por IA (Fase 4 do plano de 10/08)

Três apontamentos do teste manual, e o primeiro era um bug de dados disfarçado de UX.

- **Busca de aluno no servidor.** A tela carregava **200 alunos** num `<select>`: a partir do
  aluno 201 não havia como vincular documento nenhum, e o problema aparece justamente no
  aluno que ninguém procurou ainda. `AlunoRepository.listar/contar` passaram a aceitar `q`
  (nome ou matrícula, `ILIKE`), e `web/components/admin/BuscaAluno.tsx` busca com debounce,
  teto de 20 resultados e mínimo de 2 letras — uma letra traria meia escola.
- **Ver, não só baixar** (`?inline=true`): o `Content-Disposition` vira `inline` e o painel
  monta um **blob URL** a partir do endpoint autenticado, revogado ao fechar. Nunca um `src`
  com token na URL. Visualizar **é acessar o dado**, então é auditado à parte
  (`documento.visualizar` × `documento.baixar`) — quem audita precisa distinguir quem olhou
  na tela de quem levou o arquivo embora.
- **Leitura por IA** (`LerDocumentoPorIA`, porta `LeitorDocumento` + `AnthropicLeitorDocumento`):
  manda os **bytes** do arquivo ao modelo (bloco de imagem/documento, não OCR próprio) e
  devolve finalidade, aluno mencionado, resumo e campos de ficha. É **sugestão**, no mesmo
  fluxo prévia→confirmação da importação em massa (§6c-quater) e da ficha (§D3): a secretaria
  aplica com um clique ou ignora. **Documento ilegível é resultado normal**, não erro — vem
  em `erro` e a tela diz isso sem parecer falha. Os campos de ficha são só exibidos: preencher
  a ficha a partir daqui gravaria dado sensível de menor sem ninguém olhar.

#### 6k.2 Anti-spam: quarentena e bloqueio de mídia (§4.5)

O inbound é público — quem descobre o número da escola manda o que quiser, e a §6k já barra
MIME e tamanho. Falta**va** barrar *quem*.

- **Quarentena de desconhecido:** arquivo vindo de um telefone **sem `Contato` cadastrado**
  entra como `StatusDocumento.QUARENTENA` em vez de `recebido`. Não é recusa — a secretaria
  vê, confirma e classifica; é só o que separa a fila de trabalho do que chegou de fora.
- **`NumeroBloqueado`** (migration `0041_anti_spam_documentos`, único por `(tenant_id, telefone)`):
  recusa **o envio de arquivos**, não a pessoa. O número **segue sendo atendido por texto** —
  silenciar alguém por completo com base num contador é exatamente o erro que este produto
  existe para evitar, e o remetente pode ser o pai certo com o telefone errado no cadastro.
- **A sugestão é da máquina; o bloqueio é humano** (decisão C): `SugerirBloqueios` aponta os
  números com `DESCARTES_PARA_SUGERIR_BLOQUEIO` (3) descartes em `JANELA_DESCARTES_DIAS` (7).
  Bloqueio automático não existe — ele erraria calado, e o custo do erro é uma escola que
  para de receber os documentos de matrícula de uma família.
- **Rotas** em `api/documentos.py`: `POST /{id}/ler`, `GET .../sugestoes-bloqueio`,
  `GET .../bloqueados`, `POST /bloqueados`, `DELETE /bloqueados/{telefone}`.
