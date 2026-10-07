/**
 * The TeacherCopilot mark, drawn as plain SVG.
 *
 * Concept: an open ring with a deliberate gap on the right, and a single solid
 * node sitting in that gap - the copilot beside the teacher. It is built from two
 * primitives so it stays crisp at 14px in the sidebar and at 40px on its own.
 * No icon font, no generated-looking stock mark.
 */

/** The bare glyph. Inherits `currentColor`, so it can live on any surface. */
export function BrandMark({ size = 24, className = '', title = 'TeacherCopilot' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      role="img"
      aria-label={title}
    >
      <path
        d="M19 12a8 8 0 1 1-2.34-5.66"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
      />
      <circle cx="18.25" cy="12" r="2.15" fill="currentColor" />
    </svg>
  )
}

/**
 * Mark plus wordmark. The graphic is SVG; the name stays real text so it is
 * selectable, searchable and never mis-rendered by a missing font.
 */
export function Wordmark({ size = 30, className = '' }) {
  return (
    <span className={`flex items-center gap-2.5 ${className}`}>
      <BrandMark size={size} className="shrink-0 text-brand-400" />
      <span className="flex flex-col leading-none">
        <span className="text-[15px] font-bold tracking-tight text-ink-800">TeacherCopilot</span>
        <span className="mt-1 text-[10.5px] font-medium tracking-[0.02em] text-ink-400">
          Your AI teaching assistant
        </span>
      </span>
    </span>
  )
}

/**
 * The "an agent did this" affordance, used on generate buttons and next to AI
 * output. A small node graph - the orchestrator idea - rather than a sparkle,
 * so it reads as part of this product's own language.
 */
export function AiGlyph({ size = 16, className = '' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M12 6.6 6.4 10.2M12 6.6l5.6 3.6M6.4 10.2v4.1M17.6 10.2v4.1M6.4 14.3 12 18l5.6-3.7"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <circle cx="12" cy="6" r="2.1" fill="currentColor" />
      <circle cx="5.6" cy="18.4" r="1.9" fill="currentColor" />
      <circle cx="18.4" cy="18.4" r="1.9" fill="currentColor" />
    </svg>
  )
}

/**
 * The app backdrop: a near-black, fully desaturated photograph behind every
 * authenticated page.
 *
 * The source is 626x358 - too small to show sharp at desktop widths - so it is
 * blurred and scaled slightly past the viewport. That turns it into a soft
 * ambient wash rather than a visible photograph, which is both the right look
 * and the honest way to use a low-resolution source. A scrim on top holds the
 * surface near-black so the steel palette keeps its contrast.
 *
 * The login page deliberately does NOT use this - it keeps its own botanical
 * glass composition.
 */
export function AppBackdrop({ className = '' }) {
  return (
    <div className={`app-backdrop ${className}`} aria-hidden="true">
      <div className="app-backdrop-image" />
      <div className="app-backdrop-scrim" />
      <span className="app-backdrop-sheen" />
    </div>
  )
}

/** Kept for reference: the animated void backdrop (Uiverse "void-pulse" by
 *  chase2k25), superseded by {@link AppBackdrop}. */
export function VoidBackdrop({ className = '' }) {
  return (
    <>
      {/* Kept in the DOM (never display:none) so url(#void-texture) resolves. */}
      <svg className="void-texture-svg" aria-hidden="true" focusable="false">
        <filter id="void-texture">
          <feTurbulence result="noise" numOctaves="3" baseFrequency="0.02" type="turbulence" />
          <feGaussianBlur result="blur" stdDeviation="1" in="noise" />
          <feSpecularLighting
            result="specular"
            lighting-color="#c2cbd6"
            specularExponent="20"
            specularConstant="1"
            surfaceScale="3"
            in="blur"
          >
            <feDistantLight elevation="45" azimuth="90" />
          </feSpecularLighting>
          <feComposite result="lit" operator="over" in2="SourceGraphic" in="specular" />
          <feBlend mode="screen" in2="lit" in="SourceGraphic" />
        </filter>
      </svg>

      <div className={`void-pulse ${className}`} aria-hidden="true">
        <span className="orbit-overlay" />
      </div>
    </>
  )
}