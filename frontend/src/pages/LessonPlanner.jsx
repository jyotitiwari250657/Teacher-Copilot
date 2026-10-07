import { useEffect, useState } from 'react'
import {
  BookOpen,
  Download,
  CheckCircle2,
  RefreshCw,
  Clock,
  ChevronDown,
  AlertTriangle,
  FileText,
} from 'lucide-react'
import { AiGlyph } from '../components/brand'
import { api, documentFor } from '../api/client'
import { saveDocument } from '../lib/exportDoc'
import { useToast } from '../components/Toast'
import {
  Card,
  CardHeader,
  Field,
  ErrorBanner,
  AiLabel,
  DraftBadge,
  LoadingPanel,
  EmptyState,
  SkeletonCard,
  T,
} from '../components/ui'

const PHASE_COLORS = {
  hook: 'bg-sky-100 text-sky-800 border-sky-200',
  explain: 'bg-brand-100 text-brand-800 border-brand-200',
  activity: 'bg-accent-100 text-accent-700 border-accent-200',
  practice: 'bg-purple-100 text-purple-800 border-purple-200',
  assessment: 'bg-amber-100 text-amber-800 border-amber-200',
  recap: 'bg-ink-100 text-ink-700 border-ink-200',
}

export default function LessonPlanner() {
  const toast = useToast()
  const [classes, setClasses] = useState([])
  const [form, setForm] = useState({
    subject: 'Science',
    class_id: '',
    topic: 'Photosynthesis',
    duration_minutes: 40,
    board: 'CBSE',
    language: 'English',
    learning_objectives: '',
    class_level_notes: '',
  })
  const [plan, setPlan] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState(null)
  const [exporting, setExporting] = useState(null)

  useEffect(() => {
    api.classes().then(setClasses).catch(() => setClasses([]))
  }, [])

  async function generate(event) {
    event.preventDefault()
    setError(null)
    setGenerating(true)
    try {
      const result = await api.generateLesson({
        subject: form.subject,
        class_id: form.class_id ? Number(form.class_id) : null,
        topic: form.topic,
        duration_minutes: Number(form.duration_minutes),
        board: form.board,
        language: form.language,
        learning_objectives: form.learning_objectives
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean),
        class_level_notes: form.class_level_notes,
      })
      setPlan(result)
      toast.success('Lesson plan generated. Review it before you teach.')
    } catch (err) {
      setError(err)
    } finally {
      setGenerating(false)
    }
  }

  async function regenerate() {
    setError(null)
    setGenerating(true)
    try {
      const result = await api.regenerateLesson(plan.id)
      setPlan(result)
      toast.success('Lesson plan regenerated.')
    } catch (err) {
      setError(err)
    } finally {
      setGenerating(false)
    }
  }

  async function approve() {
    try {
      const result = await api.approveLesson(plan.id)
      setPlan(result)
      toast.success('Lesson plan approved.')
    } catch (err) {
      toast.error(err.message)
    }
  }

  async function saveEdits(nextContent) {
    try {
      const result = await api.updateLesson(plan.id, { content: nextContent })
      setPlan(result)
      toast.success('Changes saved.')
    } catch (err) {
      toast.error(err.message)
    }
  }

  function handleExport(format) {
    if (!plan) return
    setExporting(format)
    try {
      saveDocument(documentFor({ plan }), format)
      toast.success(
        format === 'pdf'
          ? 'Print dialog opened — choose "Save as PDF".'
          : 'Word document downloaded.',
      )
    } catch (err) {
      toast.error(err.message)
    } finally {
      setExporting(null)
    }
  }

  const content = plan?.content || {}
  const flowTotal = (content.lesson_flow || []).reduce(
    (sum, item) => sum + Number(item.minutes || 0),
    0,
  )

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-ink-800">Lesson Planner</h1>
        <p className="mt-1 text-sm text-ink-500">
          A full plan, timed to the minute, built for a low-resource classroom.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-5">
        {/* Form */}
        <Card className="lg:col-span-2">
          <CardHeader title="Plan a lesson" icon={BookOpen} />
          <form onSubmit={generate} className="card-pad space-y-4">
            <Field label="Class">
              <select
                className="input"
                value={form.class_id}
                onChange={(e) => setForm({ ...form, class_id: e.target.value })}
              >
                <option value="">No class (standalone)</option>
                {classes.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} · Grade {item.grade || '—'}
                  </option>
                ))}
              </select>
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Subject" required>
                <input
                  className="input"
                  value={form.subject}
                  onChange={(e) => setForm({ ...form, subject: e.target.value })}
                  required
                />
              </Field>
              <Field label="Board">
                <select
                  className="input"
                  value={form.board}
                  onChange={(e) => setForm({ ...form, board: e.target.value })}
                >
                  {['CBSE', 'ICSE', 'State', 'Other'].map((board) => (
                    <option key={board}>{board}</option>
                  ))}
                </select>
              </Field>
            </div>

            <Field label="Topic" required>
              <input
                className="input"
                value={form.topic}
                onChange={(e) => setForm({ ...form, topic: e.target.value })}
                placeholder="Photosynthesis"
                required
              />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Duration (minutes)" required>
                <input
                  className="input"
                  type="number"
                  min="5"
                  max="300"
                  value={form.duration_minutes}
                  onChange={(e) => setForm({ ...form, duration_minutes: e.target.value })}
                />
              </Field>
              <Field label="Output language">
                <select
                  className="input"
                  value={form.language}
                  onChange={(e) => setForm({ ...form, language: e.target.value })}
                >
                  <option>English</option>
                  <option>Hindi</option>
                </select>
              </Field>
            </div>

            <Field
              label="Learning objectives"
              hint="Optional — one per line. The agent adds its own if you leave this blank."
            >
              <textarea
                className="input min-h-[72px] resize-y"
                value={form.learning_objectives}
                onChange={(e) => setForm({ ...form, learning_objectives: e.target.value })}
                placeholder={'Define photosynthesis\nExplain the role of chlorophyll'}
              />
            </Field>

            <Field
              label="Class level notes"
              hint="Optional — the agent adapts the pace and scaffolds for this class."
            >
              <textarea
                className="input min-h-[72px] resize-y"
                value={form.class_level_notes}
                onChange={(e) => setForm({ ...form, class_level_notes: e.target.value })}
                placeholder="Two students have just joined; keep the pace steady."
              />
            </Field>

            {error && <ErrorBanner error={error} />}

            <button type="submit" className="btn-primary w-full" disabled={generating}>
              {generating ? (
                'Agent is writing…'
              ) : (
                <>
                  <AiGlyph size={16} />
                  Generate lesson plan
                </>
              )}
            </button>
          </form>
        </Card>

        {/* Result */}
        <div className="space-y-5 lg:col-span-3">
          {generating ? (
            <Card>
              <LoadingPanel
                label="Lesson Planner agent is working…"
                hint="Building the flow and budgeting every minute of the period."
              />
              <div className="space-y-3 px-5 pb-5">
                <SkeletonCard lines={3} />
              </div>
            </Card>
          ) : !plan ? (
            <Card>
              <EmptyState
                icon={FileText}
                title="No lesson plan yet"
                description="Fill in the topic and duration on the left, then click Generate. The agent will build a plan you can teach from directly."
              />
            </Card>
          ) : (
            <>
              <Card>
                <CardHeader
                  title={content.title || plan.title}
                  subtitle={`${plan.subject} · Class ${plan.grade || plan.class_id || '—'} · ${plan.board} · ${plan.language}`}
                  icon={BookOpen}
                  actions={
                    <>
                      <DraftBadge status={plan.status} />
                    </>
                  }
                />
                <div className="flex flex-wrap items-center gap-2 border-b border-ink-200/70 px-5 py-3">
                  <button className="btn-secondary btn-sm" onClick={regenerate} disabled={generating}>
                    <RefreshCw size={14} />
                    Regenerate
                  </button>
                  {plan.status !== 'approved' && (
                    <button className="btn-primary btn-sm" onClick={approve}>
                      <CheckCircle2 size={14} />
                      Approve
                    </button>
                  )}
                  <span className="mx-1 hidden h-5 w-px bg-ink-200 sm:block" />
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => handleExport('pdf')}
                    disabled={exporting !== null}
                  >
                    <Download size={14} />
                    {exporting === 'pdf' ? '…' : 'PDF'}
                  </button>
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => handleExport('docx')}
                    disabled={exporting !== null}
                  >
                    <Download size={14} />
                    {exporting === 'docx' ? '…' : 'DOCX'}
                  </button>
                  <div className="ml-auto">
                    <AiLabel />
                  </div>
                </div>

                <div className="card-pad space-y-6">
                  {/* Objectives */}
                  <Section title="Learning objectives" open>
                    <ul className="space-y-1.5">
                      {(content.learning_objectives || []).map((objective, index) => (
                        <li key={index} className="flex gap-2 text-sm text-ink-700">
                          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />
                          <T>{objective}</T>
                        </li>
                      ))}
                    </ul>
                  </Section>

                  {/* Lesson flow */}
                  <Section
                    title="Lesson flow"
                    subtitle={
                      <span
                        className={
                          flowTotal === Number(plan.duration_minutes)
                            ? 'text-brand-700'
                            : 'text-red-600'
                        }
                      >
                        <Clock size={12} className="mr-1 inline" />
                        {flowTotal} of {plan.duration_minutes} minutes
                      </span>
                    }
                    open
                  >
                    {flowTotal !== Number(plan.duration_minutes) && (
                      <div className="mb-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                        <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                        The phases do not add up to the requested duration. Use Regenerate.
                      </div>
                    )}
                    <ol className="space-y-2.5">
                      {(content.lesson_flow || []).map((item, index) => (
                        <li key={index} className="rounded-lg border border-ink-200 p-3.5">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <span
                                className={`chip capitalize ${
                                  PHASE_COLORS[item.phase] || PHASE_COLORS.recap
                                }`}
                              >
                                {item.phase}
                              </span>
                              <span className="text-sm font-semibold tabular-nums text-ink-700">
                                {item.minutes} min
                              </span>
                            </div>
                            <span className="text-[11px] text-ink-400">
                              Step {index + 1} of {content.lesson_flow.length}
                            </span>
                          </div>
                          <div className="mt-2.5 grid gap-3 sm:grid-cols-2">
                            <div>
                              <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
                                Teacher
                              </p>
                              <ul className="mt-1 space-y-0.5">
                                {(item.teacher_actions || []).map((action, i) => (
                                  <li key={i} className="text-sm text-ink-700">
                                    <T>• {action}</T>
                                  </li>
                                ))}
                              </ul>
                            </div>
                            <div>
                              <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
                                Students
                              </p>
                              <ul className="mt-1 space-y-0.5">
                                {(item.student_actions || []).map((action, i) => (
                                  <li key={i} className="text-sm text-ink-700">
                                    <T>• {action}</T>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          </div>
                        </li>
                      ))}
                    </ol>
                  </Section>

                  {/* Materials */}
                  <Section title="Materials" count={(content.materials || []).length}>
                    <ul className="space-y-1.5">
                      {(content.materials || []).map((item, index) => (
                        <li key={index} className="flex gap-2 text-sm text-ink-700">
                          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ink-300" />
                          <T>{item}</T>
                        </li>
                      ))}
                    </ul>
                    <p className="mt-3 rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-600">
                      Every activity here is designed to work with a chalkboard and paper — no
                      projector or internet required.
                    </p>
                  </Section>

                  {/* Vocabulary */}
                  <Section title="Key vocabulary" count={(content.key_vocabulary || []).length}>
                    <ul className="space-y-1.5">
                      {(content.key_vocabulary || []).map((item, index) => (
                        <li key={index} className="text-sm text-ink-700">
                          <T>{item}</T>
                        </li>
                      ))}
                    </ul>
                  </Section>

                  {/* Misconceptions */}
                  <Section
                    title="Common misconceptions"
                    count={(content.common_misconceptions || []).length}
                  >
                    <ul className="space-y-2">
                      {(content.common_misconceptions || []).map((item, index) => (
                        <li
                          key={index}
                          className="flex gap-2 rounded-lg bg-amber-50/70 px-3 py-2 text-sm text-amber-900"
                        >
                          <AlertTriangle size={15} className="mt-0.5 shrink-0 text-amber-600" />
                          <T>{item}</T>
                        </li>
                      ))}
                    </ul>
                  </Section>

                  {/* Homework */}
                  <Section title="Homework" subtitle="Editable — changes save on blur">
                    <textarea
                      className="input min-h-[70px] resize-y"
                      defaultValue={content.homework || ''}
                      onBlur={(event) => saveEdits({ ...content, homework: event.target.value })}
                    />
                  </Section>

                  {/* Exit ticket */}
                  <Section title="Exit ticket" subtitle="Exactly 3 questions">
                    <ul className="space-y-1.5">
                      {(content.exit_ticket || []).map((question, index) => (
                        <li key={index} className="flex gap-2 text-sm text-ink-700">
                          <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-brand-100 text-[11px] font-bold text-brand-700">
                            {index + 1}
                          </span>
                          <T>{question}</T>
                        </li>
                      ))}
                    </ul>
                  </Section>

                  {/* Rubric */}
                  <Section title="Assessment rubric" count={(content.assessment_rubric || []).length}>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead className="border-b border-ink-200 text-left text-xs uppercase tracking-wide text-ink-500">
                          <tr>
                            <th className="py-2 pr-3 font-semibold">Criterion</th>
                            <th className="py-2 pr-3 font-semibold">Description</th>
                            <th className="py-2 text-right font-semibold">Marks</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-ink-200">
                          {(content.assessment_rubric || []).map((row, index) => (
                            <tr key={index}>
                              <td className="py-2 pr-3 font-medium text-ink-800">
                                {row.criterion}
                              </td>
                              <td className="py-2 pr-3 text-ink-600">
                                <T>{row.description}</T>
                              </td>
                              <td className="py-2 text-right tabular-nums text-ink-700">
                                {row.marks}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Section>
                </div>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function Section({ title, subtitle, count, children, open = false }) {
  const [expanded, setExpanded] = useState(open)
  return (
    <div className="border-t border-ink-200/70 pt-4 first:border-0 first:pt-0">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-3 text-left"
      >
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-ink-800">{title}</span>
          {count !== undefined && (
            <span className="rounded-full bg-ink-100 px-1.5 py-0.5 text-[10px] font-semibold text-ink-600">
              {count}
            </span>
          )}
          {subtitle && <span className="text-xs font-normal text-ink-500">{subtitle}</span>}
        </span>
        <ChevronDown
          size={16}
          className={`shrink-0 text-ink-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
        />
      </button>
      {expanded && <div className="mt-3">{children}</div>}
    </div>
  )
}