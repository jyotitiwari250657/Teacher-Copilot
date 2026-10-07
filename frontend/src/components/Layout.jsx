import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Users,
  BookOpen,
  ClipboardCheck,
  Layers,
  MessageSquare,
  Workflow as WorkflowIcon,
  Settings as SettingsIcon,
  LogOut,
  Menu,
  X,
  ShieldCheck,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'
import { Wordmark, AppBackdrop } from './brand'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/classes', label: 'Classes & Students', icon: Users },
  { to: '/lessons', label: 'Lesson Planner', icon: BookOpen },
  { to: '/grading', label: 'Grading', icon: ClipboardCheck },
  { to: '/differentiation', label: 'Differentiation', icon: Layers },
  { to: '/parent-updates', label: 'Parent Updates', icon: MessageSquare },
  { to: '/workflow', label: 'Weekly Workflow', icon: WorkflowIcon },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
]

export default function Layout() {
  const { teacher, config, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const [inbox, setInbox] = useState(0)
  const location = useLocation()

  useEffect(() => setMenuOpen(false), [location.pathname])

  // Keep the approval-inbox badge live.
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const data = await api.approvalInbox()
        if (!cancelled) setInbox(data.count || 0)
      } catch {
        /* the badge is decorative - ignore failures */
      }
    }
    load()
    const timer = setInterval(load, 15000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [location.pathname])

  const nav = (
    <div className="flex h-full flex-col">
      <div className="flex items-center px-5 py-5">
        <Wordmark />
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 pb-4">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${
                isActive
                  ? 'bg-brand-500/12 text-brand-300 ring-1 ring-brand-400/20'
                  : 'text-ink-500 hover:bg-ink-200/60 hover:text-ink-800'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span
                  aria-hidden="true"
                  className={`absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-brand-400 transition-opacity ${
                    isActive ? 'opacity-100' : 'opacity-0'
                  }`}
                />
                <Icon size={17} className="shrink-0" />
                <span className="flex-1 truncate">{label}</span>
                {to === '/parent-updates' && inbox > 0 && (
                  <span className="shrink-0 rounded-full bg-accent-500 px-1.5 py-0.5 text-[10px] font-bold text-ink-50">
                    {inbox}
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="space-y-3 border-t border-ink-200/70 p-4">
        <div className="rounded-lg border border-ink-200/60 bg-ink-200/30 p-3">
          <p className="truncate text-sm font-semibold text-ink-800">{teacher?.name}</p>
          <p className="truncate text-xs text-ink-400">
            {teacher?.school_name || teacher?.email}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="chip border-brand-400/25 bg-brand-500/12 text-brand-300">
              Runs in your browser
            </span>
          </div>
        </div>
        <button onClick={logout} className="btn-ghost btn-sm w-full justify-start">
          <LogOut size={15} />
          Sign out
        </button>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-ink-50">
      {/* Animated void backdrop, filtered into a slow nebula behind everything. */}
      <AppBackdrop />

      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-ink-200/70 bg-ink-100/80 backdrop-blur-xl lg:block">
        {nav}
      </aside>

      {menuOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-ink-900/70 backdrop-blur-sm"
            onClick={() => setMenuOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[85vw] animate-slide-up border-r border-ink-200/70 bg-ink-100 shadow-glass">
            <button
              onClick={() => setMenuOpen(false)}
              className="absolute right-3 top-4 rounded-md p-1.5 text-ink-400 transition-colors hover:bg-ink-200 hover:text-ink-800"
              aria-label="Close menu"
            >
              <X size={18} />
            </button>
            {nav}
          </aside>
        </div>
      )}

      <div className="relative z-10 lg:pl-64">
        <header className="sticky top-0 z-20 border-b border-ink-200/70 bg-ink-50/80 backdrop-blur-xl">
          <div className="flex items-center gap-3 px-4 py-3 sm:px-6">
            <button
              onClick={() => setMenuOpen(true)}
              className="btn-ghost btn-sm -ml-1 lg:hidden"
              aria-label="Open menu"
            >
              <Menu size={18} />
            </button>
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-sm font-semibold text-ink-800 sm:text-base">
                {NAV.find((item) =>
                  item.end ? location.pathname === item.to : location.pathname.startsWith(item.to),
                )?.label || 'TeacherCopilot'}
              </h1>
            </div>
            <span className="hidden items-center gap-1.5 rounded-full border border-brand-400/20 bg-brand-500/10 px-3 py-1 text-xs font-medium text-brand-300 sm:inline-flex">
              <ShieldCheck size={13} />
              You approve everything
            </span>
          </div>
        </header>

        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
          <Outlet />
        </main>

        <footer className="border-t border-ink-200/70 px-4 py-5 text-center text-xs text-ink-400 sm:px-6">
          TeacherCopilot — AI suggestions are drafts. Nothing is sent to a parent without your
          approval.
        </footer>
      </div>
    </div>
  )
}
