import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Workflow as WorkflowIcon,
  Play,
  RotateCcw,
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  Inbox,
  Terminal,
  ChevronRight,
  AlertTriangle,
  SkipForward,
} from 'lucide-react'
import { AiGlyph } from '../components/brand'
import { api } from '../api/client'
import { useToast } from '../components/Toast'
import {
  Card,
  CardHeader,
  Field,
  ErrorBanner,
  LoadingPanel,
  EmptyState,
  AiLabel,
} from '../components/ui'

const STEP_ICON = {
  done: CheckCircle2,
  needs_review: AlertTriangle,
  failed: XCircle,
  running: Loader2,
  pending: SkipForward,
  skipped: SkipForward,
}

const STEP_TONE = {
  done: 'text-emerald-600 bg-emerald-50 border-emerald-200',
  needs_review: 'text-amber-600 bg-amber-50 border-amber-200',
  failed: 'text-red-600 bg-red-50 border-red-200',
  running: 'text-brand-600 bg-brand-50 border-brand-300',
  pending: 'text-ink-400 bg-ink-50 border-ink-200',
  skipped: 'text-ink-400 bg-ink-50 border-ink-200',
}

const INBOX_TONE = {
  parent_message: 'bg-sky-100 text-sky-700',
  grade: 'bg-accent-100 text-accent-700',
  lesson_plan: 'bg-brand-100 text-brand-700',
  material: 'bg-purple-100 text-purple-700',
}

