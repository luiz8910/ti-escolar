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

from app.domain.entities import MedidaSeguranca, PosturaSeguranca, StatusMedida


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
                *self._rastreabilidade(),
                *self._exposicao(config),
            ]
        )

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
        ]

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

    def _rastreabilidade(self) -> list[MedidaSeguranca]:
        return [
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
                    "Limitar quantas mensagens um mesmo telefone pode disparar por minuto no "
                    "webhook, para conter abuso e custo de LLM."
                ),
                risco=(
                    "Um único número em loop pode consumir a cota de LLM da escola e gerar "
                    "custo desproporcional — hoje só há limite de tamanho por mensagem."
                ),
                status=StatusMedida.PENDENTE,
                detalhe=(
                    "Ainda não implementado. Existe apenas MENSAGEM_PAI_MAX_CHARS, que corta "
                    "mensagem longa sem acionar a LLM."
                ),
                referencia="CLAUDE.md §G1",
            ),
        ]
