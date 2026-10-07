import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

/**
 * Botanical full-screen login.
 *
 * One photographic background sits behind both halves. The left half shows it
 * untouched; the right half lays a thin glass sheet over the *same* image, so the
 * photograph reads through the panel instead of being replaced by a solid card.
 * Everything is scoped to `.tc-login` and sized to the viewport, so the page
 * never scrolls.
 */
const BACKGROUND =
  'https://images.unsplash.com/photo-1624616802045-f7a4ab36862d?auto=format&fit=crop&w=2400&q=88'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/

/**
 * Reusable presentational shell.
 *
 * @param {(credentials: {email: string, password: string, remember: boolean}) => Promise<void>} onSubmit
 * @param {() => void} [onForgotPassword]
 * @param {() => void} [onRegister]
 */
export function LoginScreen({ onSubmit, onForgotPassword, onRegister, notice }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    if (busy) return

    if (!EMAIL_PATTERN.test(email.trim())) {
      setStatus('Please enter a valid email address.')
      return
    }
    if (!password) {
      setStatus('Please enter your password.')
      return
    }

    setBusy(true)
    setStatus('Signing you in…')
    try {
      await onSubmit({ email: email.trim(), password, remember })
      setStatus('')
    } catch (error) {
      setStatus(error?.message || 'Something went wrong. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="tc-login tc-reveal relative isolate flex w-full overflow-hidden bg-black">
      {/* The single photographic background, shared by both halves. */}
      <img
        src={BACKGROUND}
        alt=""
        aria-hidden="true"
        className="absolute inset-0 h-full w-full object-cover object-center brightness-[0.68] contrast-[1.08] saturate-[0.7]"
        draggable="false"
      />

      {/* Left: the photograph, deliberately left empty. */}
      <div className="relative hidden w-1/2 shrink-0 lg:block" aria-hidden="true" />

      {/* Right: the same photograph under a thin sheet of glass. */}
      <div className="relative flex w-full flex-1 items-center justify-center lg:w-1/2 lg:shrink-0">
        {/* Glass: a whisper of black, 10px of blur, one faint hairline of light. */}
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-black/28 backdrop-blur-[10px] shadow-[inset_1px_0_0_rgba(255,255,255,0.10)]"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-gradient-to-b from-white/[0.07] via-transparent to-transparent"
        />
        {/* Faint vertical divider between the two sections. */}
        <div
          aria-hidden="true"
          className="absolute inset-y-0 left-0 hidden w-px bg-white/12 lg:block"
        />

        <main className="relative w-full max-w-[680px] px-7 py-8 sm:px-10 lg:px-12">
          {/* 1. Heading - nudged up, independently of the rest. */}
          <header className="tc-heading text-center">
            <p className="text-[11px] font-semibold uppercase tracking-[0.34em] text-white/55">
              Member access
            </p>
            <h1 className="tc-title mt-3 text-[2.5rem] font-bold leading-[1.08] tracking-[-0.03em] text-white sm:text-[3rem]">
              Welcome back
            </h1>
            <p className="mx-auto mt-3 max-w-sm text-[15px] leading-relaxed text-white/65">
              Enter your details to continue your journey.
            </p>
          </header>

          <form onSubmit={handleSubmit} className="tc-form mt-0" noValidate>
            {/* 2. Inputs - sitting at the visual centre of the panel. */}
            <div className="mt-9 space-y-9 sm:space-y-10">
              <div>
                <label className="tc-label" htmlFor="tc-email">
                  Email address
                </label>
                <input
                  id="tc-email"
                  className="tc-field"
                  type="email"
                  name="email"
                  autoComplete="email"
                  placeholder="Enter your email"
                  value={email}
                  disabled={busy}
                  aria-describedby="tc-status"
                  onChange={(event) => setEmail(event.target.value)}
                />
              </div>

              <div>
                <label className="tc-label" htmlFor="tc-password">
                  Password
                </label>
                <input
                  id="tc-password"
                  className="tc-field"
                  type="password"
                  name="password"
                  autoComplete="current-password"
                  placeholder="Enter your password"
                  value={password}
                  disabled={busy}
                  aria-describedby="tc-status"
                  onChange={(event) => setPassword(event.target.value)}
                />
              </div>
            </div>

            {/* 3. Account options. */}
            <div className="mt-8 flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
              <label className="flex cursor-pointer items-center gap-2.5 text-[14px] text-white/75 transition-colors hover:text-white">
                <input
                  type="checkbox"
                  name="remember"
                  className="tc-checkbox"
                  checked={remember}
                  disabled={busy}
                  onChange={(event) => setRemember(event.target.checked)}
                />
                <span>Remember me</span>
              </label>

              <button
                type="button"
                onClick={onForgotPassword}
                className="rounded-[2px] text-[14px] text-white/65 underline-offset-4 transition-colors hover:text-white hover:underline focus-visible:text-white"
              >
                Forgot your password?
              </button>
            </div>

            {/* 4. CTA - pushed lower than the options row. */}
            <div className="tc-action mt-10">
              <button
                type="submit"
                disabled={busy}
                className="tc-cta group flex w-full items-center justify-center rounded-[3px] bg-black text-[15px] font-bold tracking-[0.01em] text-white transition-all duration-200 hover:-translate-y-0.5 hover:bg-[#1c1c1c] focus-visible:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-black disabled:pointer-events-none disabled:opacity-60"
              >
                {busy ? 'Signing in…' : 'Log in'}
              </button>

              <p className="mt-6 text-center text-[14px] text-white/60">
                Don&rsquo;t have an account?{' '}
                <button
                  type="button"
                  onClick={onRegister}
                  className="rounded-[2px] font-bold text-white underline-offset-4 transition-opacity hover:opacity-80 hover:underline focus-visible:underline"
                >
                  Register here
                </button>
              </p>

              {notice && (
                <p className="mt-4 text-center text-[12px] text-white/45">{notice}</p>
              )}
            </div>

            {/* Accessible, polite feedback for both errors and progress. */}
            <p
              id="tc-status"
              role="status"
              aria-live="polite"
              className="mt-4 min-h-[1.25rem] text-center text-[13px] text-white/75"
            >
              {status}
            </p>
          </form>
        </main>
      </div>
    </div>
  )
}

/** Project-specific wrapper: connects the shell to the real auth provider. */
export default function Login() {
  const { teacher, login } = useAuth()

  if (teacher) return <Navigate to="/" replace />

  return (
    <LoginScreen
      notice="Demo account — demo@teachercopilot.app / demo1234"
      onSubmit={({ email, password, remember }) => login(email, password, remember)}
      onForgotPassword={() =>
        window.alert(
          'Password reset is not wired up in this demo build.\n\nDemo account: demo@teachercopilot.app / demo1234',
        )
      }
      onRegister={() =>
        window.alert(
          'TeacherCopilot is pre-provisioned per school, so accounts are created by your administrator.\n\nDemo account: demo@teachercopilot.app / demo1234',
        )
      }
    />
  )
}
