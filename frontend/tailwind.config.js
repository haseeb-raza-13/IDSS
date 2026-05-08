/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        alert: {
          red: "#dc2626",
          orange: "#ea580c",
          yellow: "#ca8a04",
          green: "#16a34a",
        },
      },
    },
  },
  plugins: [],
};
