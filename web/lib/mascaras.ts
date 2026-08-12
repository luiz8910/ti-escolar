/**
 * Máscaras e formatos brasileiros do painel.
 *
 * O back-end **já normaliza e valida** tudo isto (`app/application/validacao.py`) — CPF
 * com dígitos verificadores, telefone em E.164, data em ISO. O que existe aqui não é uma
 * segunda validação: é o formato que a secretaria enxerga enquanto digita.
 *
 * Isso importa por dois motivos concretos:
 *
 * - **CPF e telefone sem pontuação são difíceis de conferir de olho.** Quem digita o
 *   documento de um aluno com a mãe esperando no balcão precisa bater o número com o
 *   papel, e `12345678909` não se confere; `123.456.789-09` sim.
 * - **A data era o pior caso.** O `<input type="date">` desenha no formato do *sistema
 *   operacional*, então uma máquina em inglês mostrava `mm/dd/aaaa` — e 03/04 vira dia 3
 *   de abril ou 4 de março dependendo de quem olha. Num cadastro escolar, data de
 *   nascimento trocada é matrícula errada.
 */

export function somenteDigitos(bruto: string): string {
  return (bruto || "").replace(/\D/g, "");
}

/* ---------- CPF ----------------------------------------------------------- */

export function mascaraCPF(bruto: string): string {
  const d = somenteDigitos(bruto).slice(0, 11);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `${d.slice(0, 3)}.${d.slice(3)}`;
  if (d.length <= 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`;
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}

/**
 * Confere os dois dígitos verificadores. Mesma regra do back-end, de propósito: o valor
 * de repetir é o **momento** do aviso — errar um dígito e descobrir só ao salvar, com a
 * mãe no balcão, é o que se quer evitar.
 *
 * Sequências de dígito repetido são recusadas: elas **passam** no algoritmo, e são
 * exatamente o que se digita para escapar de um campo obrigatório.
 */
export function cpfValido(bruto: string): boolean {
  const d = somenteDigitos(bruto);
  if (d.length !== 11 || d === d[0].repeat(11)) return false;
  const verificador = (parcial: string, pesoInicial: number) => {
    let soma = 0;
    for (let i = 0; i < parcial.length; i++) soma += Number(parcial[i]) * (pesoInicial - i);
    const resto = (soma * 10) % 11;
    return resto === 10 ? 0 : resto;
  };
  return (
    verificador(d.slice(0, 9), 10) === Number(d[9]) &&
    verificador(d.slice(0, 10), 11) === Number(d[10])
  );
}

/* ---------- Telefone ------------------------------------------------------ */

/**
 * `(xx) 9xxxx-xxxx` para celular, `(xx) xxxx-xxxx` para fixo.
 *
 * O DDI é descartado ao entrar: o back-end recoloca o `+55` ao normalizar, e deixar o
 * `55` visível faria a secretaria contá-lo como parte do DDD.
 */
export function mascaraTelefone(bruto: string): string {
  let d = somenteDigitos(bruto);
  if (d.length > 11 && d.startsWith("55")) d = d.slice(2);
  d = d.slice(0, 11);

  if (d.length <= 2) return d.length ? `(${d}` : "";
  const ddd = d.slice(0, 2);
  const resto = d.slice(2);
  if (resto.length <= 4) return `(${ddd}) ${resto}`;
  const corte = resto.length > 8 ? 5 : 4; // 9 dígitos = celular
  return `(${ddd}) ${resto.slice(0, corte)}-${resto.slice(corte)}`;
}

/** Telefone vindo da API (E.164) pronto para exibição em lista. */
export function formatarTelefone(e164: string): string {
  const mascarado = mascaraTelefone(e164);
  // Número estrangeiro não cabe no molde brasileiro: melhor mostrar como veio do que
  // recortá-lo em algo que ninguém consegue discar.
  return somenteDigitos(mascarado).length >= 10 ? mascarado : e164;
}

/* ---------- RA / matrícula ------------------------------------------------ */

/**
 * RA/RM do aluno: só dígitos, até 13.
 *
 * **Sem agrupamento de propósito.** O formato do RA varia por estado (São Paulo usa 12
 * dígitos mais um verificador; outras redes usam a matrícula interna), e pontuar no molde
 * errado é pior do que não pontuar — a secretaria passa a conferir contra um desenho que
 * o documento dela não tem.
 */
export function mascaraRA(bruto: string): string {
  return somenteDigitos(bruto).slice(0, 13);
}

/* ---------- Data ---------------------------------------------------------- */

export function mascaraData(bruto: string): string {
  const d = somenteDigitos(bruto).slice(0, 8);
  if (d.length <= 2) return d;
  if (d.length <= 4) return `${d.slice(0, 2)}/${d.slice(2)}`;
  return `${d.slice(0, 2)}/${d.slice(2, 4)}/${d.slice(4)}`;
}

/** `dd/mm/aaaa` → `aaaa-mm-dd`. Devolve `""` enquanto a data não está completa/válida. */
export function dataParaISO(digitada: string): string {
  const d = somenteDigitos(digitada);
  if (d.length !== 8) return "";
  const [dia, mes, ano] = [d.slice(0, 2), d.slice(2, 4), d.slice(4)];
  const data = new Date(`${ano}-${mes}-${dia}T00:00:00`);
  // Recusa 31/02: o `Date` aceita e "corrige" para 03/03, o que gravaria silenciosamente
  // uma data que ninguém digitou.
  if (
    Number.isNaN(data.getTime()) ||
    data.getMonth() + 1 !== Number(mes) ||
    data.getDate() !== Number(dia)
  ) {
    return "";
  }
  return `${ano}-${mes}-${dia}`;
}

/** `aaaa-mm-dd` → `dd/mm/aaaa`. Texto que não seja ISO volta como veio. */
export function dataDeISO(iso: string): string {
  const casa = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return casa ? `${casa[3]}/${casa[2]}/${casa[1]}` : iso || "";
}
