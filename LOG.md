# LOG — registro de sessões

> O §0.4 ([`docs/guia/metodo-de-trabalho.md`](docs/guia/metodo-de-trabalho.md)) manda fechar
> toda sessão aqui. Este arquivo é curto de propósito: **quatro linhas por sessão**, mais
> recente no topo. Ele não substitui o roadmap (§12a, *o que* falta) nem as pendências
> externas (*o que depende do Luiz*) — ele responde uma pergunta só: **o fluxo andou?**
>
> Formato de cada entrada:
>
> ```
> ## AAAA-MM-DD — <fluxo da sessão>
> - **Andou?** sim | não
> - **Rótulo** (só quando não andou): escopo · infra · refactor · decisão · dependência · polimento · documentação
> - **Próxima ação:** <a primeira coisa da próxima sessão>
> - **Precisa de deploy?** não | homolog | produção — e se foi feito
> ```
>
> **Três vezes o mesmo rótulo = pare e traga o padrão** (§0.5). Uma ocorrência é ruído.

---

## 2026-09-06 — a esteira de deploy saiu da máquina

- **Andou?** não — nenhum fluxo do beta mudou de estado; o que saiu do lugar foi o bloqueio.
- **Rótulo:** `infra`.
- **Próxima ação:** mergear o **PR #87** e cadastrar `RENDER_DEPLOY_HOOK_URL`, `FLY_API_TOKEN`,
  `HOMOLOG_BASE_URL` e `PRODUCAO_BASE_URL` — depois disso, escolher **um** fluxo do corte do
  beta e parar de mexer em documentação.
- **Precisa de deploy?** não, mas o merge do #87 muda *como* todo deploy acontece daqui em diante.
- `feat/pipelines-homolog-producao` publicada (estava parada desde 02/set) e a documentação
  desta rodada saiu para `docs/metodo-de-trabalho-e-pendencias`, fora da branch de código.

## 2026-09-05 — método, índice e o mapa das pendências externas

- **Andou?** não — nenhum fluxo do beta saiu de *não funciona* para *funciona*.
- **Rótulo:** `documentação`.
- **Próxima ação:** `git push -u origin feat/pipelines-homolog-producao` e abrir o PR; depois
  cadastrar `RENDER_DEPLOY_HOOK_URL`, `FLY_API_TOKEN`, `HOMOLOG_BASE_URL` e `PRODUCAO_BASE_URL`
  ([`docs/pendencias-externas.md`](docs/pendencias-externas.md) §1).
- **Precisa de deploy?** não.
- Entrou: `LOG.md`, `docs/pendencias-externas.md` e as linhas correspondentes no índice.
  Achado da sessão: **a esteira de deploy estava pronta desde 02/set e nunca saiu da máquina** —
  sem push, sem PR. Era isso o "travados no deploy".

## 2026-09-02 — exclusão de arquivos e prefixos por finalidade *(em andamento)*

- **Andou?** não — na branch `feat/exclusao-de-arquivos-e-prefixos`, ainda sem commit.
- **Rótulo:** — (sessão aberta, não travada).
- **Próxima ação:** rodar `pytest`, commitar e abrir o PR. Em aberto: a solicitação de
  impressão não tem `expira_em`, então para ela o lifecycle é o **mecanismo**, não a rede.
- **Precisa de deploy?** produção, quando entrar — a migration `0046_chave_impressao_120`
  alarga a coluna da fila de 64 para 120 caracteres.
