# Base de conhecimento, LLM e documentos externos

> Parte do guia do TI-Escolar — índice em [`CLAUDE.md`](../../CLAUDE.md).
> A numeração das seções (§6a, §9c, …) é a original: as referências cruzadas
> espalhadas pelos outros documentos continuam valendo.

### 6b. Base de conhecimento por tenant e system prompt da escola

- **Documentos da escola (RAG):** o admin sobe textos/arquivos de procedimentos
  (`FonteConhecimento`); o caso de uso `IngerirDocumento` fragmenta o conteúdo
  (`fragmentar`), gera embeddings e indexa cada trecho no `VectorStore` com `fonte_id`
  apontando para a fonte. Isso enriquece o contexto da LLM **apenas daquele tenant**.
  Gestão via `app/interfaces/api/conhecimento.py` (`/api/admin/conhecimento`):
  listar, **abrir**, **editar** e **ligar/desligar a indexação**; remover apaga a fonte e
  seus trechos.
  - **O texto original é persistido** (`FonteConhecimento.conteudo`, migration
    `0031_fonte_conhecimento_conteudo`). Antes o documento só existia fragmentado no vector
    store: dava para apagar, nunca para reler ou corrigir uma linha. A migration **recupera
    o texto dos documentos antigos** recolando os trechos indexados (`string_agg` ordenado
    por `criado_em, id`) — reconstrução, não o original byte a byte, e exata para documento
    de um trecho só.
  - **`ativo` separa existir de estar indexado.** Desativada, a fonte fica com zero trechos
    no vector store; `total_trechos` continua contando os fragmentos que o texto *tem*,
    para o número não oscilar a cada clique. `AtualizarFonteConhecimento` **reindexa
    sempre** (apaga os trechos e regrava), porque reindexação incremental deixaria trecho
    órfão quando o texto encurtasse — e trecho órfão no RAG é o bot respondendo regra
    revogada.
  - **Apagar exige super admin**; a escola tem `PUT .../ativo` no lugar. Destruir o texto é
    irreversível, e o que a secretaria precisa no dia a dia é tirar do ar um procedimento
    vencido — sem esperar por nós, senão o assistente segue citando a regra antiga.
- **System prompt do tenant (`PromptTenant`):** um "CLAUDE.md" por escola, editável no
  painel (`/api/admin/prompt`). É anexado às diretrizes-base do assistente
  (`montar_sistema` / `montar_sistema_agente`) e tem **prioridade institucional**.
  `ResponderDuvida` e `AtenderConversa` recebem um `PromptTenantRepository` opcional e
  injetam o texto da escola no prompt de sistema.
- **Painel:** páginas `web/app/admin/conhecimento/` (upload/lista) e `web/app/admin/prompt/`
  (editor das instruções). O upload lê o arquivo no navegador e envia o texto via JSON
  (sem multipart no servidor).

---

## 7. Camada de LLM

- Contrato único: porta **`LLMProvider`** no domínio (ex.: `gerar(prompt/messages, opções) -> resposta`).
- Adaptadores concretos ficam em **`infrastructure/`**; a **seleção do provedor/modelo é por
  variável de ambiente**. Nenhuma chamada a SDK de LLM fora da infraestrutura.
- O **"raciocínio" sobre a resposta** acontece no caso de uso de orquestração RAG
  (`ResponderDuvida`): recupera trechos relevantes, monta o contexto, chama o `LLMProvider` e
  retorna a resposta **com citação de fonte**.

---

## 8. Integrações de documentos

- Porta **`DocumentSource`** abstrai sistemas externos (sistema acadêmico, drive, etc.).
- Por enquanto, **adaptadores mock** em `infrastructure/` simulam a recuperação de documentos.
- **Para adicionar uma integração real:** implementar um novo adaptador de `DocumentSource` sem
  tocar em domínio/aplicação; registrar via injeção de dependência/config.
