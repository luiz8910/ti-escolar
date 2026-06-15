import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Paleta inspirada no WhatsApp
        wa: {
          bg: "#efeae2",
          header: "#008069",
          out: "#d9fdd3",
          in: "#ffffff",
          panel: "#f0f2f5",
        },
      },
    },
  },
  plugins: [],
};

export default config;
