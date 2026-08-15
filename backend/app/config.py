"""Configuração da aplicação (carregada de variáveis de ambiente)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://tiescolar:tiescolar@db:5432/tiescolar"

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalizar_dsn(cls, valor: str) -> str:
        """Aceita o DSN cru do Render/Heroku (``postgres://``/``postgresql://``) e força
        o driver psycopg v3 (async) exigido pelo SQLAlchemy desta aplicação."""
        if not isinstance(valor, str):
            return valor
        if valor.startswith("postgres://"):
            valor = "postgresql://" + valor[len("postgres://") :]
        if valor.startswith("postgresql://"):
            valor = "postgresql+psycopg://" + valor[len("postgresql://") :]
        return valor
    backend_cors_origins: str = "http://localhost:3000"

    # LLM — "fake" | "anthropic" | "openai" | "openai_compatible"
    llm_provider: str = "fake"
    llm_model: str = "claude-opus-4-8"
    llm_base_url: str = "https://api.openai.com/v1"  # usado por openai/openai_compatible
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Embeddings — "fake" | "openai" | "openai_compatible"
    embedding_dim: int = 1536  # dimensão da coluna pgvector (text-embedding-3-small = 1536)
    embeddings_provider: str = "fake"
    embeddings_base_url: str = "https://api.openai.com/v1"
    embeddings_api_key: str | None = None
    embeddings_model: str = "text-embedding-3-small"

    # Canal
    message_channel: str = "demo"

    # Seed de demonstração (escola fictícia, alunos, senhas de exemplo).
    # Default DESLIGADO: o seed nunca deve rodar contra o banco de uma escola real.
    # Ver a política completa em `app/bootstrap.py::avaliar_seed`.
    seed_demo: bool = False

    # Super admin (criado no bootstrap, em qualquer ambiente)
    super_admin_email: str = "admin@tiescolar.test"
    super_admin_senha: str = "troque-esta-senha"
    super_admin_nome: str = "Super Admin"

    # Admin do tenant demo (criado no seed)
    demo_admin_email: str = "admin@escola-demo.test"
    demo_admin_senha: str = "escola123"
    # Senha do professor demo (login do mural do professor — §A1)
    demo_professor_senha: str = "prof123"

    # Observabilidade / logs (§16, item 8 do checklist).
    log_nivel: str = "INFO"
    # Log de console em JSON (útil se algum dia houver um coletor externo lendo o stdout).
    log_json: bool = False
    # Persistir os logs no Postgres para o painel /admin/logs. Desligue se o volume
    # crescer além do que o plano do banco comporta.
    log_persistir: bool = True
    log_nivel_persistido: str = "INFO"
    # Teto da fila em memória: cheia, descarta o mais antigo em vez de bloquear a resposta.
    log_fila_capacidade: int = 2000
    log_retencao_dias: int = 14

    # Limite de taxa de entrada (item 5 do checklist de pré-deploy).
    # Estado compartilhado no Postgres (tabela controle_taxa), para valer entre réplicas.
    rate_limit_habilitado: bool = True
    # Login: tentativas por janela, contadas por IP e por e-mail.
    rate_limit_login_tentativas: int = 10
    rate_limit_login_janela_segundos: int = 300
    # Inbound do webhook: mensagens por janela, por telefone remetente.
    rate_limit_inbound_mensagens: int = 20
    rate_limit_inbound_janela_segundos: int = 60
    # Confiar no X-Forwarded-For para descobrir o IP do cliente. Ligado porque o Render
    # põe um proxy na frente; desligue se a aplicação for exposta direto (o cabeçalho é
    # enviado pelo cliente e, sem proxy reescrevendo, é forjável).
    trust_proxy_headers: bool = True

    # Autenticação (JWT) — segredo de assinatura HS256 e validade do token (minutos).
    # Em produção, defina JWT_SECRET com um valor forte e secreto.
    jwt_secret: str = "troque-este-segredo-jwt"
    jwt_expira_minutos: int = 480  # 8 horas

    # Inbound / UX das mensagens dos pais (§G1)
    # Limite de caracteres da mensagem do responsável; acima disso o bot pede objetividade
    # sem acionar a LLM. 0 desativa o limite.
    mensagem_pai_max_chars: int = 1000

    # Sessão de conversa (§13). Uma conversa parada por mais que isto é encerrada, e a
    # próxima mensagem do responsável abre outra. 24h alinha com a janela da Meta, que é o
    # relógio que ele percebe. **0 desliga o recorte** e devolve a conversa eterna de
    # antes — existe como válvula, não como caminho recomendado: sem ela o contexto
    # enviado à LLM cresce sem limite.
    conversa_janela_horas: int = 24

    # Documentos recebidos dos responsáveis (§6k)
    # Retenção dos arquivos enviados pelos pais. É dado sensível de menor (atestado é dado
    # de saúde), então o prazo é obrigatório: um ano cobre o ciclo letivo inteiro sem
    # transformar o repositório num passivo permanente. 0 desativa o expurgo.
    documento_retencao_dias: int = 365

    # Atendimento humano (§6j)
    # Nome do template usado para reabrir uma conversa cuja janela de 24h expirou (a
    # secretaria só viu o recado no dia seguinte).
    #
    # **O default deixou de ser vazio em 12/ago/2026.** O vazio existia como trava: sem
    # catálogo, nada no sistema sabia se o template estava aprovado na Meta, e disparar
    # contra um template inexistente morre na Graph API — a secretaria acreditaria ter
    # respondido alguém que nunca recebeu nada. Quem segurava isso era esta env, que
    # precisava ser preenchida à mão no Render, escola por deploy.
    #
    # Com o catálogo (§9a-bis) a trava mudou de lugar e ficou melhor: quem responde "dá
    # para enviar?" é o **status do template**, que vem da própria Meta pelo webhook ou
    # pela sincronização. `_template_de_retomada` já exige `StatusTemplate.APROVADO`, então
    # o modo de falha seguro está garantido sem depender de alguém lembrar de uma variável
    # de ambiente. Preencher continua possível — serve para apontar outro nome ou para
    # desligar a retomada (valor vazio).
    template_retomada_atendimento: str = "retomada_atendimento"

    # Retomada de disparos travados pela cota diária (§9a-quinquies). O teto da Meta é de
    # destinatários únicos por 24h, então uma escola grande não cabe num dia — e sem esta
    # tarefa "espera a próxima janela" significa alguém lembrar de re-disparar à mão.
    broadcast_retomada_habilitada: bool = True
    broadcast_retomada_intervalo_segundos: int = 1800
    # Prazo de validade do disparo, não otimização: aviso de três semanas atrás entregue
    # hoje é pior que não entregue — a reunião já passou.
    broadcast_retomada_janela_dias: int = 7

    # Licenciamento / avisos por e-mail
    # Janela (em dias) para avisar que a licença anual está perto de vencer.
    license_warning_days: int = 30
    # Remetente dos e-mails administrativos (adaptador atual é mock/log).
    email_from: str = "no-reply@tiescolar.test"
    # Provedor de e-mail: "log" (mock, só registra) | "resend" (envio real via API HTTP).
    email_provider: str = "log"
    # Chave da API do resend.com. Vazia = cai no adaptador de log.
    resend_api_key: str | None = None

    # Meta WhatsApp Cloud API
    # Número remetente PADRÃO (fallback): usado quando a escola não tem o seu próprio
    # phone_number_id cadastrado. Em produção multi-tenant cada escola tem o seu — ver §9e.
    meta_phone_number_id: str | None = None
    # **Não existe `META_WABA_ID`.** A conta do WhatsApp Business mora no banco (`Waba`),
    # cadastrada no painel e escolhida por escola: uma env não comporta a segunda conta, e
    # o teto de números do portfólio garante que ela vai existir (§9e.3). O id chega
    # sozinho pelo webhook — ver `AdotarContaDoWebhook` —, ou é digitado em
    # Administração → Contas WhatsApp.
    # Token de USUÁRIO DO SISTEMA (o token da tela de Configuração da API expira em 24h).
    meta_access_token: str | None = None
    # Token do handshake GET do webhook (hub.verify_token). TROQUE em produção.
    meta_webhook_verify_token: str = "changeme"
    # Destinatários **únicos por 24h** que podemos iniciar conversa. Medido pela Meta **no
    # portfólio** e compartilhado por todos os números dele (mudança de out/2025), não por
    # número como esta linha assumia quando dizia 1000.
    #
    # **250 é o teto real de um portfólio novo** — conferido em 14/ago/2026 no Gerenciador
    # do WhatsApp ("0 de 250 enviados") e pela API (`messaging_limit_tier: TIER_250`).
    # Configurar acima do real é pior que inútil: o disparo manda até o teto da Meta e o
    # excedente vira **falha**, que conta contra a qualidade do número — justamente o que
    # precisa estar alto para o limite subir. Com o valor certo, o excedente fica marcado
    # como bloqueado pela cota e espera a próxima janela, sem queimar reputação.
    #
    # Sobe sozinho (verificação da empresa → 2.000; depois, um nível a cada 6h com
    # qualidade alta e metade do limite usada em 7 dias). **Ao subir, ajuste aqui.**
    meta_daily_tier_limit: int = 250
    # App secret usado para validar a assinatura X-Hub-Signature-256 dos webhooks.
    meta_app_secret: str | None = None
    # Valida a assinatura dos webhooks da Meta. OBRIGATÓRIO em produção: sem isso o
    # endpoint aceita qualquer POST, permitindo forjar status de entrega e mensagens.
    meta_validate_signature: bool = False

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]

    @property
    def ambiente_producao(self) -> bool:
        """Ambiente de produção — aceita as grafias usadas pelos provedores de deploy."""
        return self.app_env.strip().lower() in {"production", "producao", "prod"}

    @property
    def ambiente_desenvolvimento(self) -> bool:
        """Máquina do dev / docker-compose local, onde o banco é descartável."""
        return self.app_env.strip().lower() in {"development", "desenvolvimento", "dev", "local"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
