import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BookOpen,
  ClipboardCheck,
  MessageSquare,
  Layers,
  Clock,
  Users,
  TrendingUp,
  Inbox,
  ArrowRight,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { api } from '../api/client'
import { AiGlyph } from '../components/brand'
import { useAuth } from '../context/AuthContext'
import {
  Card,
  CardHeader,
  SkeletonCard,
  ErrorBanner,
  Stat,
  EmptyState,
} from '../components/ui'

// Four steps of one workflow, so four rungs of the same steel scale.
const TASK_COLORS = {
  lesson_plan: '#e8edf3',
  grading: '#c2cbd6',
  differentiation: '#98a3b0',
  parent_message: '#79838f',
}

function minutesToHours(minutes) {
  return Math.round((minutes / 60) * 10) / 10
}

export default function Dashboard() {
  const { teacher } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await api.dashboard())
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const firstName = (teacher?.name || '').split(' ')[0]

  if (loading) {
    return (
      <div className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="card card-pad">
              <div className="skeleton h-3 w-24" />
              <div className="skeleton mt-3 h-7 w-16" />
            </div>
          ))}
        </div>
        <SkeletonCard lines={6} />
      </div>
    )
  }

  if (error) return <ErrorBanner error={error} onRetry={load} />
  if (!data) return null

  const weekly = (data.weekly_time_saved || []).map((point) => ({
    ...point,
    hours: minutesToHours(point.minutes),
  }))

  const taskBreakdown = Object.entries(data.time_saved_by_task || {})
    .map(([task, minutes]) => ({
      task,
      label: task.replace(/_/g, ' '),
      minutes,
      hours: minutesToHours(minutes),
    }))
    .sort((a, b) => b.minutes - a.minutes)

  return (
    <div className="space-y-6">
      {/* Greeting */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-ink-800">
            {firstName ? `Hello, ${firstName}` : 'Welcome'}
          </h1>
          <p className="mt-1 text-sm text-ink-500">
            Here is how much teaching time TeacherCopilot has given back to you.
          </p>
        </div>
        <Link to="/workflow" className="btn-primary">
          <AiGlyph size={16} />
          Run Weekly Workflow
        </Link>
      </div>

      {/* Headline stats */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Time saved this week"
          value={data.time_saved_this_week_human || '0m'}
          hint={`${data.time_saved_this_week_minutes || 0} minutes · all time ${data.time_saved_all_time_human || '0m'}`}
          icon={Clock}
          tone="brand"
        />
        <Stat
          label="Lesson plans"
          value={data.lesson_plans_created}
          hint={`${data.lesson_plans_approved || 0} approved`}
          icon={BookOpen}
          tone="violet"
        />
        <Stat
          label="Papers graded"
          value={data.papers_graded}
          hint={`${data.students_graded} student scripts approved`}
          icon={ClipboardCheck}
          tone="accent"
        />
        <Stat
          label="Parent messages sent"
          value={data.messages_sent}
          hint={`${data.messages_pending} waiting for your approval`}
          icon={MessageSquare}
          tone="sky"
        />
      </div>

      {/* Approval prompt */}
      {data.approval_inbox_count > 0 && (
        <Card className="border-accent-200 bg-accent-50/60">
          <div className="card-pad flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-start gap-3">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-accent-500 text-white">
                <Inbox size={19} />
              </span>
              <div>
                <p className="text-sm font-semibold text-ink-800">
                  {data.approval_inbox_count} item
                  {data.approval_inbox_count === 1 ? '' : 's'} need your approval
                </p>
                <p className="text-xs text-ink-600">
                  Lesson plans, marks and parent messages stay as drafts until you approve them.
                </p>
              </div>
            </div>
            <Link to="/parent-updates" className="btn-secondary btn-sm">
              Open approval inbox <ArrowRight size={14} />
            </Link>
          </div>
        </Card>
      )}

      <div className="grid gap-5 lg:grid-cols-5">
        {/* Weekly chart */}
        <Card className="lg:col-span-3">
          <CardHeader
            title="Time saved per week"
            subtitle="Estimated from the tasks TeacherCopilot handled for you."
            icon={TrendingUp}
          />
          <div className="card-pad pt-4">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={weekly} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#232830" vertical={false} />
                  <XAxis
                    dataKey="week"
                    tick={{ fontSize: 11, fill: '#79838f' }}
                    axisLine={{ stroke: '#232830' }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: '#79838f' }}
                    axisLine={false}
                    tickLine={false}
                    unit=""
                  />
                  <Tooltip
                    formatter={(value) => [`${value}h`, 'Time saved']}
                    contentStyle={{
                      borderRadius: 8,
                      border: '1px solid #232830',
                      background: '#0b0d10',
                      color: '#e6eaf0',
                      fontSize: 12,
                    }}
                    labelFormatter={(label, payload) =>
                      payload?.[0]?.payload?.is_current ? `${label} (this week)` : label
                    }
                  />
                  <Bar dataKey="hours" radius={[6, 6, 0, 0]}>
                    {weekly.map((entry, index) => (
                      <Cell key={index} fill={entry.is_current ? '#c2cbd6' : '#4a525c'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {taskBreakdown.length > 0 && (
              <div className="mt-5 border-t border-ink-200/70 pt-4">
                <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-ink-500">
                  Where the time went
                </p>
                <div className="space-y-2">
                  {taskBreakdown.map((row) => (
                    <div key={row.task} className="flex items-center gap-3">
                      <span
                        className="h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{ backgroundColor: TASK_COLORS[row.task] || '#98a3b0' }}
                      />
                      <span className="min-w-0 flex-1 truncate text-sm text-ink-600">
                        {row.label.charAt(0).toUpperCase() + row.label.slice(1)}
                      </span>
                      <span className="shrink-0 text-sm font-semibold tabular-nums text-ink-800">
                        {row.hours}h
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Card>

        {/* Class overview */}
        <Card className="lg:col-span-2">
          <CardHeader
            title="Class overview"
            subtitle="Average of your approved marks."
            icon={Users}
            actions={
              <Link to="/classes" className="btn-ghost btn-sm">
                Manage
              </Link>
            }
          />
          <div className="card-pad pt-4">
            {(data.class_overview || []).length === 0 ? (
              <EmptyState
                icon={Users}
                title="No classes yet"
                description="Create a class and add students to see performance here."
                action={
                  <Link to="/classes" className="btn-primary btn-sm">
                    Add a class
                  </Link>
                }
              />
            ) : (
              <div className="space-y-3">
                {data.class_overview.map((row) => (
                  <div key={row.class_id} className="rounded-lg border border-ink-200 p-3.5">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-ink-800">{row.name}</p>
                        <p className="text-xs text-ink-500">
                          {row.student_count} students · {row.subject || 'General'}
                        </p>
                      </div>
                      <span className="shrink-0 text-lg font-bold tabular-nums text-brand-700">
                        {row.average_percentage
                          ? `${Math.round(row.average_percentage)}%`
                          : '—'}
                      </span>
                    </div>
                    <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-ink-200">
                      <div
                        className="h-full rounded-full bg-brand-500 transition-all"
                        style={{ width: `${Math.min(100, row.average_percentage || 0)}%` }}
                      />
                    </div>
                    <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-ink-500">
                      <span>{row.lesson_plans} lesson plans</span>
                      <span>{row.graded_students} graded</span>
                      <span>{row.messages_sent} messages sent</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* Recent activity */}
        <Card>
          <CardHeader title="Recent activity" icon={TrendingUp} />
          <div className="card-pad pt-4">
            {(data.recent_activity || []).length === 0 ? (
              <EmptyState
                title="Nothing yet"
                description="Run the Weekly Workflow to see your activity here."
              />
            ) : (
              <ul className="space-y-2.5">
                {data.recent_activity.map((event, index) => (
                  <li key={index} className="flex items-start gap-3">
                    <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand-400" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-ink-800">{event.label}</p>
                      <p className="truncate text-xs text-ink-500">{event.detail}</p>
                    </div>
                    <span className="shrink-0 text-[11px] text-ink-400">
                      {new Date(event.at).toLocaleDateString(undefined, {
                        month: 'short',
                        day: 'numeric',
                      })}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>

        {/* Quick actions */}
        <Card>
          <CardHeader
            title="What would you like to do?"
            subtitle="Every action produces a draft you can review and edit."
            icon={AiGlyph}
          />
          <div className="card-pad grid gap-2.5 pt-4 sm:grid-cols-2">
            {[
              { to: '/lessons', label: 'Plan a lesson', icon: BookOpen, hint: 'Exact time budgeting' },
              { to: '/grading', label: 'Grade a paper', icon: ClipboardCheck, hint: 'Single, bulk or CSV' },
              { to: '/differentiation', label: 'Differentiate', icon: Layers, hint: 'Three levels at once' },
              { to: '/parent-updates', label: 'Write parent notes', icon: MessageSquare, hint: 'Never sent without you' },
            ].map(({ to, label, icon: Icon, hint }) => (
              <Link
                key={to}
                to={to}
                className="group flex items-center gap-3 rounded-lg border border-ink-200 p-3.5 transition hover:border-brand-300 hover:bg-brand-50/50"
              >
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-ink-100 text-ink-600 transition group-hover:bg-brand-500 group-hover:text-ink-50">
                  <Icon size={17} />
                </span>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-ink-800">{label}</p>
                  <p className="truncate text-xs text-ink-500">{hint}</p>
                </div>
              </Link>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}