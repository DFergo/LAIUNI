/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Branding tokens (Sprint 43): CSS variables set from the backend's catalog (src/brand.ts)
        'brand-primary': 'rgb(var(--brand-primary) / <alpha-value>)',
        'brand-on-primary': 'rgb(var(--brand-on-primary) / <alpha-value>)',
        'brand-accent': 'rgb(var(--brand-accent) / <alpha-value>)',
        'brand-dark': 'rgb(var(--brand-dark) / <alpha-value>)',
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
