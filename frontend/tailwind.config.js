/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        aurelia: {
          bg: "#08090B",
          secondary: "#0D0F12",
          card: "#121418",
          surface: "#181B20",
          hover: "#22262D",
          border: "rgba(255, 255, 255, 0.09)",
          bronze: "#C59A55",
          gold: "#E6C17A",
          amber: "#8B622F",
          success: "#42D6A4",
          error: "#F07878",
          info: "#82AFFF",
        }
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      boxShadow: {
        card: "0 12px 36px -8px rgba(0, 0, 0, 0.65), 0 0 0 1px rgba(255, 255, 255, 0.09)",
        bronze: "0 0 30px -5px rgba(197, 154, 85, 0.25)",
      }
    },
  },
  plugins: [],
}
