"""Postura de segurança da plataforma — auditoria interna do super admin (§14).

O caso de uso não lê variáveis de ambiente: recebe um retrato já coletado
(``ConfiguracaoSeguranca``) montado na camada de interface. Assim a regra que decide se uma
medida está ``ATIVA``, em ``ATENCAO`` ou ``PENDENTE`` fica testável sem tocar em config.

Regra de honestidade: uma medida só aparece como ``ATIVA`` quando existe **no código** e a
configuração em uso não a enfraquece. Medida planejada e ainda não implementada é
``PENDENTE`` — um painel de auditoria que dourasse a pílula não serviria para auditar nada.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.entities import (
    ItemChecklist,
    MedidaSeguranca,
    PosturaSeguranca,
    StatusMedida,
)

# Fonte externa do checklist de pré-deploy (§15 do CLAUDE.md).
CHECKLIST_FONTE = (
    "https://github.com/moalsayed95/cookbook/blob/main/topics/pre-deployment-checklist"
)


@dataclass(frozen=True)
class ConfiguracaoSeguranca:
    """Retrato da configuração vigente, coletado pela camada de interface."""

    canal: str
    # Webhook da Meta
    meta_validate_signature: bool
    meta_app_secret_definido: bool
    meta_verify_token_padrao: bool
    # Sessão / autenticação
    jwt_secret_padrao: bool
    jwt_expira_minutos: int
    # Exposição
    cors_liberado: bool
    # Ambiente declarado (APP_ENV): "production" no Render, "development" no local.
    app_env: str
    # Limite de taxa de entrada (login e inbound). Defaults preservam a leitura de quem
    # constrói a configuração sem esses sinais.
    rate_limit_habilitado: bool = True
    rate_limit_login_tentativas: int = 0
    rate_limit_inbound_mensagens: int = 0
    # Seed de demonstração habilitado no ambiente (SEED_DEMO).
    seed_demo_habilitado: bool = False
    # Observabilidade: logs persistidos e por quantos dias.
    logs_persistidos: bool = False
    logs_retencao_dias: int = 0
    # Token da Meta presente. Com ``canal`` diz se o WhatsApp está mesmo no ar: pedir "meta"
    # sem token faz a aplicação subir no canal demo, calada.
    meta_access_token_definido: bool = False
    # Retenção dos documentos que os pais enviam (§6k). 0 = sem expurgo, e o que fica
    # guardado para sempre é dado sensível de criança.
    documento_retencao_dias: int = 0
    # Onde os bytes dos arquivos moram: o **pedido** (ARQUIVO_STORAGE) e o **efetivo**. A
    # divergência entre os dois é o que a medida `storage_efetivo` acusa.
    arquivo_storage: str = "postgres"
    arquivo_storage_efetivo: str = "postgres"
    # Região do bucket. Fora do Brasil, guardar laudo de menor vira transferência
    # internacional (LGPD arts. 33-36) e exige base legal declarada.
    aws_region: str = "sa-east-1"
    # Escolas ativas sem conta do WhatsApp (`Tenant.waba_id`) vinculada. É contagem de
    # banco, não de env: a configuração aqui está no cadastro.
    escolas_sem_conta_whatsapp: int = 0


# Segredos que vêm no .env.example e nunca devem sobreviver ao deploy.
JWT_SECRET_PADRAO = "troque-este-segredo-jwt"
META_VERIFY_TOKEN_PADRAO = "changeme"


class AvaliarPosturaSeguranca:
    """Monta a lista de medidas protetivas com o status real de cada uma."""

    def executar(self, *, config: ConfiguracaoSeguranca) -> PosturaSeguranca:
        return PosturaSeguranca(
            medidas=[
                *self._integridade_webhook(config),
                *self._autenticacao(config),
                *self._isolamento(),
                *self._rastreabilidade(config),
                *self._exposicao(config),
            ],
            checklist=self._checklist_pre_deploy(config),
            checklist_fonte=CHECKLIST_FONTE,
        )

    # -- Checklist de pré-deploy (fonte externa) ---------------------------

    def _checklist_pre_deploy(self, c: ConfiguracaoSeguranca) -> list[ItemChecklist]:
        """Os 9 itens da lista de origem, auditados contra o código.

        Mantido em ordem e com a numeração original para conferência 1:1 — quem audita
        precisa conseguir cruzar item a item com a fonte, sem reinterpretar.
        """
        return [
            ItemChecklist(
                numero=1,
                titulo="Autorização — cada usuário preso aos próprios dados",
                exigencia="Todo endpoint verifica a identidade e o escopo de quem chama.",
                status=StatusMedida.ATIVA,
                situacao=(
                    "Guardas _exige_acesso_tenant, _exige_super_admin e _exige_tenant_ativo em "
                    "todas as rotas administrativas, com o usuário revalidado no banco a cada "
                    "requisição. Em 27/jul/2026 fecharam-se os furos de POST /api/broadcasts e "
                    "da consulta de cota, que recebiam tenant_id sem exigir login."
                ),
                medidas_relacionadas=["multi_tenant", "papeis", "jwt_sessao"],
            ),
            ItemChecklist(
                numero=2,
                titulo="Link de redefinição de senha expira",
                exigencia="Token de uso único e TTL curto no reset de senha.",
                status=StatusMedida.NAO_APLICAVEL,
                situacao=(
                    "Não existe fluxo de redefinição: a senha é definida pelo super admin "
                    "(administradores) ou pela secretaria (professores). Não há link a expirar. "
                    "Vira obrigatório no dia em que o autoatendimento de senha existir."
                ),
            ),
            ItemChecklist(
                numero=3,
                titulo="Validação de entrada — SQL injection e XSS",
                exigencia="Queries parametrizadas e saída escapada.",
                status=StatusMedida.ATIVA,
                situacao=(
                    "Nenhuma query em SQL cru — tudo passa pelo SQLAlchemy, que parametriza. "
                    "DTOs Pydantic validam toda a borda HTTP. No painel, React escapa por "
                    "padrão e não há nenhum dangerouslySetInnerHTML."
                ),
            ),
            ItemChecklist(
                numero=4,
                titulo="CORS restrito ao próprio domínio",
                exigencia="Sem curinga em produção.",
                status=(StatusMedida.ATENCAO if c.cors_liberado else StatusMedida.ATIVA),
                situacao=(
                    "BACKEND_CORS_ORIGINS está com '*': qualquer origem é aceita. O curinga "
                    "desabilita allow_credentials, mas ainda expõe a API a qualquer página."
                    if c.cors_liberado
                    else "Lista explícita de origens; o curinga só é aceito como escape hatch."
                ),
                medidas_relacionadas=["cors"],
            ),
            ItemChecklist(
                numero=5,
                titulo="Rate limiting",
                exigencia="Limite em login, reset, cadastro e operações caras.",
                status=(
                    StatusMedida.ATIVA if c.rate_limit_habilitado else StatusMedida.ATENCAO
                ),
                situacao=(
                    (
                        f"Login limitado a {c.rate_limit_login_tentativas} tentativas por "
                        f"janela (contadas por IP e por e-mail) e inbound a "
                        f"{c.rate_limit_inbound_mensagens} mensagens por remetente. O "
                        "contador vive no Postgres (tabela controle_taxa), então vale para "
                        "todas as réplicas e sobrevive a restart."
                    )
                    if c.rate_limit_habilitado
                    else (
                        "RATE_LIMIT_HABILITADO=false: o código existe, mas está desligado — "
                        "brute force livre contra as senhas de administrador e inbound sem "
                        "teto de consumo de LLM."
                    )
                ),
                medidas_relacionadas=["rate_limit_login", "rate_limit_inbound"],
            ),
            ItemChecklist(
                numero=6,
                titulo="Tratamento de erro — telas próprias",
                exigencia="Sem stack trace visível; erro com identificação para suporte.",
                status=StatusMedida.ATIVA,
                situacao=(
                    "O painel tem error.tsx, global-error.tsx e not-found.tsx, e o back-end "
                    "tem handlers próprios: toda resposta de erro carrega o id de correlação "
                    "(também no cabeçalho X-Request-Id), enquanto o traceback fica no log. É "
                    "o id que o usuário informa ao suporte e que localiza a falha em /admin/logs."
                ),
                medidas_relacionadas=["observabilidade"],
            ),
            ItemChecklist(
                numero=7,
                titulo="Índices nas consultas quentes",
                exigencia="Colunas frequentemente filtradas indexadas.",
                status=StatusMedida.ATIVA,
                situacao=(
                    "53 colunas com index=True nos modelos, cobrindo os tenant_id e as chaves "
                    "estrangeiras quentes. Índices compostos (ex.: tenant_id + criado_em nas "
                    "listagens) são otimização futura, não pendência."
                ),
            ),
            ItemChecklist(
                numero=8,
                titulo="Logging e monitoramento",
                exigencia="Log estruturado somado a alerta de falha crítica.",
                status=StatusMedida.ATENCAO,
                situacao=(
                    (
                        "A metade do logging está feita: logging configurado, id de correlação "
                        "por requisição, persistência no Postgres e painel em /admin/logs, com "
                        f"retenção de {c.logs_retencao_dias} dias. Falta a outra metade — "
                        "**alerta ativo**: ninguém é avisado de um erro; é preciso alguém abrir "
                        "o painel para descobrir. Fica ATENÇÃO até haver notificação "
                        "(e-mail/push) em falha crítica."
                    )
                    if c.logs_persistidos
                    else (
                        "Existe auditoria de negócio e loggers por módulo, mas a persistência "
                        "de log está desligada (LOG_PERSISTIR=false): uma falha em produção só "
                        "aparece se alguém abrir os logs do provedor no momento certo."
                    )
                ),
                medidas_relacionadas=["auditoria", "observabilidade"],
            ),
            ItemChecklist(
                numero=9,
                titulo="Estratégia de rollback",
                exigencia="Capacidade de reverter testada (blue-green ou equivalente).",
                status=StatusMedida.ATENCAO,
                situacao=(
                    "O procedimento está documentado passo a passo em docs/runbook-rollback.md "
                    "(Render, Vercel, Cloudflare, downgrade de migration e restauração via "
                    "Neon), mas NUNCA FOI EXECUTADO — segue em ATENÇÃO até o ensaio. Ponto "
                    "específico deste projeto: rollback de aplicação não desfaz migration, e o "
                    "CMD do container reaplica `alembic upgrade head` a cada restart."
                ),
            ),
            ItemChecklist(
                numero=10,
                titulo="Política de backup (extra ao checklist de origem)",
                exigencia="Cópia fora do provedor do dado, com restauração testada.",
                status=StatusMedida.PENDENTE,
                situacao=(
                    "Existe apenas o point-in-time recovery do Neon, que cobre erro de operação "
                    "recente mas mora dentro do mesmo provedor: perda de conta ou corrupção "
                    "descoberta depois da janela de retenção não têm de onde voltar. A política "
                    "proposta (dump diário para armazenamento externo, com teste trimestral de "
                    "restauração) está em docs/backup.md, aguardando decisão. Pesa mais aqui do "
                    "que num sistema comum: a base guarda ficha de matrícula de menor, com "
                    "dado sensível que só existe aqui."
                ),
            ),
        ]

    # -- Integridade dos eventos externos ---------------------------------

    def _integridade_webhook(self, c: ConfiguracaoSeguranca) -> list[MedidaSeguranca]:
        # A validação existe no código; o que varia é se está ligada e com segredo.
        if not c.meta_validate_signature:
            status_assinatura = StatusMedida.ATENCAO
            detalhe = (
                "Implementada, mas DESLIGADA: META_VALIDATE_SIGNATURE=false. "
                "Ligue antes de expor o webhook em produção."
            )
        elif not c.meta_app_secret_definido:
            status_assinatura = StatusMedida.ATENCAO
            detalhe = (
                "Ligada, porém sem META_APP_SECRET: sem a chave do HMAC toda requisição "
                "é recusada e o webhook para de funcionar."
            )
        else:
            status_assinatura = StatusMedida.ATIVA
            detalhe = "Ligada, com app secret configurado."

        return [
            MedidaSeguranca(
                chave="webhook_assinatura",
                titulo="Assinatura dos webhooks (X-Hub-Signature-256)",
                categoria="Integridade de dados",
                descricao=(
                    "Todo POST recebido da Meta é validado por HMAC-SHA256 sobre o corpo "
                    "bruto, com o app secret como chave e comparação em tempo constante."
                ),
                risco=(
                    "Sem ela, qualquer um que descubra a URL pública pode forjar eventos: "
                    "marcar como 'entregue' um aviso que não chegou (desligando o alarme de "
                    "não-entrega da escola) e, com o inbound ativo, injetar conversas falsas "
                    "em nome de qualquer telefone, consumindo cota de LLM."
                ),
                status=status_assinatura,
                detalhe=detalhe,
                referencia="app/interfaces/api/webhook.py · validar_assinatura_meta()",
            ),
            MedidaSeguranca(
                chave="webhook_verify_token",
                titulo="Token de verificação do webhook",
                categoria="Integridade de dados",
                descricao=(
                    "O handshake GET da Meta só devolve o hub.challenge quando o "
                    "hub.verify_token confere com o configurado."
                ),
                risco=(
                    "Com o token default, qualquer pessoa reproduz o handshake e consegue "
                    "apontar um webhook próprio para o endpoint."
                ),
                status=(
                    StatusMedida.ATENCAO if c.meta_verify_token_padrao else StatusMedida.ATIVA
                ),
                detalhe=(
                    f"META_WEBHOOK_VERIFY_TOKEN ainda é o valor de exemplo "
                    f"('{META_VERIFY_TOKEN_PADRAO}')."
                    if c.meta_verify_token_padrao
                    else "Token próprio configurado."
                ),
                referencia="app/interfaces/api/webhook.py · verificar()",
            ),
            self._canal_efetivo(c),
            self._storage_efetivo(c),
            self._conta_whatsapp(c),
        ]

    def _canal_efetivo(self, c: ConfiguracaoSeguranca) -> MedidaSeguranca:
        """O canal pedido pela env é o que a aplicação usa de fato?

        Só é ``ATENCAO`` no caso híbrido — pediu ``meta``, subiu ``demo``. Rodar em ``demo``
        de propósito (desenvolvimento local, sem token da Meta) não é um problema de
        segurança e não pode virar alarme falso no painel.
        """
        degradado = c.canal == "meta" and not c.meta_access_token_definido
        return MedidaSeguranca(
            chave="canal_efetivo",
            titulo="Canal de mensagens efetivo",
            categoria="Integridade de dados",
            descricao=(
                "O adaptador de WhatsApp em uso é o que MESSAGE_CHANNEL pede. A fábrica só "
                "devolve o canal da Meta com MESSAGE_CHANNEL=meta e META_ACCESS_TOKEN "
                "preenchido; faltando o token ela cai no canal demo."
            ),
            risco=(
                "A queda para o demo é silenciosa e o processo sobe normal. O inbound segue "
                "sendo roteado, chamando a LLM (custo real) e marcado como concluído, mas a "
                "resposta some — o responsável escreve para a escola e nunca é respondido, "
                "sem erro em lugar nenhum. No outbound o demo devolve um id 'demo-N' que "
                "jamais casa com um wamid, então todo destinatário fica preso em ENVIADO e a "
                "não-entrega reativa passa a acusar a escola inteira."
            ),
            status=StatusMedida.ATENCAO if degradado else StatusMedida.ATIVA,
            detalhe=(
                "MESSAGE_CHANNEL=meta, mas META_ACCESS_TOKEN está vazio: a aplicação está no "
                "canal demo e NADA chega ao WhatsApp. Gere o token de usuário do sistema "
                "(docs/producao-whatsapp.md §4)."
                if degradado
                else f"Canal '{c.canal}' ativo, coerente com a configuração."
            ),
            referencia="app/infrastructure/factories.py · canal_efetivo()",
        )

    def _storage_efetivo(self, c: ConfiguracaoSeguranca) -> MedidaSeguranca:
        """Os arquivos estão onde ARQUIVO_STORAGE diz que estão?

        Mesmo critério do canal: só é ``ATENCAO`` no caso híbrido — pediu ``s3``, ficou no
        Postgres. Rodar em ``postgres`` de propósito (desenvolvimento, ou produção antes de
        o bucket existir) não é problema de segurança e não pode virar alarme falso.

        A região entra junto porque é o mesmo objeto de auditoria: bucket fora do Brasil
        transforma o armazenamento em transferência internacional.
        """
        degradado = c.arquivo_storage == "s3" and c.arquivo_storage_efetivo != "s3"
        fora_do_brasil = c.arquivo_storage_efetivo == "s3" and not c.aws_region.startswith(
            "sa-east"
        )
        return MedidaSeguranca(
            chave="storage_efetivo",
            titulo="Armazenamento efetivo dos arquivos",
            categoria="Integridade de dados",
            descricao=(
                "Os bytes dos documentos que os pais enviam estão no adaptador que "
                "ARQUIVO_STORAGE pede. A fábrica só devolve o S3 com ARQUIVO_STORAGE=s3 e "
                "S3_BUCKET_DOCUMENTOS preenchido; sem o bucket, cai no Postgres."
            ),
            risco=(
                "A queda para o Postgres é silenciosa. O upload responde sucesso, o painel "
                "mostra o documento e o download funciona — só que atestado e laudo de "
                "menor estão engordando um banco cobrado por GB, sem lifecycle, sem KMS e "
                "sem a rede de segurança do prazo de retenção que o bucket daria. E com o "
                "bucket fora do Brasil, guardar dado de saúde de criança vira transferência "
                "internacional (LGPD arts. 33-36), que exige base legal declarada."
            ),
            status=(
                StatusMedida.ATENCAO if (degradado or fora_do_brasil) else StatusMedida.ATIVA
            ),
            detalhe=(
                "ARQUIVO_STORAGE=s3, mas S3_BUCKET_DOCUMENTOS está vazio: os arquivos estão "
                "indo para o bytea do Postgres."
                if degradado
                else (
                    f"Bucket na região '{c.aws_region}', fora do Brasil: declare a base legal "
                    "da transferência internacional na política de privacidade."
                    if fora_do_brasil
                    else f"Armazenamento '{c.arquivo_storage_efetivo}' ativo, coerente com a "
                    "configuração."
                )
            ),
            referencia="app/infrastructure/factories.py · storage_efetivo()",
        )

    def _conta_whatsapp(self, c: ConfiguracaoSeguranca) -> MedidaSeguranca:
        """Toda escola está vinculada a uma conta do WhatsApp Business?

        A escola sem conta dispara pelo número dela, mas **não por template** — e template
        é o que sai fora da janela de 24h, ou seja, todo aviso ativo. A tela de escolas
        marca isso com ⚠; aqui entra porque é auditoria, e o modo de falha é o mesmo que
        `canal_efetivo` existe para acusar: o produto parece configurado e não está.
        """
        pendentes = c.escolas_sem_conta_whatsapp
        return MedidaSeguranca(
            chave="conta_whatsapp_por_escola",
            titulo="Escola vinculada a uma conta do WhatsApp (WABA)",
            categoria="Integridade de dados",
            descricao=(
                "Cada escola declara em qual conta do WhatsApp Business o número dela "
                "está. É a conta que responde pelo catálogo de templates: é onde o "
                "template dela é criado e onde a aprovação é conferida antes de um "
                "disparo."
            ),
            risco=(
                "Sem conta vinculada, o disparo por template é recusado — e template é o "
                "que sai fora da janela de 24h, ou seja, todo aviso ativo. Com a conta "
                "errada é pior: o painel mostra 'aprovado' de um template que não existe "
                "naquela conta, e a Graph API recusa destinatário a destinatário, depois "
                "de a cota do dia ter sido consumida."
            ),
            status=StatusMedida.ATENCAO if pendentes else StatusMedida.ATIVA,
            detalhe=(
                f"{pendentes} escola(s) ativa(s) sem conta vinculada — o disparo por "
                "template delas é recusado. Defina a conta no cadastro da escola."
                if pendentes
                else "Todas as escolas ativas estão vinculadas a uma conta."
            ),
            referencia="app/application/templates_use_cases.py · CriarTemplate._contas_alvo()",
        )

    # -- Autenticação e sessão --------------------------------------------

    def _autenticacao(self, c: ConfiguracaoSeguranca) -> list[MedidaSeguranca]:
        return [
            MedidaSeguranca(
                chave="senha_pbkdf2",
                titulo="Senhas com PBKDF2-SHA256",
                categoria="Autenticação",
                descricao=(
                    "Senhas de administradores e professores são guardadas como hash "
                    "PBKDF2-SHA256 com salt por usuário e 200.000 iterações — nunca em "
                    "texto puro nem reversíveis."
                ),
                risco=(
                    "Um vazamento do banco entregaria as senhas em claro, e como as pessoas "
                    "reusam senha, daria acesso a outras contas delas."
                ),
                status=StatusMedida.ATIVA,
                detalhe="200.000 iterações, salt aleatório por senha (somente stdlib).",
                referencia="app/infrastructure/security.py · hash_senha()",
            ),
            MedidaSeguranca(
                chave="jwt_sessao",
                titulo="Sessão por JWT com revalidação no banco",
                categoria="Autenticação",
                descricao=(
                    "O painel guarda um JWT (HS256), não a senha. Cada requisição decodifica "
                    "o token E reconsulta o usuário no banco, conferindo existência e flag "
                    "'ativo' — desativar alguém encerra a sessão na hora, sem esperar o token "
                    "expirar."
                ),
                risco=(
                    "Sem a revalidação, um funcionário desligado continuaria entrando até o "
                    "token vencer. Com segredo default, qualquer um forja um token de super "
                    "admin e acessa todas as escolas."
                ),
                status=(StatusMedida.ATENCAO if c.jwt_secret_padrao else StatusMedida.ATIVA),
                detalhe=(
                    "JWT_SECRET ainda é o valor de exemplo do .env.example — trocar é "
                    "obrigatório em produção."
                    if c.jwt_secret_padrao
                    else f"Segredo próprio; sessão expira em {c.jwt_expira_minutos} min."
                ),
                referencia="app/interfaces/api/admin.py · usuario_autenticado()",
            ),
            MedidaSeguranca(
                chave="papeis",
                titulo="Separação de papéis (super admin / escola / professor)",
                categoria="Autenticação",
                descricao=(
                    "Três papéis com guardas distintos: super admin (cross-tenant), admin da "
                    "escola (preso ao próprio tenant) e professor (portal separado, com login "
                    "próprio). Só o super admin cria outro super admin."
                ),
                risco=(
                    "Sem a separação, o admin de uma escola poderia criar usuários com alcance "
                    "sobre todas as outras."
                ),
                status=StatusMedida.ATIVA,
                detalhe="Guardas _exige_super_admin e _exige_acesso_tenant nas rotas.",
                referencia="app/interfaces/api/admin.py",
            ),
        ]

    # -- Isolamento entre escolas ------------------------------------------

    def _isolamento(self) -> list[MedidaSeguranca]:
        return [
            MedidaSeguranca(
                chave="multi_tenant",
                titulo="Isolamento multi-tenant por escola",
                categoria="Isolamento",
                descricao=(
                    "Toda consulta é escopada por tenant_id, e o acesso a qualquer recurso de "
                    "uma escola passa pelo guarda _exige_acesso_tenant, que devolve 403 fora "
                    "do tenant do usuário."
                ),
                risco=(
                    "Uma escola veria conversas, alunos e contatos de outra — vazamento de "
                    "dados de menores entre clientes concorrentes."
                ),
                status=StatusMedida.ATIVA,
                detalhe="Escopo por tenant_id em todas as tabelas e repositórios.",
                referencia="CLAUDE.md §6 · _exige_acesso_tenant()",
            ),
            MedidaSeguranca(
                chave="suspensao_tenant",
                titulo="Suspensão de acesso da escola",
                categoria="Isolamento",
                descricao=(
                    "Escola bloqueada ou cancelada perde o login do painel (403 com motivo) e "
                    "os disparos, sem que os dados sejam apagados."
                ),
                risco=(
                    "Uma escola inadimplente ou desligada seguiria disparando mensagens no "
                    "nosso número e consumindo cota."
                ),
                status=StatusMedida.ATIVA,
                detalhe="Guarda _exige_tenant_ativo nos disparos; login recusa suspensa.",
                referencia="CLAUDE.md §6e",
            ),
        ]

    # -- Rastreabilidade ---------------------------------------------------

    def _rastreabilidade(self, c: ConfiguracaoSeguranca) -> list[MedidaSeguranca]:
        return [
            MedidaSeguranca(
                chave="observabilidade",
                titulo="Log operacional persistido e consultável",
                categoria="Rastreabilidade",
                descricao=(
                    "Toda requisição recebe um id de correlação, e os logs (com traceback) são gravados no Postgres e consultáveis em /admin/logs. Distinto da auditoria: aquela registra decisões de negócio, este registra o que o processo fez."
                ),
                risco=(
                    "Sem log persistido, uma falha em produção só existe enquanto alguém estiver com o painel do Render aberto — e o erro que o usuário relata na segunda-feira já não pode ser localizado."
                ),
                status=(
                    StatusMedida.ATIVA if c.logs_persistidos else StatusMedida.ATENCAO
                ),
                detalhe=(
                    f"Retenção de {c.logs_retencao_dias} dias; a gravação é assíncrona (fila em memória drenada em lote), de modo a não somar latência à resposta."
                    if c.logs_persistidos
                    else (
                        "LOG_PERSISTIR=false: os logs só vão para o stdout do provedor, que é volátil."
                    )
                ),
                referencia="CLAUDE.md §16 · app/infrastructure/logs.py",
            ),
            MedidaSeguranca(
                chave="retencao_documentos",
                titulo="Prazo de retenção dos documentos recebidos dos pais",
                categoria="Rastreabilidade",
                descricao=(
                    "Todo arquivo que um responsável envia pelo WhatsApp (§6k) nasce com data de expurgo, e a rotina apaga os bytes e o metadado quando o prazo vence."
                ),
                risco=(
                    "É o dado mais sensível da base: atestado médico é dado de saúde de criança (LGPD arts. 11 e 14). Sem prazo, o repositório vira passivo permanente — e um vazamento futuro alcança documento que a escola nem precisava mais ter."
                ),
                status=(
                    StatusMedida.ATIVA
                    if c.documento_retencao_dias > 0
                    else StatusMedida.ATENCAO
                ),
                detalhe=(
                    f"DOCUMENTO_RETENCAO_DIAS={c.documento_retencao_dias}: cada arquivo recebe expira_em no momento em que chega. O expurgo ainda depende de alguém acionar POST /api/admin/documentos/expurgar — falta o job agendado."
                    if c.documento_retencao_dias > 0
                    else (
                        "DOCUMENTO_RETENCAO_DIAS=0: os arquivos enviados pelos responsáveis ficam guardados indefinidamente."
                    )
                ),
                referencia="CLAUDE.md §6k · app/application/documentos_use_cases.py",
            ),
            MedidaSeguranca(
                chave="auditoria",
                titulo="Log de auditoria de ações",
                categoria="Rastreabilidade",
                descricao=(
                    "Ações de usuários logados (login, criação de usuário/grupo, disparos) e "
                    "da própria LLM (cada atendimento) ficam registradas com ator, ação, "
                    "descrição, metadados e data."
                ),
                risco=(
                    "Sem o log não há como responder 'quem disparou isso' depois de um "
                    "incidente — nem para a escola, nem numa eventual demanda judicial."
                ),
                status=StatusMedida.ATIVA,
                detalhe="Auditar é tolerante a falhas: nunca derruba a ação auditada.",
                referencia="CLAUDE.md §13 · app/application/auditoria_use_cases.py",
            ),
            MedidaSeguranca(
                chave="exportacao_legal",
                titulo="Exportação de conversa para fins legais",
                categoria="Rastreabilidade",
                descricao=(
                    "Uma conversa pode ser exportada como documento textual com cabeçalho "
                    "institucional e marca de exportação, para anexar a processo ou prontuário."
                ),
                risco=(
                    "Sem isso, atender a uma requisição judicial sobre uma conversa vira "
                    "trabalho manual e sujeito a erro."
                ),
                status=StatusMedida.ATIVA,
                detalhe="Recorte opcional por período.",
                referencia="CLAUDE.md §6i · app/interfaces/api/exportacao.py",
            ),
        ]

    # -- Exposição da aplicação --------------------------------------------

    def _exposicao(self, c: ConfiguracaoSeguranca) -> list[MedidaSeguranca]:
        return [
            MedidaSeguranca(
                chave="cors",
                titulo="CORS restrito a origens conhecidas",
                categoria="Exposição",
                descricao=(
                    "A API só aceita chamadas de navegador vindas das origens declaradas em "
                    "BACKEND_CORS_ORIGINS (o painel na Vercel e o ambiente local)."
                ),
                risco=(
                    "Com CORS liberado, uma página maliciosa aberta pelo admin poderia chamar "
                    "a API usando a sessão dele."
                ),
                status=(StatusMedida.ATENCAO if c.cors_liberado else StatusMedida.ATIVA),
                detalhe=(
                    "BACKEND_CORS_ORIGINS está com '*' — qualquer origem é aceita."
                    if c.cors_liberado
                    else "Lista explícita de origens."
                ),
                referencia="app/main.py · CORSMiddleware",
            ),
            MedidaSeguranca(
                chave="segredos_env",
                titulo="Segredos fora do código",
                categoria="Exposição",
                descricao=(
                    "Chaves de LLM, token da Meta, app secret e segredo do JWT vivem só em "
                    "variáveis de ambiente do Render — nunca no repositório."
                ),
                risco=(
                    "Segredo commitado é segredo vazado: o histórico do Git é público para "
                    "quem tiver acesso ao repo e não se apaga com um novo commit."
                ),
                status=StatusMedida.ATIVA,
                detalhe="O .env.example traz apenas placeholders.",
                referencia="CLAUDE.md §11",
            ),
            MedidaSeguranca(
                chave="ambiente",
                titulo="Ambiente declarado como produção",
                categoria="Exposição",
                descricao=(
                    "APP_ENV identifica o ambiente em execução. Em produção ele deve valer "
                    "'production', que é a chave para tratar defaults de desenvolvimento como "
                    "erro em vez de conveniência."
                ),
                risco=(
                    "Um ambiente rodando como desenvolvimento tende a carregar credenciais de "
                    "seed e defaults permissivos sem que ninguém perceba."
                ),
                status=(
                    StatusMedida.ATIVA if c.app_env == "production" else StatusMedida.ATENCAO
                ),
                detalhe=f"APP_ENV={c.app_env or '(vazio)'}.",
                referencia="app/config.py",
            ),
            MedidaSeguranca(
                chave="rate_limit_inbound",
                titulo="Limite de taxa por remetente no inbound",
                categoria="Exposição",
                descricao=(
                    "Limita quantas mensagens um mesmo telefone pode disparar por janela no "
                    "webhook. A checagem roda depois da idempotência e antes da LLM, então a "
                    "mensagem excedente não chega a custar uma chamada ao provedor."
                ),
                risco=(
                    "Um único número em loop pode consumir a cota de LLM da escola e gerar "
                    "custo desproporcional."
                ),
                status=(
                    StatusMedida.ATIVA
                    if c.rate_limit_habilitado and c.rate_limit_inbound_mensagens > 0
                    else StatusMedida.ATENCAO
                ),
                detalhe=(
                    f"{c.rate_limit_inbound_mensagens} mensagens por remetente por janela; "
                    "a excedente é descartada e o webhook segue devolvendo 200 à Meta."
                    if c.rate_limit_habilitado and c.rate_limit_inbound_mensagens > 0
                    else (
                        "Desligado: sobra apenas MENSAGEM_PAI_MAX_CHARS, que corta mensagem "
                        "longa mas não limita quantas chegam."
                    )
                ),
                referencia="app/application/inbound_use_cases.py",
            ),
            MedidaSeguranca(
                chave="rate_limit_login",
                titulo="Limite de tentativas de login",
                categoria="Autenticação",
                descricao=(
                    "Conta as tentativas por IP e por identificador (e-mail do admin, "
                    "telefone do professor) numa janela fixa e recusa o excedente com 429. "
                    "As duas chaves juntas cobrem o ataque distribuído (que passaria pelo "
                    "contador de IP) sem permitir trancar a conta alheia só por saber o "
                    "e-mail."
                ),
                risco=(
                    "Sem limite, o brute force contra a senha de um administrador é livre: o "
                    "PBKDF2 encarece cada tentativa, mas não limita quantas são feitas."
                ),
                status=(
                    StatusMedida.ATIVA
                    if c.rate_limit_habilitado and c.rate_limit_login_tentativas > 0
                    else StatusMedida.ATENCAO
                ),
                detalhe=(
                    f"{c.rate_limit_login_tentativas} tentativas por janela, por IP e por "
                    "identificador. Contador no Postgres (controle_taxa), compartilhado "
                    "entre réplicas."
                    if c.rate_limit_habilitado and c.rate_limit_login_tentativas > 0
                    else "Desligado por configuração."
                ),
                referencia="app/interfaces/api/rate_limit.py",
            ),
            MedidaSeguranca(
                chave="seed_producao",
                titulo="Seed de demonstração fora de produção",
                categoria="Exposição",
                descricao=(
                    "O seed cria escola fictícia, alunos e logins com senha de exemplo. Ele é "
                    "bloqueado quando APP_ENV=production e, fora de desenvolvimento, exige "
                    "que as senhas tenham valor próprio."
                ),
                risco=(
                    "Rodando em produção, o seed insere no banco da escola real dados falsos "
                    "indistinguíveis dos verdadeiros e um login cuja senha está versionada "
                    "no repositório."
                ),
                status=(
                    StatusMedida.ATENCAO
                    if c.seed_demo_habilitado and c.app_env == "production"
                    else StatusMedida.ATIVA
                ),
                detalhe=(
                    f"SEED_DEMO={'ligado' if c.seed_demo_habilitado else 'desligado'}; "
                    f"APP_ENV={c.app_env or '(vazio)'}. O provisionamento de produção é o "
                    "`app.bootstrap`, que cria apenas o super admin."
                ),
                referencia="app/bootstrap.py",
            ),
        ]