export default function Workflow() {
  const toast = useToast()
  const pollRef = useRef(null)

  const [classes, setClasses] = useState([])
  const [form, setForm] = useState({
    class_id: '',
    topic: 'Photosynthesis',
    subject: 'Science',
    language: 'English',
    duration_minutes: 40,
    board: 'CBSE',
    strictness: 'standard',
    tone: 'warm',
    channel: 'whatsapp',
  })
  const [definitions, setDefinitions] = useState([])
  const [run, setRun] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const [rerunning, setRerunning] = useState(null)
  const [showLogs, setShowLogs] = useState(true)

  useEffect(() => {
    api.classes()
      .then((list) => {
        setClasses(list)
        if (list.length > 0) setForm((f) => ({ ...f, class_id: String(list[0].id) }))
      })
      .catch(() => setClasses([]))
    api.stepDefinitions().then(setDefinitions).catch(() => setDefinitions([]))
  }, [])

  useEffect(() => () => clearInterval(pollRef.current), [])

  // While a run is live, poll for status so the timeline animates.
  const startPolling = useCallback((runId) => {
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const snapshot = await api.workflowStatus(runId)
        setRun((current) => (current ? { ...current, ...snapshot } : current))
        if (!['running', 'pending'].includes(snapshot.status)) {
          clearInterval(pollRef.current)
          try {
            const inbox = await api.workflowInbox(runId)
            setRun((current) => (current ? { ...current, inbox } : current))
          } catch {
            /* inbox is a nice-to-have */
          }
        }
      } catch {
        clearInterval(pollRef.current)
      }
    }, 900)
  }, [])

  async function startRun(event) {
    event.preventDefault()
    setError(null)
    setRunning(true)
    setRun(null)
    try {
      // Show the pipeline immediately so the timeline is not blank while we wait.
      setRun({ status: 'running', steps: [], logs: [], inbox: null, topic: form.topic })
      const result = await api.runWorkflow({
        class_id: Number(form.class_id),
        topic: form.topic,
        subject: form.subject,
        language: form.language,
        duration_minutes: Number(form.duration_minutes),
        board: form.board,
        strictness: form.strictness,
        tone: form.tone,
        channel: form.channel,
        use_sample_answers: true,
      })
      setRun(result)
      toast.success('Workflow finished. Review everything in the approval inbox.')
    } catch (err) {
      setError(err)
    } finally {
      setRunning(false)
      clearInterval(pollRef.current)
    }
  }

  async function rerun(stepKey) {
    if (!run?.id) return
    setRerunning(stepKey)
    setError(null)
    try {
      const result = await api.rerunStep(run.id, stepKey)
      setRun(result)
      toast.success(`Step re-run: ${stepKey}`)
    } catch (err) {
      setError(err)
      toast.error(err.message)
    } finally {
      setRerunning(null)
    }
  }

  const steps = run?.steps?.length ? run.steps : definitions.map((d) => ({ ...d, status: 'pending' }))

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-ink-800">Weekly Workflow</h1>
        <p className="mt-1 text-sm text-ink-500">
          One click runs all four agents in sequence and fills your approval inbox.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-4">
        {/* Config */}
        <Card className="lg:col-span-1">
          <CardHeader title="Run the pipeline" icon={WorkflowIcon} />
          <form onSubmit={startRun} className="card-pad space-y-3.5">
            <Field label="Class" required>
              <select
                className="input"
                value={form.class_id}
                onChange={(e) => setForm({ ...form, class_id: e.target.value })}
              >
                {classes.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Topic" required>
              <input
                className="input"
                value={form.topic}
                onChange={(e) => setForm({ ...form, topic: e.target.value })}
              />
            </Field>
            <div className="grid grid-cols-2 gap-2.5">
              <Field label="Duration">
                <input
                  className="input"
                  type="number"
                  min="5"
                  max="300"
                  value={form.duration_minutes}
                  onChange={(e) => setForm({ ...form, duration_minutes: e.target.value })}
                />
              </Field>
              <Field label="Language">
                <select
                  className="input"
                  value={form.language}
                  onChange={(e) => setForm({ ...form, language: e.target.value })}
                >
                  <option>English</option>
                  <option>Hindi</option>
                </select>
              </Field>
              <Field label="Grading">
                <select
                  className="input"
                  value={form.strictness}
                  onChange={(e) => setForm({ ...form, strictness: e.target.value })}
                >
                  <option value="lenient">Lenient</option>
                  <option value="standard">Standard</option>
                  <option value="strict">Strict</option>
                </select>
              </Field>
              <Field label="Send via">
                <select
                  className="input"
                  value={form.channel}
                  onChange={(e) => setForm({ ...form, channel: e.target.value })}
                >
                  <option value="whatsapp">WhatsApp</option>
                  <option value="email">Email</option>
                </select>
              </Field>
            </div>

            {error && <ErrorBanner error={error} />}

            <button className="btn-primary w-full" disabled={running || !form.class_id}>
              {running ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              {running ? 'Agents are working…' : 'Run weekly workflow'}
            </button>
            <p className="text-xs text-ink-500">
              Uses the seeded sample answers, so you can see the whole pipeline without typing
              anything.
            </p>
          </form>
        </Card>

        {/* Timeline + inbox */}
        <div className="space-y-5 lg:col-span-3">
          <Card>
            <CardHeader
              title="Agent timeline"
              subtitle={run?.topic ? `Topic: ${run.topic}` : 'The five steps that run in order'}
              icon={WorkflowIcon}
              actions={
                run?.status && (
                  <span
                    className={`chip ${
                      run.status === 'done'
                        ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                        : run.status === 'running'
                          ? 'border-brand-200 bg-brand-50 text-brand-800'
                          : 'border-amber-200 bg-amber-50 text-amber-800'
                    }`}
                  >
                    {run.status.replace(/_/g, ' ')}
                  </span>
                )
              }
            />
            <div className="card-pad pt-4">
              {running && !run?.steps?.length ? (
                <LoadingPanel
                  label="Running the pipeline…"
                  hint="Four agents working in sequence. This usually takes a few seconds."
                />
              ) : (
                <ol className="space-y-2">
                  {steps.map((step, index) => {
                    const Icon = STEP_ICON[step.status] || SkipForward
                    const tone = STEP_TONE[step.status] || STEP_TONE.pending
                    const isLast = index === steps.length - 1
                    return (
                      <li key={step.step_key} className="relative">
                        <div className="flex gap-3">
                          {/* Rail */}
                          <div className="flex flex-col items-center">
                            <span
                              className={`grid h-9 w-9 shrink-0 place-items-center rounded-full border-2 ${tone}`}
                            >
                              <Icon
                                size={16}
                                className={step.status === 'running' ? 'animate-spin' : ''}
                              />
                            </span>
                            {!isLast && (
                              <span className="my-1 w-px flex-1 bg-ink-200" />
                            )}
                          </div>

                          {/* Body */}
                          <div className="min-w-0 flex-1 pb-4">
                            <div className="flex flex-wrap items-start justify-between gap-2">
                              <div className="min-w-0">
                                <p className="text-sm font-semibold text-ink-800">
                                  <span className="mr-1.5 text-ink-400">{step.step_number || index + 1}.</span>
                                  {step.title}
                                </p>
                                <p className="text-xs text-ink-500">
                                  agent: <code className="rounded bg-ink-100 px-1">{step.agent}</code>
                                  {step.duration_ms > 0 && (
                                    <>
                                      {' · '}
                                      <Clock size={10} className="mr-0.5 inline" />
                                      {(step.duration_ms / 1000).toFixed(2)}s
                                    </>
                                  )}
                                </p>
                              </div>
                              {run?.id && (
                                <button
                                  className="btn-ghost btn-sm"
                                  onClick={() => rerun(step.step_key)}
                                  disabled={rerunning === step.step_key || running}
                                  title="Re-run just this step"
                                >
                                  {rerunning === step.step_key ? (
                                    <Loader2 size={13} className="animate-spin" />
                                  ) : (
                                    <RotateCcw size={13} />
                                  )}
                                  Re-run
                                </button>
                              )}
                            </div>
                            {step.detail && (
                              <p className="mt-1 rounded bg-ink-50 px-3 py-1.5 text-xs text-ink-600">
                                {step.detail}
                              </p>
                            )}
                          </div>
                        </div>
                      </li>
                    )
                  })}
                </ol>
              )}
            </div>
          </Card>

          {/* Approval inbox */}
          {run?.inbox && (
            <Card>
              <CardHeader
                title="Approval inbox"
                subtitle="Everything this run produced that still needs you."
                icon={Inbox}
                actions={
                  <span className="chip border-accent-200 bg-accent-50 text-accent-700">
                    {run.inbox.count} item{run.inbox.count === 1 ? '' : 's'}
                  </span>
                }
              />
              <div className="card-pad pt-4">
                {run.inbox.count === 0 ? (
                  <EmptyState
                    icon={CheckCircle2}
                    title="Nothing waiting"
                    description="Every output of this run has been dealt with."
                  />
                ) : (
                  <ul className="space-y-2">
                    {run.inbox.items.map((item, index) => (
                      <li
                        key={`${item.kind}-${item.id}-${index}`}
                        className="flex flex-wrap items-start gap-3 rounded-lg border border-ink-200 p-3.5"
                      >
                        <span
                          className={`chip shrink-0 ${INBOX_TONE[item.kind] || 'bg-ink-100 text-ink-700'}`}
                        >
                          {item.kind.replace(/_/g, ' ')}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-ink-800">{item.title}</p>
                          <p className="text-xs text-ink-500">{item.subtitle}</p>
                          {item.preview && (
                            <p className="mt-1 line-clamp-2 text-xs text-ink-500">{item.preview}</p>
                          )}
                          {item.needs_review && (item.reasons || []).length > 0 && (
                            <p className="mt-1 text-xs font-medium text-amber-700">
                              ⚠ {item.reasons[0]}
                            </p>
                          )}
                        </div>
                        <Link
                          to={
                            item.kind === 'parent_message'
                              ? '/parent-updates'
                              : item.kind === 'grade'
                                ? '/grading'
                                : item.kind === 'material'
                                  ? '/differentiation'
                                  : '/lessons'
                          }
                          className="btn-ghost btn-sm shrink-0"
                        >
                          Review <ChevronRight size={13} />
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </Card>
          )}

          {/* Agent logs */}
          {run?.logs?.length > 0 && (
            <Card>
              <div className="px-5 pt-4">
                <button
                  className="flex w-full items-center justify-between"
                  onClick={() => setShowLogs((v) => !v)}
                >
                  <span className="flex items-center gap-2 text-sm font-semibold text-ink-800">
                    <Terminal size={15} className="text-ink-400" />
                    Agent log ({run.logs.length})
                  </span>
                  <ChevronRight
                    size={15}
                    className={`text-ink-400 transition-transform ${showLogs ? 'rotate-90' : ''}`}
                  />
                </button>
              </div>
              {showLogs && (
                <div className="card-pad pt-3">
                  <div className="max-h-72 space-y-1.5 overflow-y-auto rounded-lg bg-ink-900 p-3.5 font-mono text-[11px] leading-relaxed">
                    {run.logs.map((log) => (
                      <div
                        key={log.id}
                        className={
                          log.success ? 'text-emerald-300' : 'text-red-400'
                        }
                      >
                        <span className="text-ink-500">[{new Date(log.created_at).toLocaleTimeString()}]</span>{' '}
                        <span className="text-brand-300">{log.agent}</span>{' '}
                        <span className="text-ink-400">
                          ({log.duration_ms}ms{log.tokens ? `, ${log.tokens} tokens` : ''})
                        </span>{' '}
                        <span className="text-ink-300">
                          {log.success ? log.output_summary?.slice(0, 120) : log.error?.slice(0, 120)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          )}

          {!run && !running && (
            <Card>
              <EmptyState
                icon={AiGlyph}
                title="Ready when you are"
                description="Press Run weekly workflow. The Lesson Planner writes the plan, the Differentiation agent builds three levels, the Grader marks every script, students are regrouped from those marks, and the Parent Update agent drafts a message for each family."
              />
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}