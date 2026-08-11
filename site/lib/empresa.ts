/**
 * Dados institucionais do TI-Escolar — ponto único de verdade da landing page.
 *
 * ┌──────────────────────────────────────────────────────────────────────────┐
 * │ IMPORTANTE — verificação da empresa na Meta                              │
 * │                                                                          │
 * │ A Meta compara estes dados, caractere por caractere, com o documento     │
 * │ enviado (Cartão CNPJ / CCMEI) e com o que está cadastrado em             │
 * │ "Informações da empresa" no Business Manager. Qualquer divergência       │
 * │ (abreviação, acento, número faltando) é motivo de reprovação.            │
 * │                                                                          │
 * │ Preencha os campos marcados com PENDENTE copiando do Cartão CNPJ.        │
 * └──────────────────────────────────────────────────────────────────────────┘
 */

/** Marcador dos campos que ainda precisam ser preenchidos com os dados reais. */
export const PENDENTE = "«preencher»";

type DadosEmpresa = {
  nome: string;
  razaoSocial: string;
  cnpj: string;
  endereco: {
    logradouro: string;
    bairro: string;
    cidade: string;
    uf: string;
    cep: string;
  };
  telefone: string;
  email: string;
  site: string;
  painelUrl: string;
};

/**
 * Os campos são tipados como `string` (e não como literais via `as const`) de
 * propósito: assim as checagens `!== PENDENTE` espalhadas pelas páginas seguem
 * sendo comparações válidas mesmo com tudo preenchido, e continuam protegendo
 * caso algum campo volte a ficar em aberto.
 */
export const EMPRESA: DadosEmpresa = {
  /**
   * Marca sob a qual o serviço é oferecido.
   * Atenção: o Cartão CNPJ não registra nome fantasia ("TÍTULO DO ESTABELECIMENTO"
   * em branco), então "TI-Escolar" é apenas a marca comercial — por isso o rodapé
   * e os documentos legais sempre exibem também a razão social.
   */
  nome: "TI-Escolar",

  /** Razão social exatamente como no Cartão CNPJ ("NOME EMPRESARIAL"). */
  razaoSocial: "LUIZ FERNANDO SANCHES",

  /** CNPJ da matriz, conforme Cartão CNPJ emitido em 24/06/2026 (situação ATIVA). */
  cnpj: "60.116.323/0001-77",

  endereco: {
    logradouro: "Rua Odete Gori Bicudo, 601", // No cartão: "R ODETE GORI BICUDO", nº 601
    bairro: "Nova Votorantim",
    cidade: "Votorantim",
    uf: "SP",
    cep: "18113-400",
  },

  /**
   * Telefone comercial (celular, com o nono dígito).
   * O Cartão CNPJ ainda registra a forma antiga, de 8 dígitos ("9745-4531"),
   * anterior ao nono dígito — este é o número em uso. Use exatamente este valor
   * também em Business Manager → Informações da empresa, para que site e cadastro
   * batam entre si.
   */
  telefone: "(15) 99745-4531",

  /** E-mail institucional (Cloudflare Email Routing → Gmail). */
  email: "contato@tiescolar.com.br",

  site: "https://tiescolar.com.br",

  /**
   * URL do painel administrativo (produto), publicado na Vercel. O endereço do Render é o
   * back-end (API/webhook) e não serve o painel — apontar para lá deixava o botão "Entrar no
   * painel" caindo em 404. Aponta para `/admin/login` e não para a raiz porque a raiz só
   * redireciona pelo cliente (responde 307 sem `Location`, com o shell do Next); o login é
   * 200 direto, que é o destino de quem clica no botão.
   */
  painelUrl: "https://ti-escolar.vercel.app/admin/login",
};

/** Endereço em uma linha, para o rodapé. Omite o que ainda está pendente. */
export function enderecoCompleto(): string {
  const { logradouro, bairro, cidade, uf, cep } = EMPRESA.endereco;
  const partes = [
    logradouro,
    bairro,
    [cidade, uf].filter((p) => p !== PENDENTE).join(" — "),
    cep !== PENDENTE ? `CEP ${cep}` : PENDENTE,
  ];
  return partes.filter((p) => p && p !== PENDENTE && p !== "").join(" · ");
}

/** `true` quando todos os dados legais já foram preenchidos. */
export function dadosLegaisCompletos(): boolean {
  const valores = [
    EMPRESA.razaoSocial,
    EMPRESA.cnpj,
    EMPRESA.telefone,
    ...Object.values(EMPRESA.endereco),
  ];
  return valores.every((v) => v !== PENDENTE);
}

/** Data da última atualização dos documentos legais (privacidade/termos). */
export const ATUALIZADO_EM = "26 de julho de 2026";
