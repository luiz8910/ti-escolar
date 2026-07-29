# Política de backup

> **Estado atual: não existe política de backup.** O que existe é o *point-in-time
> recovery* que o Neon oferece por padrão — que é bom, mas **não é backup**, pelos motivos
> da seção 2. Este documento propõe a política e apresenta as opções para decisão.

---

## 1. O que estamos protegendo

Não é "o banco". É isto:

| Dado | Por que dói perder | Recuperável de outro lugar? |
|---|---|---|
| Fichas de matrícula (§D2) | Dado **sensível de menor**: cor/raça, CID, laudo, NIS, alergia. Coletado uma vez, no papel, com a família | Não. Refazer significa pedir tudo de novo a cada responsável |
| Alunos, responsáveis, turmas | Base de tudo; o vínculo aluno↔responsável↔turma é o que permite avisar a pessoa certa | Parcialmente (planilhas antigas da escola) |
| Conversas e mensagens | Prova do que a escola respondeu a um responsável — §H1 existe justamente para uso legal | **Não** |
| Auditoria (§13) | Rastreabilidade de quem fez o quê | Não |
| Base de conhecimento + embeddings | Reindexável a partir das fontes, se as fontes existirem | Sim, com trabalho |
| Logs (§16) | Diagnóstico | Não, e tudo bem — são descartáveis por desenho (retenção de 14 dias) |

**A pergunta que define o resto:** quanto de perda de dado a escola tolera? Para um
sistema que guarda ficha de matrícula de criança, a resposta honesta é **quase nada** —
e isso é o RPO.

---

## 2. Por que PITR do Neon não é, sozinho, uma política

O Neon mantém histórico e permite criar uma branch a partir de um instante no passado
(usado no passo 4 do `docs/runbook-rollback.md`). É excelente contra **erro de operação**
— `DELETE` errado, migration destrutiva, remoção de escola por engano.

Ele **não** cobre três coisas:

1. **Perda da conta.** PITR mora dentro do Neon. Conta suspensa por engano, cobrança
   recusada, disputa de acesso — e o histórico vai junto. Todo backup sério tem uma cópia
   **fora do provedor do dado**.
2. **Janela de retenção curta.** A janela depende do plano; nos planos de entrada ela é
   contada em **horas ou poucos dias**. Uma corrupção descoberta duas semanas depois (o
   caso realista: alguém nota em setembro que as fichas de agosto estão erradas) já não
   tem de onde voltar.
3. **Exportação para auditoria/LGPD.** "Prove o que havia na base em 1º de março" não se
   responde com PITR de 24h.

**Regra prática (3-2-1, versão enxuta):** ao menos **uma cópia fora do Neon**, testada.

---

## 3. Opções — para decidir

### Opção A · Só PITR do Neon (o que existe hoje)

- **Custo:** R$ 0 adicional.
- **RPO:** segundos, **dentro da janela de retenção**.
- **RTO:** minutos (criar branch e apontar).
- **Cobre:** erro de operação recente.
- **Não cobre:** perda de conta, corrupção descoberta tarde, exigência de auditoria.
- **Veredito:** insuficiente a partir da primeira escola real pagante.

### Opção B · PITR + `pg_dump` diário para armazenamento externo ✅ *recomendada*

Um job diário roda `pg_dump`, comprime e envia para um bucket fora do Neon (Cloudflare R2
— já usamos Cloudflare —, ou Backblaze B2/S3).

- **Custo:** R$ 0–5/mês nesta escala. O dump de um banco escolar com poucas escolas fica
  na casa de dezenas de MB comprimidos; o R2 tem 10 GB gratuitos e **não cobra egresso**,
  o que importa justamente na hora de restaurar.
