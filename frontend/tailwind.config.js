/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Outfit", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      colors: {
        gray: Object.fromEntries([100,200,300,400,500,600,700,800,900,950].map(n => [n, `rgb(var(--gray-${n}) / <alpha-value>)`])),
        brand: {
          500: "rgb(var(--accent) / <alpha-value>)",
          600: "rgb(var(--accent-dark) / <alpha-value>)",
        },
        navy: {
          600: "rgb(var(--surface-border) / <alpha-value>)",
          700: "rgb(var(--surface-border) / <alpha-value>)",
          800: "rgb(var(--surface) / <alpha-value>)",
          900: "rgb(var(--surface-deep) / <alpha-value>)",
        },
      },
    },
  },
  plugins: [],
};
