import type { Config } from "tailwindcss";

/**
 * TI-Escolar — Tailwind config da landing page.
 *
 * Mesmos tokens do painel (`web/tailwind.config.ts`): as cores apontam para CSS
 * variables em canais RGB definidas em `app/globals.css`, então a LP e o painel
 * falam a mesma língua visual (marca Cobalt, neutros frios, âmbar de acento).
 * Modificadores de opacidade seguem funcionando: `bg-brand-600/10`.
 */
const rgb = (v: string) => `rgb(var(${v}) / <alpha-value>)`;

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: rgb("--brand-50"),
          100: rgb("--brand-100"),
          200: rgb("--brand-200"),
          500: rgb("--brand-500"),
          600: rgb("--brand-600"),
          700: rgb("--brand-700"),
          900: rgb("--brand-900"),
          DEFAULT: rgb("--brand-600"),
        },
        n: {
          50: rgb("--n-50"),
          100: rgb("--n-100"),
          200: rgb("--n-200"),
          300: rgb("--n-300"),
          400: rgb("--n-400"),
          500: rgb("--n-500"),
          600: rgb("--n-600"),
          700: rgb("--n-700"),
          800: rgb("--n-800"),
          900: rgb("--n-900"),
        },
        accent: {
          DEFAULT: rgb("--accent"),
          soft: rgb("--accent-soft"),
        },
        success: { DEFAULT: rgb("--success"), soft: rgb("--success-soft") },
        warning: { DEFAULT: rgb("--warning"), soft: rgb("--warning-soft") },
        danger: { DEFAULT: rgb("--danger"), soft: rgb("--danger-soft") },

        // Aliases semânticos de superfície
        bg: rgb("--bg"),
        surface: rgb("--surface"),
        border: rgb("--border"),
        text: rgb("--text"),
        muted: rgb("--text-muted"),

        // WhatsApp — só o mock de conversa do hero
        wa: {
          header: rgb("--wa-header"),
          bg: rgb("--wa-bg"),
          out: rgb("--wa-out"),
          in: rgb("--wa-in"),
          panel: rgb("--wa-panel"),
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
      },
      maxWidth: {
        content: "1120px",
      },
    },
  },
  plugins: [],
};

export default config;
