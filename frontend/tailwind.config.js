/**
 * Black + steel silver theme.
 *
 * The neutral, brand and semantic ramps are *inverted* on purpose: the low
 * numbers are dark surfaces and the high numbers are bright text. That keeps the
 * meaning of every existing class (`bg-ink-50` as a page tint, `text-ink-800`
 * as primary text, `border-ink-200` as a hairline) identical to the light
 * version, so the pages read correctly on dark without a rewrite.
 *
 * Surfaces run from near-black to gunmetal with a cool blue undertone - the
 * colour of brushed steel in shadow. `brand` is polished steel: a desaturated
 * cool grey used for accents, focus rings and the button glow. Status colours
 * (amber, red, green) are kept but desaturated roughly 45% so they read as
 * functional signals rather than fighting the monochrome.
 */
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Neutral ramp - black through gunmetal to bright steel.
        // ink.100 is lifted slightly: the app sits on a photographic backdrop,
        // and panels need to stay clearly separable from it.
        ink: {
          50: '#060709',
          100: '#101317',
          200: '#171b21',
          300: '#232830',
          400: '#79838f',
          500: '#98a2ae',
          600: '#b4bec9',
          700: '#cfd6de',
          800: '#e6eaf0',
          900: '#ffffff',
        },
        // Primary accent - polished steel silver.
        brand: {
          50: '#101318',
          100: '#191d23',
          200: '#252a31',
          300: '#98a3b0',
          400: '#c2cbd6',
          500: '#d9e0e8',
          600: '#e8edf3',
          700: '#f1f5f9',
          800: '#f8fafc',
          900: '#ffffff',
        },
        // Secondary accent - used sparingly for counts and highlights.
        accent: {
          50: '#101318',
          100: '#191d23',
          200: '#252a31',
          300: '#a8b2be',
          400: '#bcc5d0',
          500: '#ccd4dd',
          600: '#dde3ea',
          700: '#e9edf2',
          800: '#f2f5f8',
          900: '#fafbfc',
        },

        // --- semantic ramps: muted steel-tinted signals ---
        emerald: {
          50: '#071310',
          100: '#0c1e19',
          200: '#13302a',
          300: '#5fae95',
          400: '#5fae95',
          500: '#4f9c85',
          600: '#8bc7b2',
          700: '#b0dccb',
          800: '#d3ebe1',
          900: '#e7f4ee',
        },
        teal: {
          50: '#0a1214',
          100: '#101d20',
          200: '#173034',
          300: '#7ba3a8',
          400: '#7ba3a8',
          500: '#68908f',
          600: '#9cc2c4',
          700: '#bad7d8',
          800: '#d6e8e8',
          900: '#e9f2f2',
        },
        sky: {
          50: '#080f15',
          100: '#0d1a23',
          200: '#132833',
          300: '#6f97ab',
          400: '#6f97ab',
          500: '#5d8497',
          600: '#93b4c4',
          700: '#b3cdd9',
          800: '#d0e0e8',
          900: '#e5eff4',
        },
        amber: {
          50: '#131006',
          100: '#1e1a0d',
          200: '#2c2614',
          300: '#bb9445',
          400: '#bb9445',
          500: '#a8813a',
          600: '#cbaa68',
          700: '#dfc68e',
          800: '#eddfba',
          900: '#f6eedb',
        },
        orange: {
          50: '#140e06',
          100: '#21160c',
          200: '#312014',
          300: '#b87a4b',
          400: '#b87a4b',
          500: '#a66b40',
          600: '#cb9873',
          700: '#e0b899',
          800: '#efd4bf',
          900: '#f7e7da',
        },
        red: {
          50: '#150a0b',
          100: '#211013',
          200: '#311719',
          300: '#c27070',
          400: '#c27070',
          500: '#b25f5f',
          600: '#d19191',
          700: '#e2b3b3',
          800: '#eedede',
          900: '#f7eded',
        },
        rose: {
          50: '#160a0f',
          100: '#231017',
          200: '#351821',
          300: '#bb6b80',
          400: '#bb6b80',
          500: '#a95c70',
          600: '#cb8a99',
          700: '#dcafb9',
          800: '#ecd1d7',
          900: '#f6e9ec',
        },
        purple: {
          50: '#0e0c16',
          100: '#17141f',
          200: '#221e2e',
          300: '#9b8fbe',
          400: '#9b8fbe',
          500: '#887ca9',
          600: '#b1a8cb',
          700: '#c7c0da',
          800: '#ddd9e9',
          900: '#eceaf3',
        },
        violet: {
          50: '#0f0b16',
          100: '#18131f',
          200: '#241d2e',
          300: '#a08fbe',
          400: '#b0a3c7',
          500: '#8d7ba9',
          600: '#b4a7cb',
          700: '#c9bfda',
          800: '#ded9ea',
          900: '#edebf3',
        },
      },

      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'system-ui', '-apple-system', 'sans-serif'],
      },

      boxShadow: {
        glass: '0 24px 60px -20px rgba(0, 0, 0, 0.85)',
        // A hairline of steel along the top edge, then a deep drop.
        card: '0 1px 0 0 rgba(255,255,255,0.05) inset, 0 18px 40px -28px rgba(0,0,0,0.95)',
        glow: '0 0 0 1px rgba(194,203,214,0.28), 0 12px 40px -12px rgba(194,203,214,0.30)',
      },

      keyframes: {
        'fade-in': { '0%': { opacity: 0 }, '100%': { opacity: 1 } },
        'slide-up': {
          '0%': { opacity: 0, transform: 'translateY(8px)' },
          '100%': { opacity: 1, transform: 'translateY(0)' },
        },
        // One calm reveal for the whole login form - premium easing, 700ms.
        reveal: {
          '0%': { opacity: 0, transform: 'translateY(16px)' },
          '100%': { opacity: 1, transform: 'translateY(0)' },
        },
        shimmer: { '100%': { transform: 'translateX(100%)' } },
        'pulse-soft': { '0%,100%': { opacity: 1 }, '50%': { opacity: 0.55 } },
      },

      animation: {
        'fade-in': 'fade-in 0.25s ease-out',
        'slide-up': 'slide-up 0.3s ease-out',
        reveal: 'reveal 0.7s cubic-bezier(0.16, 1, 0.3, 1) both',
        shimmer: 'shimmer 1.6s infinite',
        'pulse-soft': 'pulse-soft 1.5s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}