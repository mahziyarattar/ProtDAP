import type { Config } from 'tailwindcss'

// Tailwind v4 auto-detects template content and doesn't strictly require
// this file, but it's kept for editor IntelliSense and explicit `content`
// globs, and to give the project a place to extend the theme later.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {},
  },
} satisfies Config
