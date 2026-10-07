import { useEffect, useState } from 'react'
import {
  Settings as SettingsIcon,
  Cpu,
  Mail,
  ShieldCheck,
  Clock,
  Save,
  RefreshCw,
} from 'lucide-react'
import { api, resetDb as resetDemo } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { Card, CardHeader, Field, Toggle, Spinner } from '../components/ui'

export default function Settings() {
  const { teacher, config, refreshConfig } = useAuth()
  const toast = useToast()
  const [profile, setProfile] = useState({
    name: teacher?.name || '',
    school_name: teacher?.school_name || '',
    subject: teacher?.subject || '',
    preferred_language: teacher?.preferred_language || 'English',
    default_tone: teacher?.default_tone || 'warm',
  })
  const [saving, setSaving] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    if (teacher) {
      setProfile({
        name: teacher.name || '',
        school_name: teacher.school_name || '',
        subject: teacher.subject || '',
        preferred_language: teacher.preferred_language || 'English',
        default_tone: teacher.default_tone || 'warm',
      })
    }
  }, [teacher])

  async function save(event) {
    event.preventDefault()
    setSaving(true)
    try {
      await api.updateMe(profile)
      await refreshConfig()
      toast.success('Settings saved.')
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function refresh() {
    setRefreshing(true)
    try {
      await refreshConfig()
      toast.success('Configuration reloaded.')
    } finally {
      setRefreshing(false)
    }
  }

  async function handleReset() {
    if (!window.confirm('Reset all demo data? Any generated work will be discarded.')) return
    await resetDemo()
    await refreshConfig()
    toast.success('Demo data reset. Generated work has been cleared.')
    window.location.reload()
  }

  const llm = config?.llm
  const messaging = config?.messaging
  const estimates = config?.time_saved_estimates

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-ink-800">Settings</h1>
        <p className="mt-1 text-sm text-ink-500">
          Your defaults, and what the backend is currently configured to do.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* Profile */}
        <Card>
          <CardHeader title="Your details" subtitle="Used as defaults by every agent." />
          <form onSubmit={save} className="card-pad space-y-4">
            <Field label="Name">
              <input
                className="input"
                value={profile.name}
                onChange={(e) => setProfile({ ...profile, name: e.target.value })}
              />
            </Field>
            <Field label="School">
              <input
                className="input"
                value={profile.school_name}
                onChange={(e) => setProfile({ ...profile, school_name: e.target.value })}
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Subject">
                <input
                  className="input"
                  value={profile.subject}
                  onChange={(e) => setProfile({ ...profile, subject: e.target.value })}
                />
              </Field>
              <Field label="Default language">
                <select
                  className="input"
                  value={profile.preferred_language}
                  onChange={(e) =>
                    setProfile({ ...profile, preferred_language: e.target.value })
                  }
                >
                  <option>English</option>
                  <option>Hindi</option>
                </select>
              </Field>
            </div>
            <Field label="Default tone for parent messages">
              <select
                className="input"
                value={profile.default_tone}
                onChange={(e) => setProfile({ ...profile, default_tone: e.target.value })}
              >
                <option value="warm">Warm</option>
                <option value="formal">Formal</option>
              </select>
            </Field>
            <button className="btn-primary" disabled={saving}>
              {saving ? <Spinner size={15} /> : <Save size={15} />}
              {saving ? 'Saving…' : 'Save settings'}
            </button>
          </form>
        </Card>

        {/* LLM */}
        <Card>
          <CardHeader
            title="AI provider"
            subtitle="Everything runs in this browser tab — no API key, no server."
            icon={Cpu}
            actions={
              <button className="btn-ghost btn-sm" onClick={refresh} disabled={refreshing}>
                {refreshing ? <Spinner size={13} /> : <RefreshCw size={13} />}
                Refresh
              </button>
            }
          />
          <div className="card-pad space-y-3.5">
            {!llm ? (
              <p className="text-sm text-ink-400">Loading configuration…</p>
            ) : (
              <>
                <dl className="divide-y divide-ink-200/70 rounded-lg border border-ink-200/70">
                  <Row label="Provider" value={llm.provider} />
                  <Row label="Agents" value={llm.model} />
                  <Row label="Where they run" value={llm.base_url} mono />
                  <Row label="Network calls" value="None" tone="good" />
                  <Row label="Data location" value="Your browser (localStorage)" tone="good" />
                </dl>

                <div className="rounded-lg border border-ink-200/70 bg-ink-200/30 p-3.5">
                  <p className="text-xs font-semibold uppercase tracking-wide text-ink-400">
                    How this build works
                  </p>
                  <p className="mt-1 text-sm text-ink-600">
                    The four agents run in JavaScript inside this page. Lesson minutes, grading
                    confidence, the 120-word limit and the approval gate are all enforced in code,
                    so every rule behaves identically whether or not a model is attached.
                  </p>
                  <p className="mt-2 text-xs text-ink-400">
                    Nothing you type leaves this device. To return to the seeded demo data, use{' '}
                    <button
                      type="button"
                      onClick={handleReset}
                      className="font-semibold text-brand-300 underline-offset-2 hover:underline"
                    >
                      Reset demo data
                    </button>
                    .
                  </p>
                </div>
              </>
            )}
          </div>
        </Card>

        {/* Messaging */}
        <Card>
          <CardHeader
            title="Parent messaging"
            subtitle="Simulated — nothing ever leaves this device."
            icon={Mail}
          />
          <div className="card-pad space-y-3.5">
            {!messaging ? (
              <p className="text-sm text-ink-400">Loading…</p>
            ) : (
              <>
                <dl className="divide-y divide-ink-200/70 rounded-lg border border-ink-200/70">
                  <Row label="Mode" value={messaging.mode} mono />
                  <Row label="Real delivery" value="None — simulated only" tone="good" />
                  <Row label="Word limit (WhatsApp)" value="120 words" />
                  <Row
                    label="Student data shared"
                    value="Never — agents see anonymous IDs"
                    tone="good"
                  />
                </dl>
                <div className="flex items-start gap-2.5 rounded-lg border border-brand-400/25 bg-brand-50/40 p-3.5">
                  <ShieldCheck size={16} className="mt-0.5 shrink-0 text-brand-300" />
                  <p className="text-xs text-brand-300">
                    <strong>Approval is enforced in code.</strong> Sending only accepts messages
                    whose status is <code>approved</code>, and editing an approved message revokes
                    that approval so it must be read again.
                  </p>
                </div>
              </>
            )}
          </div>
        </Card>

        {/* Estimates & limits */}
        <Card>
          <CardHeader
            title="Time-saved estimates"
            subtitle="Used for the dashboard metrics."
            icon={Clock}
          />
          <div className="card-pad">
            {!estimates ? (
              <p className="text-sm text-ink-400">Loading…</p>
            ) : (
              <dl className="divide-y divide-ink-200/70 rounded-lg border border-ink-200/70">
                <Row label="Lesson plan" value={`${estimates.lesson_plan_minutes} min`} />
                <Row
                  label="Grading"
                  value={`${estimates.grading_minutes_per_paper} min per paper`}
                />
                <Row
                  label="Differentiated worksheets"
                  value={`${estimates.differentiation_minutes} min`}
                />
                <Row
                  label="Parent message"
                  value={`${estimates.parent_message_minutes} min each`}
                />
              </dl>
            )}
            <p className="mt-3 text-xs text-ink-400">
              These are the published estimates the dashboard reports against, kept in
              <code className="mx-1 rounded bg-ink-200/70 px-1 py-0.5 text-ink-600">src/api/local.js</code>
              so a class can see where the time went.
            </p>
          </div>
        </Card>
      </div>
    </div>
  )
}

function Row({ label, value, mono, tone }) {
  const toneClass =
    tone === 'good' ? 'text-brand-700' : tone === 'warn' ? 'text-amber-600' : 'text-ink-700'
  return (
    <div className="flex items-center justify-between gap-3 px-3.5 py-2.5">
      <dt className="text-sm text-ink-500">{label}</dt>
      <dd
        className={`text-sm font-medium ${toneClass} ${mono ? 'font-mono text-xs' : ''}`}
      >
        {value}
      </dd>
    </div>
  )
}