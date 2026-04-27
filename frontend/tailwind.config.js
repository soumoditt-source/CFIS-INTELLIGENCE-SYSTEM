/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      colors: {
        aegis: {
          50:  "#eef2ff",
          100: "#e0e7ff",
          200: "#c7d2fe",
          300: "#a5b4fc",
          400: "#818cf8",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
          800: "#3730a3",
          900: "#312e81",
          950: "#1e1b4b",
        },
        surface: {
          0:    "#0a0b0f",
          50:   "#0f1117",
          100:  "#141720",
          200:  "#1a1f2e",
          300:  "#212639",
          400:  "#2a3044",
          500:  "#353b52",
        },
      },
      backgroundImage: {
        "glass": "linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)",
        "aurora": "radial-gradient(ellipse 80% 50% at 50% -20%, rgba(99,102,241,0.3), transparent)",
        "hero-glow": "radial-gradient(ellipse 60% 60% at 50% 50%, rgba(79,70,229,0.15), transparent 70%)",
        "card-glow": "linear-gradient(135deg, rgba(99,102,241,0.08), rgba(168,85,247,0.04))",
        "sentiment-positive": "linear-gradient(135deg, #059669, #10b981)",
        "sentiment-negative": "linear-gradient(135deg, #dc2626, #ef4444)",
        "sentiment-neutral":  "linear-gradient(135deg, #4b5563, #6b7280)",
      },
      boxShadow: {
        "glass": "0 8px 32px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255,255,255,0.06)",
        "glow-indigo": "0 0 30px rgba(99,102,241,0.3)",
        "glow-green":  "0 0 20px rgba(16,185,129,0.25)",
        "glow-red":    "0 0 20px rgba(239,68,68,0.25)",
        "card":  "0 4px 24px rgba(0,0,0,0.4)",
        "fab":   "0 8px 32px rgba(79,70,229,0.5)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
        "float":      "float 6s ease-in-out infinite",
        "scan":       "scan 2s linear infinite",
        "shimmer":    "shimmer 2s linear infinite",
        "fade-up":    "fadeUp 0.5s ease-out",
      },
      keyframes: {
        float:   { "0%,100%": { transform: "translateY(0px)" }, "50%": { transform: "translateY(-12px)" } },
        scan:    { "0%": { top: "0%" }, "100%": { top: "100%" } },
        shimmer: { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
        fadeUp:  { "0%": { opacity: 0, transform: "translateY(16px)" }, "100%": { opacity: 1, transform: "translateY(0)" } },
      },
      backdropBlur: { xs: "2px" },
      borderRadius:  { "2xl": "1rem", "3xl": "1.5rem", "4xl": "2rem" },
    },
  },
  plugins: [],
};
