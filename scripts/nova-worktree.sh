#!/usr/bin/env bash
#
# nova-worktree.sh — cria um git worktree ISOLADO para rodar uma sessão do Claude
# (ou um dev) em paralelo, sem colidir com as outras worktrees.
#
# O que isola:
#   - branch própria, criada a partir de origin/main atualizada;
#   - docker-compose com COMPOSE_PROJECT_NAME próprio  -> containers, rede e
#     VOLUME do Postgres separados (cada worktree tem o SEU banco);
#   - portas de host próprias (DB / backend / web), escolhidas automaticamente
#     para não colidir com worktrees já existentes nem com portas em uso;
#   - NEXT_PUBLIC_API_URL e BACKEND_CORS_ORIGINS ajustados às novas portas.
#
# Uso:
#   scripts/nova-worktree.sh <feat|fix>/<nome-da-branch> [diretorio-destino]
#
# Exemplos:
#   scripts/nova-worktree.sh feat/assinaturas
#   scripts/nova-worktree.sh fix/webhook-status ../ti-escolar-webhook
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Portas-base (espelham os defaults do docker-compose.yml). O offset N é somado
# a todas elas: DB=5433+N, BACKEND=8000+N, WEB=3000+N.
# ---------------------------------------------------------------------------
BASE_DB=5433
BASE_BACKEND=8000
BASE_WEB=3000

die() { printf '\033[31merro:\033[0m %s\n' "$*" >&2; exit 1; }
info() { printf '\033[36m›\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }

[ $# -ge 1 ] || die "informe a branch. Uso: $0 <feat|fix>/<nome> [destino]"

BRANCH="$1"
case "$BRANCH" in
  feat/*|fix/*) ;;
  *) die "a branch deve começar com 'feat/' ou 'fix/' (convenção do projeto). Recebi: '$BRANCH'" ;;
esac

# Raiz do repositório atual (funciona de qualquer subpasta).
REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)" \
  || die "não estou dentro de um repositório git."
cd "$REPO_ROOT"

# slug seguro para nome de pasta e de projeto docker (só [a-z0-9_-]).
SLUG="$(printf '%s' "${BRANCH#*/}" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-' | sed 's/-\+/-/g; s/^-//; s/-$//')"
DEST="${2:-../ti-escolar-$SLUG}"
PROJECT="tiescolar-$SLUG"

[ -e "$DEST" ] && die "o destino '$DEST' já existe."
git show-ref --verify --quiet "refs/heads/$BRANCH" && die "a branch '$BRANCH' já existe."

# ---------------------------------------------------------------------------
# Escolha do offset de portas: a primeira faixa cujas 3 portas estejam livres
# (nem ocupadas no host, nem reservadas no .env de outra worktree).
# ---------------------------------------------------------------------------
porta_em_uso() {
  local p="$1"
  # conexão TCP bem-sucedida = alguém escutando = porta ocupada.
  (exec 3<>"/dev/tcp/127.0.0.1/$p") 2>/dev/null && { exec 3>&- 3<&-; return 0; }
  return 1
}

# Portas já reservadas nos .env das worktrees existentes (mesmo que paradas).
reservadas() {
  local path envf
  while read -r _ path; do
    envf="$path/.env"
    [ -f "$envf" ] && grep -hE '^(DB_PORT|BACKEND_PORT|WEB_PORT)=' "$envf" 2>/dev/null | cut -d= -f2
  done < <(git worktree list --porcelain | grep '^worktree ')
}

mapfile -t RESERVADAS < <(reservadas)
esta_reservada() { local p="$1"; printf '%s\n' "${RESERVADAS[@]:-}" | grep -qx "$p"; }

OFFSET=""
for n in $(seq 1 50); do
  db=$((BASE_DB + n)); be=$((BASE_BACKEND + n)); we=$((BASE_WEB + n))
  if ! esta_reservada "$db" && ! esta_reservada "$be" && ! esta_reservada "$we" \
     && ! porta_em_uso "$db" && ! porta_em_uso "$be" && ! porta_em_uso "$we"; then
    OFFSET="$n"; break
  fi
done
[ -n "$OFFSET" ] || die "não achei uma faixa de portas livre (offsets 1..50)."

DB_PORT=$((BASE_DB + OFFSET))
BACKEND_PORT=$((BASE_BACKEND + OFFSET))
WEB_PORT=$((BASE_WEB + OFFSET))

# ---------------------------------------------------------------------------
# Cria a worktree a partir de origin/main atualizada (sem mexer na branch atual).
# ---------------------------------------------------------------------------
info "buscando origin/main…"
git fetch --quiet origin main || die "falha no 'git fetch origin main'."

info "criando worktree '$DEST' na branch '$BRANCH' (a partir de origin/main)…"
git worktree add --quiet -b "$BRANCH" "$DEST" origin/main

DEST_ABS="$(cd "$DEST" && pwd)"

# ---------------------------------------------------------------------------
# .env isolado: parte do .env atual (ou do .env.example) e sobrescreve as
# chaves de isolamento.
# ---------------------------------------------------------------------------
ENV_DEST="$DEST_ABS/.env"
if [ -f "$REPO_ROOT/.env" ]; then
  cp "$REPO_ROOT/.env" "$ENV_DEST"
elif [ -f "$REPO_ROOT/.env.example" ]; then
  cp "$REPO_ROOT/.env.example" "$ENV_DEST"
else
  : > "$ENV_DEST"
fi

set_env() { # set_env CHAVE VALOR
  local k="$1" v="$2" tmp
  tmp="$(mktemp)"
  grep -vE "^${k}=" "$ENV_DEST" > "$tmp" 2>/dev/null || true
  printf '%s=%s\n' "$k" "$v" >> "$tmp"
  mv "$tmp" "$ENV_DEST"
}

{
  printf '\n# --- Isolamento da worktree (gerado por scripts/nova-worktree.sh) ---\n'
} >> "$ENV_DEST"
set_env COMPOSE_PROJECT_NAME "$PROJECT"
set_env DB_PORT "$DB_PORT"
set_env BACKEND_PORT "$BACKEND_PORT"
set_env WEB_PORT "$WEB_PORT"
set_env NEXT_PUBLIC_API_URL "http://localhost:$BACKEND_PORT"
set_env BACKEND_CORS_ORIGINS "http://localhost:$WEB_PORT"

ok "worktree pronta."
cat <<RESUMO

  Branch ............. $BRANCH
  Pasta .............. $DEST_ABS
  Projeto docker ..... $PROJECT   (volume do Postgres exclusivo)
  Postgres (host) .... localhost:$DB_PORT
  Backend (host) ..... http://localhost:$BACKEND_PORT
  Web (host) ......... http://localhost:$WEB_PORT

  Próximos passos:
    cd "$DEST_ABS"
    docker compose up --build        # sobe o stack isolado desta worktree
    claude                           # abre a sessão do Claude aqui

  Para remover quando terminar (de dentro do repo principal):
    docker compose -p $PROJECT down -v
    git worktree remove "$DEST_ABS"
    git branch -D $BRANCH            # se não for mais usar a branch
RESUMO
