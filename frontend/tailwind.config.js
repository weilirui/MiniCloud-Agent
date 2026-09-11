/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: '#0f1115',
          panel: '#171a21',
          card: '#1f232c',
        },
        text: {
          primary: '#e6e8eb',
          muted: '#8b94a3',
        },
        accent: {
          DEFAULT: '#7c3aed',
          hover: '#6d28d9',
        },
        success: '#10b981',
        danger: '#ef4444',
      },
    },
  },
  plugins: [],
};