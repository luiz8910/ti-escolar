# Administração, papéis e acesso

> Parte do guia do TI-Escolar — índice em [`CLAUDE.md`](../../CLAUDE.md).
> A numeração das seções (§6a, §9c, …) é a original: as referências cruzadas
> espalhadas pelos outros documentos continuam valendo.

### 6a. Administração e grupos

- **`Usuario`** com `papel` ∈ {`super_admin`, `tenant_admin`, `secretaria`} e `cargo` ∈
  {`diretor`, `vice_diretor`, `coordenador`, `secretaria`} (migration
  `0033_usuario_cargo_hierarquia`), mais contato (`telefone` E.164, `endereco`, `turno`).
  O super admin tem `tenant_id = NULL` e **não ocupa cargo**. Senhas com **PBKDF2-SHA256**
  (`app/infrastructure/security.py`, somente stdlib).
  - **`Papel` × `Cargo` existem separados de propósito.** `Papel` é a **fronteira de
    autorização**, checada por rota; `Cargo` é o posto na escola, que **ordena a
    hierarquia**. Colapsar os dois faria "coordenadora" virar regra espalhada por dezenas
    de guardas. O `papel` **decorre do cargo** (`Cargo.papel_correspondente`) e nunca é
    editável por si — senão daria para criar uma secretaria com acesso de admin.
  - **`Papel.SECRETARIA` é papel próprio, não um `tenant_admin` com um campo a mais**, para
    falhar **fechado**: uma rota que só pergunte "é tenant_admin?" recusa a secretaria por
    construção, em vez de liberar tudo porque alguém esqueceu de conferir o cargo. Ela
    opera a escola (atende a fila §6j, cadastra, dispara) mas **não gerencia contas** — é a
    exceção explícita do apontamento de 10/08.
  - **Hierarquia:** só se cria/edita/desliga quem está **estritamente abaixo**
    (`Usuario.manda_em`). Estritamente, e não "no mesmo nível ou acima", porque diretor
    editando diretor é como uma conta é tomada — inclusive trocando a senha. Três travas
    em `CriarUsuario`/`AtualizarUsuario`: criar acima de si, promover alguém (ou a si
    mesmo) ao próprio nível, e a secretaria mexer em contas. Editar a **própria** conta
    (nome, senha, contato) é sempre permitido; trocar o **próprio cargo**, nunca —
    promover-se é o ataque óbvio e rebaixar-se deixa a escola sem ninguém no topo.
    Cobertura: `tests/test_cargos_hierarquia.py`.
  - **`Usuario.telefone` destrava o roadmap** de notificar o atendente por WhatsApp (§6j),
    que estava parado exatamente por falta deste campo. O aviso de licença a vencer (§6e)
    passou a excluir a secretaria: cobrança não é assunto do balcão.
- **Permissões** (`CriarUsuario`): só super admin cria super admin; admin de tenant só cria/lista
  dentro do próprio tenant. Acesso a grupos exige `_exige_acesso_tenant` (403 fora do tenant);
  a gestão de contas exige `_exige_gestao_de_usuarios` (403 para a secretaria).
- **`Contato` (pai/responsável)** carrega o cadastro civil desde 12/ago/2026 (migration
  `0034_contato_responsavel`): `cpf`, `tipo_filiacao`, `data_nascimento`, `telefone_2`,
  `local_trabalho`, `telefone_trabalho`, `email`. Único por `(tenant_id, telefone)` **e**
  por `(tenant_id, cpf)` quando informado (UNIQUE parcial, como em `professores`).
  - **Só `telefone` roteia a conversa.** É a chave do inbound (o webhook entrega o
    remetente, não o id do contato) e do outbound. `telefone_2` e `telefone_trabalho` são
    contato de emergência e **não entram em disparo** — dois números na mesma conversa
    quebrariam o roteamento (decisão E do plano de 10/08).
  - **O termo de guarda deixou de ser um booleano.** Estava modelado como
    `FichaMatricula.termo_guarda` + um nome solto em `responsavel_legal`, o que deixava
    quem responde pela criança **invisível para o canal**: não recebia disparo, não era
    reconhecido no WhatsApp, não contava na cobertura da turma. Agora é um `Contato` com
    `tipo_filiacao = responsavel_legal`, ligado ao aluno por `aluno_responsaveis`. A tela
    de Alunos tem o botão que cadastra e vincula num passo só.
  - **`tipo_filiacao` fica no `Contato`, não na associação com o aluno** — é assim que a
    secretaria cadastra e enxerga ("a mãe", "o responsável legal"). O caso de alguém ser
    mãe de um aluno e guardiã de outro na mesma escola existe, mas é raro o bastante para
    não justificar hoje um campo por vínculo; quando aparecer, ele entra em
    `aluno_responsaveis`.
  - **Mínimo continua sendo nome + telefone**: é o que a importação em massa (§6c-quater)
    produz e o que a escola tem quando a mãe manda o número pelo WhatsApp.
- **`Grupo`** (por tenant) agrega **`Contato`s** (N:N via `grupo_contatos`). `EnviarBroadcastParaGrupo` resolve os membros do grupo em destinatários
  e delega a `EnviarBroadcast` (template aprovado + cota + rate limit).
- **Seed** (`app/seed.py`) cria: super admin, admin do tenant demo, e grupos ("Turma 5º A",
  "Pais do Fundamental I") com contatos. Credenciais default em `.env.example`
  (`SUPER_ADMIN_*`, `DEMO_ADMIN_*`) — **trocar em produção**.
- **Rotas** em `app/interfaces/api/admin.py`: `/api/admin/login`, `/usuarios`, `/grupos`,
  `/grupos/{id}/contatos`, `/grupos/{id}/enviar`. **Autenticação por JWT (HS256):** o
  `POST /api/admin/login` devolve `{ access_token, expira_em, usuario }`; as demais rotas
  exigem `Authorization: Bearer <token>`. O token é assinado com `JWT_SECRET` e expira
  conforme `JWT_EXPIRA_MINUTOS` (default 480 min). A dependência `usuario_autenticado`
  decodifica o token (`app/infrastructure/security.py`, só stdlib) e **revalida o usuário
  no banco** (existência + `ativo`) a cada requisição. O painel guarda o token no
  `localStorage` (`web/lib/admin.ts`) e o reenvia no cabeçalho `Authorization`.
- **Escola em foco (super admin).** O `tenant_admin` é amarrado à sua escola; o super admin
  tem `tenant_id = NULL` e precisa **dizer** sobre qual escola está operando. Até 11/ago/2026
  não dizia: `tenantEmFoco()` caía num `DEMO_TENANT_ID` e **toda tela de escola** —
  instruções, base de conhecimento, alunos, turmas, atendimentos, documentos — agia em
  silêncio sobre a escola de demonstração. Agora a escolha é explícita
  (`getEscolaEmFoco`/`setEscolaEmFoco`, guardada ao lado da sessão e **descartada no
  logout**), feita no `SeletorDeEscola` da `Topbar` ou ao abrir `/admin/escolas/[tenantId]`.
  Sem escolha, `tenantEmFoco()` **lança** em vez de chutar, e a `AppShell` mostra o pedido de
  escolha no lugar da tela (`exigeEscola={false}` nas telas cross-tenant: escolas, segurança,
  logs). O `POST /login` passou a devolver `usuario.tenant_nome`, porque a barra lateral
  também exibia "Escola Demonstração" cravado em toda página, para toda escola.
