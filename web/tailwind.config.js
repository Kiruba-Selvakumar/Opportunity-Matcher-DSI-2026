/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#f3efe6',
        surface: '#fffcf6',
        sunk: '#ebe5d8',
        line: { DEFAULT: '#e2dacb', strong: '#cbc0ab' },
        ink: { DEFAULT: '#1f1c17', soft: '#544e44', faint: '#6e675b' },
        navy: '#1b2d27',
        accent: { DEFAULT: '#2c6148', dark: '#204a37', soft: '#e3ebdf' },
        pine: { DEFAULT: '#143528', 700: '#1c4535', ink: '#e9e4d4', soft: '#a9bfae' },
        maple: { DEFAULT: '#c0392b', soft: '#f8e2dc', line: '#eab3a8' },
        pass: { DEFAULT: '#33672b', soft: '#e6eedb', line: '#bcd0a6' },
        fail: { DEFAULT: '#9c3521', soft: '#f5e3dc', line: '#e0b3a5' },
        amber: { DEFAULT: '#85540a', soft: '#f6ebd3', line: '#dfc790' },
        sky: { DEFAULT: '#2f6aa6', soft: '#e0ebf6', line: '#b5cde6' },
        pear: { DEFAULT: '#7d9a2c', soft: '#eef2d6', line: '#cfdc9c' },
        plum: { DEFAULT: '#7a3b6c', soft: '#f3e4ef', line: '#dcb9d3' },
      },
      fontFamily: {
        sans: ['Geist', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        serif: ['Newsreader', 'Georgia', 'serif'],
        mono: ['"Geist Mono"', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        xs: ['12px', '17.6px'],
        sm: ['13px', '20px'],
        base: ['15px', '23.2px'],
        lg: ['17px', '24px'],
        xl: ['20px', '27.2px'],
        '2xl': ['26px', '32px'],
        '3xl': ['36px', '40px'],
      },
      boxShadow: {
        paper: '0 1px 0 rgba(60,45,20,0.04), 0 8px 24px -12px rgba(60,45,20,0.18)',
        lift: '0 2px 4px rgba(60,45,20,0.06), 0 18px 40px -16px rgba(60,45,20,0.28)',
      },
      transitionTimingFunction: { out: 'cubic-bezier(0.16, 1, 0.3, 1)' },
    },
  },
  plugins: [],
}
