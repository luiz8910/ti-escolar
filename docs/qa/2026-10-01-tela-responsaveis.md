# QA exploratório — tela de Responsáveis (01/out/2026)

> Relatório do agente `qa-browser`, guardado para a correção ser feita em outra sessão.
> **Estado: achados 1 e 2 corrigidos** na branch `fix/telefone-nono-digito` (ver
> [Resolução](#resolução)). Os achados 3 e 4 seguem sem ação, como o relatório já previa.

## Contexto da rodada

| | |
|---|---|
| Tela | `/admin/responsaveis` (entrou no PR #100) |
| Ambiente | `docker-compose` local; painel em `http://localhost:3010` (nesta máquina a 3000 é um Grafana de outro projeto) |
| Perfil | super admin, escola em foco "Escola Demonstração" |
| Código no ar | branch `feat/agents-qa`, igual à `develop` em `fc10d93` para back-end e painel |
| Dados | só sintéticos; os dois registros criados foram removidos e a lista voltou aos 6 originais |
| Custo | cerca de 73 mil tokens, 79 chamadas |

## Achados

### 1. `[Médio]` O mesmo celular entra duas vezes, com e sem o nono dígito

**Passos**
1. Cadastrar "QA Conceição D'Ávila" com `11999990001`.
2. Editar o WhatsApp para `+55 11 9999-0002` (8 dígitos após o DDD). Salvou como `(11) 9999-0002`.
3. Cadastrar outro responsável com `5511999990002` (9 dígitos). Salvou como `(11) 99999-0002`.

**Esperado:** o anti-duplicidade tratar `9999-0002` e `99999-0002` como o mesmo número, ou
o cadastro recusar celular sem o nono dígito.

**Obtido:** os dois cadastros entraram. O anti-duplicidade só barrou o número exatamente
igual (`+5511999990002` de novo): "Já existe um responsável com este telefone neste tenant".

**Causa (conferida no código):** `normalizar_telefone` em
`backend/app/application/validacao.py` aceita 10 **ou** 11 dígitos (e 12 ou 13 com o `55`)
e devolve o E.164 como veio, sem unificar. A duplicidade é comparada pelo E.164 em
`backend/app/application/cadastro_use_cases.py` (linhas 120 e 172 para responsável).

**Risco:** responsável duplicado; disparo para um número que não existe no WhatsApp; e a
conversa do inbound não casar com o cadastro, já que o casamento é pelo E.164 que o webhook
entrega. Este último ponto é hipótese — conferir como o `from` da Meta chega para números
brasileiros antes de escolher a forma canônica.

### 2. `[Baixo]` A mensagem de duplicado diz "neste tenant"

Para a secretaria deveria ser "nesta escola". O texto está em
`backend/app/application/cadastro_use_cases.py`, em quatro pontos:

- linhas 120 e 172 — "Já existe um responsável com este telefone neste tenant."
- linhas 778 e 856 — "Já existe um professor com este telefone neste tenant."

Vale um `grep -rn "tenant\." backend/app/application` atrás de outras mensagens ao usuário
com o mesmo termo antes de fechar.

### 3. `[Baixo]` Campo de nome com lixo, não reproduzido

Ao digitar "QA Duplicado" num cadastro novo logo após um F5, o campo mostrou
"dosQA Duplicado". O mesmo fluxo foi repetido três vezes sem o problema. Pode ser artefato
da automação. Fica só o registro; não há o que corrigir sem reproduzir.

### 4. `[Baixo]` Warning de hidratação no console

"Extra attributes from the server: cz-shortcut-listen". Vem provavelmente de extensão do
navegador (ColorZilla), não do painel. Não houve erro 4xx/5xx de API no fluxo. Sem ação.

## Resolução

Decidido pelo Luiz em 01/out/2026:

| Pergunta | Decisão |
|---|---|
| Nono dígito | **Opção A** — inserir o `9` no celular de oito dígitos; fixo intocado |
| Registros já gravados sem o 9 | **Não tratar agora** — sem migration de dados |
| `from` da Meta sem o 9 no inbound | **Fora deste PR** |

O que entrou:

- **Achado 1:** `_com_nono_digito` em `backend/app/application/validacao.py`, aplicada por
  `normalizar_telefone` nos três caminhos (com `+55`, com `55` e só com o DDD). O passo 2 da
  reprodução usava `+55 11 9999-0002`, então tratar só o número sem DDI não bastaria.
- **Achado 2:** "neste tenant" e "para o tenant" viraram "nesta escola" em todas as
  mensagens de erro do back-end (aplicação, repositórios e os fakes de teste), mais
  "Acesso negado a esta escola" e a mensagem de criação de usuário.
- Testes em `test_cadastro_pais_salas.py`, `test_cadastro_professores.py` e
  `test_importacao_alunos.py`.

O que **fica em aberto**, de propósito:

- **Legado:** um responsável ou professor gravado antes desta correção sem o nono dígito
  continua assim, e o mesmo número ainda pode ser cadastrado de novo com o 9. Reabrir e
  salvar o cadastro corrige aquele registro.
- **Inbound:** `normalizar_origem` (`backend/app/application/inbound_use_cases.py`) só põe o
  `+` no `from`. A hipótese do achado 1 segue **não conferida**: falta olhar nos logs da
  produção se a Meta entrega remetente brasileiro com 12 dígitos.
- O alcance é maior que o relatório dizia: `normalizar_telefone_contato` e o número de
  WhatsApp da escola chamam `telefone_ou_erro`, que usa a mesma normalização. Um celular
  de contato digitado sem o 9 também passa a ganhá-lo.

## Decisão pendente (histórico)

Telefone fixo brasileiro tem 10 dígitos de verdade (DDD + 8), então **recusar todo número
de 10 dígitos barraria fixos legítimos**. As opções para o achado 1:

- **A — unificar só celular (recomendada):** quando o número tem 10 dígitos e o primeiro
  após o DDD é 6, 7, 8 ou 9, inserir o `9`. Fixos (2 a 5) ficam como estão.
- **B — recusar celular sem o nono dígito:** mesma detecção, mas devolve erro pedindo o
  número completo, em vez de corrigir em silêncio.
- **C — não mexer na normalização** e comparar a duplicidade por uma forma canônica à parte.

Qualquer uma delas precisa decidir o que fazer com os registros **já gravados** sem o nono
dígito: a mudança na normalização não os alcança, e uma migration de dados em produção é
ação irreversível (§0 — exige aviso antes).

`normalizar_telefone` também serve a importação em massa e o cadastro de professor; a
mudança vale para todos. `normalizar_telefone_contato`
(`backend/app/application/tenant_use_cases.py:81`) é outra função, a do telefone de contato
da escola, e não entra nesta correção.

## O que passou

- Campos obrigatórios vazios mostram "Nome e WhatsApp são obrigatórios", com o painel aberto.
- Telefone inválido (`123`) mostra erro claro, e o que foi digitado sobrevive.
- `+55` ou `55` na frente é normalizado.
- Nome com acento e apóstrofo (`Conceição D'Ávila`) é salvo e exibido corretamente.
- Duplo clique em "Cadastrar" criou um registro só.
- Depois de criar, o painel passa para "Editar responsável".
- A busca ignora acento (`conceicao` achou) e aceita telefone formatado; busca sem resultado
  mostra a mensagem de vazio.
- Os contadores das abas (Ativos, Sem aluno vinculado, Todos) atualizam ao criar e excluir.
- A exclusão pede confirmação em português e remove da lista.
- F5 com o painel aberto fecha o painel e recarrega a lista de forma consistente.

## Não testado

- Troca da escola em foco: o banco local só tem a "Escola Demonstração".
- Campos opcionais: CPF, data dd/mm/aaaa, e-mail, telefone de trabalho e telefone 2.
- Vincular aluno no painel lateral.
- Aba "Inativos" com dados; reativar e inativar.
- Estados de carregando e de erro de rede.
- Layout no celular.
- Permissão por outro perfil (admin da escola, secretaria, professor).
- Qualquer ação que envie WhatsApp: o simulador (`/api/dev/whatsapp`) respondia 404, porque
  o back-end local estava numa branch sem o PR #101.

## Testes a escrever junto da correção

Em `backend/tests/` (o arquivo de cadastro de responsáveis é `test_cadastro_pais_salas.py`;
conferir se já há um de validação de telefone antes de criar outro):

- `11999990002`, `+5511999990002` e `1199990002` caem no mesmo responsável (opção A) ou o
  último é recusado (opção B).
- Fixo de 10 dígitos (`1132110000`) continua aceito e não ganha o `9`.
- O mesmo telefone em duas escolas é permitido; na mesma escola é recusado, com mensagem em
  português sem a palavra "tenant".

## Como retomar

1. Ler este arquivo e pedir ao Luiz a escolha entre A, B e C.
2. Branch `fix/telefone-nono-digito` a partir da `develop` atualizada (achados 1 e 2 juntos).
3. Corrigir, escrever os testes acima, rodar `.venv/bin/pytest -q` e `ruff check app tests`.
4. Opcional: nova rodada do `qa-browser` na mesma tela, com a URL `http://localhost:3010`,
   cobrindo também o que ficou em "Não testado".
