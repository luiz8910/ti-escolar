// Cliente da API do back-end TI-Escolar.

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Tenant fixo do seed de demonstração (Escola Demonstração).
//
// ⚠️ Sobrou **apenas** para o portal do professor (`lib/professor.ts`), onde o login
// precisa do tenant antes de haver sessão e ainda não há como o navegador do professor
// descobrir a escola. Isso é uma limitação conhecida: hoje o portal do professor só
// atende a escola de demonstração.
//
// No painel admin ele NÃO é mais usado. Era o fallback de `tenantEmFoco()` para o super
// admin (que tem `tenant_id` nulo), e o efeito era operar em silêncio sobre a escola de
// demonstração em toda tela de escola. Ali a escola em foco passou a ser escolha
// explícita — ver `tenantEmFoco()` em `lib/admin.ts`.
export const DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001";
