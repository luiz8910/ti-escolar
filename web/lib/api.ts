// Cliente da API do back-end TI-Escolar.

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Tenant fixo do seed de demonstração (Escola Demonstração). Usado só como fallback de
// escopo quando a sessão ainda não diz a qual escola o usuário pertence.
export const DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001";
