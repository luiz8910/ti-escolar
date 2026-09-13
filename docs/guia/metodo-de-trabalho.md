# §0 — Método de trabalho

> Este arquivo não descreve o produto. Descreve **como as sessões de desenvolvimento
> acontecem**: o que conta como progresso, como uma sessão abre e fecha, e o que Claude Code
> deve questionar antes de obedecer.
>
> Ele é anterior a todos os outros: as decisões de arquitetura (§4, §11) e o roadmap (§12,
> §12a) dizem *o que* construir; este diz *como não parar de construir*.

---

## §0.1 — O problema que este arquivo resolve

O projeto não está parado por falta de capacidade técnica nem de arquitetura. A base é
sólida, o guia é extenso, a produção existe. O que trava é **escopo e foco**: o guia cobre
17 áreas, e uma escola está esperando o beta há tempo demais.

Diagnóstico honesto: **construir não é o gargalo. Cortar é.**

Toda regra abaixo existe para separar o que entra no beta do que só parece urgente.

---

## §0.2 — A única métrica

Estas **não** medem progresso: commits, features "prontas", refactors, cobertura de testes,
áreas novas de guia, tempo trabalhado, infra melhorada.

A medida é uma só:

> **Quantos fluxos do corte do beta a escola consegue executar ponta a ponta hoje?**

Um fluxo só conta quando alguém da secretaria completa do início ao fim, em produção, sem
eu intervir. 90% pronto conta como zero.

**O corte do beta vive em [`roadmap.md`](roadmap.md) (§12a)**, marcado explicitamente — não
crie lista paralela. Se o corte ainda não estiver marcado lá, essa é a **primeira tarefa**
antes de qualquer código: escolher entre 5 e 8 fluxos e marcar o resto como pós-beta.

Depois de marcado, **o corte não cresce** até o beta estar na escola. Ideia nova vai para o
roadmap como pós-beta, sem discussão.

---

## §0.3 — Invariante × escopo

Distinção que não pode ser confundida:

- **Invariante** — não se corta, não se negocia, não se adia: `tenant_id` em toda consulta
  (§6), regra de dependência da hexagonal (§4), segredos fora do repo, LGPD em documento de
  menor (§6k, §17), migrations em cadeia linear (§6), branch `fix/` ou `feat/` a partir da
  `main` sincronizada.
- **Escopo** — tudo o mais. Feature, tela, integração, polimento, área nova de guia.

Corte de escopo **nunca** justifica quebrar invariante. E invariante **nunca** justifica
ampliar escopo ("já que estou aqui, faço a auditoria disso também").

---

## §0.4 — Ritual de sessão

**Ao abrir**, antes de código:

1. Recapitulação: onde paramos, o que mudou, estado do corte do beta no §12a.
2. O fluxo único da sessão — **um só**.
3. Execute com autonomia. **Não espere aprovação de escopo** — abra a branch (`fix/` ou
   `feat/` a partir da `main` sincronizada) e trabalhe. A revisão acontece no PR.
4. **Ação irreversível é exceção e continua exigindo aviso antes**, porque não passa pelo
   PR: migration aplicada, deploy (homolog ou produção), DNS, dado de produção, envio real
   pela Meta (custo por mensagem).

**Ao fechar**, pergunte e registre em `LOG.md`:

1. O fluxo saiu de `não funciona` para `funciona`? Sim/não.
2. Se não: classifique pela taxonomia §0.5 — uma palavra, sem justificar.
3. Primeira ação da próxima sessão.
4. Precisa de deploy? Lembre que **merge não publica**: homolog é *Manual Deploy* no Render,
   produção é `cd backend && fly deploy` (§12a).

Se eu não fechar a sessão, cobre no início da próxima. O registro é o que faz o método
funcionar.

---

## §0.5 — Taxonomia de sessão travada

Sessão que não moveu fluxo recebe **um** rótulo:

| Tipo | O que é |
|---|---|
| `escopo` | Comecei em A e terminei em B |
| `infra` | Consumida por deploy, ambiente, config, credenciais |
| `refactor` | Melhorei código que já funcionava |
| `decisão` | Fiquei escolhendo entre opções em vez de executar |
| `dependência` | Travou em sócio, escola, Meta, aprovação de template |
| `polimento` | Melhorei algo que a escola não notaria |
| `documentação` | Escrevi guia em vez de entregar fluxo |

**Não proponha correção com uma ocorrência.** Uma sessão travada é ruído. Quando o mesmo
rótulo aparecer **três vezes**, pare e traga o padrão com proposta de mudança estrutural.

---

## §0.6 — Regras de escopo

- **Um fluxo por sessão.** Terminou antes? Sessão encerrada — não emende outro.
- **Não invente requisito.** Fora do corte do beta não existe. Pergunte antes.
- **Refactor não solicitado não acontece.** Código feio que funciona fica.
- **Área nova de guia é sinal de alerta.** Escrever `docs/guia/x.md` novo antes do beta
  quase sempre é escopo disfarçado de organização. Questione uma vez.
- **Infra tem teto de 30 min.** Passou disso, pare e me avise.
- **Serviço pago é último recurso.** Meta e LLM em modo de teste; custo por uso é restrição
  real, não detalhe.
- **Se eu pedir algo fora do fluxo do dia**, me lembre uma vez. Se eu insistir, faça.

---

## §0.7 — Aprender × entregar

Este projeto é também meu laboratório de Python/FastAPI e IA, e isso é legítimo — mas é a
causa mais provável de o beta não sair. Aprofundar é mais interessante que terminar.

Regra: **profundidade técnica só depois que o fluxo do beta funcionar.** Melhorar RAG,
trocar provider, otimizar embedding, generalizar porta — tudo isso é pós-beta salvo se um
fluxo do corte estiver quebrado por causa disso.

Quando eu propuser aprofundamento, sua pergunta padrão é: **"isso destrava um fluxo do beta
ou é o caminho mais interessante?"** Uma vez só; depois respeite a decisão.

---

## §0.8 — Ambiente honesto

Dev local não mede nada: sem usuário real, sem custo de erro, tudo parece funcionar. O único
ambiente que mede é **a secretaria da escola usando**.

Portanto, entre "melhorar o que existe" e "colocar na frente do usuário real", a resposta é
sempre a segunda — e você deve me lembrar quando eu escolher a primeira. Um fluxo feio em
uso vale mais que cinco fluxos que eu acho que estão prontos.

---

## §0.9 — Postura

- Direto. Discorde quando eu estiver errado, sem rodeio.
- Explique o porquê e use analogia antes de mostrar código.
- Recomendação enxuta e fundamentada, não lista exaustiva de opções.
- Se eu estiver evitando a mesma tarefa há várias sessões, diga isso na cara.