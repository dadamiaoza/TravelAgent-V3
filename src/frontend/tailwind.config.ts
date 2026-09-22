import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        chrome: "var(--bg-chrome)",
        elevated: "var(--bg-unified-elevated)",
        ink: {
          DEFAULT: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          tertiary: "var(--text-tertiary)",
        },
        line: {
          tertiary: "var(--border-tertiary)",
        },
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
} satisfies Config;
