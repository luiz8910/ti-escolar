#!/usr/bin/env bash
# Espera um ambiente publicar um commit específico e prova que ele está atendendo.
#
# Existe por causa de um sintoma que já custou caro: quando o deploy não acontece, o
# ambiente continua respondendo `200 ok` no /health — "publiquei" e "achei que publiquei"
# são indistinguíveis de fora. Foi assim que o Render ficou atrás da `main` por dias, com
# `/health/pronto` respondendo 404 em produção (09/ago/2026). Por isso a esteira não
# pergunta "está no ar?", e sim "**qual commit** está no ar?": o /health ecoa o commit da
# imagem (`versao`, ver app/main.py) e este script espera até que ele seja o esperado.
#
# Uso:
#   scripts/aguarda_deploy.sh <base_url> <sha_esperado> [tentativas] [intervalo_s]
#
# Códigos de saída:
#   0 — o commit esperado está no ar.
#   1 — o ambiente não respondeu, ou respondeu com OUTRO commit até o fim da espera
#       (deploy não aconteceu, falhou, ou publicou coisa diferente).
#   2 — o ambiente responde mas não sabe dizer a versão (imagem antiga, anterior a este
#       mecanismo, ou construída sem o build-arg). Quem chama decide se avisa ou reprova.
set -uo pipefail

base="${1:?informe a URL raiz da API}"
esperado="${2:?informe o commit esperado}"
tentativas="${3:-60}"
intervalo="${4:-15}"

base="${base%/}"
ultima="(sem resposta)"

echo "Esperando ${base}/health publicar ${esperado:0:12} (até $((tentativas * intervalo))s)…"

for i in $(seq 1 "$tentativas"); do
  corpo=$(curl -fsS --max-time 10 "$base/health" 2>/dev/null) || corpo=""
  if [ -n "$corpo" ]; then
    ultima=$(printf '%s' "$corpo" | jq -r '.versao // "ausente"')
    if [ "$ultima" = "$esperado" ]; then
      echo "✅ ${esperado:0:12} no ar (tentativa $i)."
      printf '%s\n' "$corpo" | jq .
      exit 0
    fi
  fi
  echo "  tentativa $i/$tentativas — no ar: $ultima"
  sleep "$intervalo"
done

if [ "$ultima" = "desconhecida" ] || [ "$ultima" = "ausente" ]; then
  echo "::warning::O ambiente responde mas não informa a versão ('${ultima}'). Não dá"
  echo "::warning::para provar qual commit está atendendo — confira o deploy à mão."
  exit 2
fi

if [ "$ultima" = "(sem resposta)" ]; then
  echo "::error::${base}/health não respondeu em $((tentativas * intervalo))s. O ambiente"
  echo "::error::está fora do ar, ou o deploy derrubou o processo — veja o log do provedor."
  exit 1
fi

echo "::error::Depois de $((tentativas * intervalo))s o ambiente ainda serve '${ultima:0:12}'"
echo "::error::em vez de '${esperado:0:12}'. O deploy não chegou — veja o log do provedor."
exit 1