- **RPO:** 24h para a cópia externa, **segundos** para o caso comum (PITR continua lá).
- **RTO:** ~15–30 min (baixar, `pg_restore`, apontar).
- **Cobre:** tudo da opção A **mais** perda de conta e corrupção descoberta tarde.
- **Onde rodar:** GitHub Actions agendado (`schedule: cron`) é o caminho de menor atrito —
  já temos CI, os *secrets* já vivem lá e não há servidor novo para manter. Alternativa:
  Render Cron Job (mais caro, mesma função).
- **Retenção sugerida:** 7 diários + 4 semanais + 12 mensais. Cabe folgado no free tier e
  cobre o "descobri em setembro" da seção 2.

### Opção C · Opção B + réplica em outro provedor

Um segundo Postgres (Supabase/RDS) recebendo restauração periódica, pronto para assumir.

- **Custo:** o de um segundo banco gerenciado + o tempo de manter os dois em dia.
- **RPO/RTO:** melhor, mas a diferença real vem de **fazer failover ensaiado**, não de ter
  a réplica.
- **Veredito:** desproporcional para o estágio atual. Reavaliar quando houver ~20 escolas
  ou um contrato com SLA escrito.

---

## 4. Recomendação

**Adotar a Opção B agora**, com estes parâmetros:

| Parâmetro | Valor proposto |
|---|---|
| RPO (perda máxima aceitável) | 24h para a cópia externa; segundos via PITR |
| RTO (tempo até voltar) | 30 min |
| Frequência do dump | diário, de madrugada (baixo uso) |
| Retenção | 7 diários + 4 semanais + 12 mensais |
| Destino | Cloudflare R2, bucket privado, credencial só de escrita no job |
| Criptografia | do lado do servidor no bucket; **o dump contém dado sensível de menor** |
| Teste de restauração | **trimestral**, restaurando num banco descartável |

O último item é o que separa política de teatro: **backup não testado não é backup**.
Um `pg_dump` que roda há meses e falha silenciosamente (senha trocada, disco cheio, banco
suspenso por inatividade) é indistinguível de um que funciona — até o dia em que importa.

### O que falta decidir (é sua chamada)

1. **Destino:** R2 (mesma conta Cloudflare do site) ou outro provedor?
2. **Retenção:** 12 meses de mensais é suficiente para a exigência da escola/LGPD, ou o
   contrato pede mais?
3. **Quem recebe o alerta** quando o job falhar? Hoje não há canal de alerta — é a mesma
   lacuna do item 8 do checklist. Sem isso, um backup quebrado passa despercebido.
4. **Anonimização:** o dump levado para fora carrega ficha de matrícula com CID e laudo.
   Aceitamos isso com criptografia no bucket, ou queremos um segundo dump anonimizado
   para uso em homologação?

---

## 5. Esboço do job (não implementado)

Referência para quando a decisão sair — **ainda não existe no repositório**:

```yaml
# .github/workflows/backup.yml  [PROPOSTA]
name: Backup diário do banco
on:
  schedule:
    - cron: "0 6 * * *"   # 03:00 em Brasília (o cron do GitHub é UTC)
  workflow_dispatch:       # permite disparar à mão antes de uma migration arriscada

jobs:
  dump:
    runs-on: ubuntu-latest
    steps:
      - name: Instala o cliente do Postgres
        run: sudo apt-get update && sudo apt-get install -y postgresql-client-16

      - name: Gera o dump
        env:
          DATABASE_URL: ${{ secrets.NEON_DATABASE_URL }}
        run: |
          set -euo pipefail   # sem isto, uma falha no meio do pipe passa como sucesso
          pg_dump --format=custom --no-owner "$DATABASE_URL" \
            > "backup-$(date -u +%Y-%m-%d).dump"

      - name: Envia para o R2
        # ... aws s3 cp com endpoint do R2 ...

      # Um dump de 0 byte é o modo clássico de falhar em silêncio.
      - name: Confere que o arquivo não está vazio
        run: test -s "backup-$(date -u +%Y-%m-%d).dump"
```

**Antes de considerar pronto:** rodar uma restauração completa num banco descartável e
cronometrar. O número obtido é o RTO real — o da tabela acima é estimativa.
