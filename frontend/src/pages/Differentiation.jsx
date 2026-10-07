import { useCallback, useEffect, useState } from 'react'
import { Layers, Download, Users, RefreshCw, Info } from 'lucide-react'
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
  LoadingPanel,
  EmptyState,
  Spinner,
  T,
} from '../components/ui'

const LEVELS = [
  {
    key: 'support',
    label: 'Support',
    tagline: 'Below grade level',
    accent: 'border-sky-400/30 bg-sky-50/40',
    header: 'text-sky-300',
    chip: 'bg-sky-500/15 text-sky-200',
  },
  {
    key: 'core',
    label: 'Core',
    tagline: 'On grade level',
    accent: 'border-brand-400/30 bg-brand-50/40',
    header: 'text-brand-300',
    chip: 'bg-brand-500/15 text-brand-300',
  },
  {
    key: 'extension',
    label: 'Extension',
    tagline: 'Advanced',
    accent: 'border-purple-400/30 bg-purple-50/40',
    header: 'text-purple-300',
    chip: 'bg-purple-500/15 text-purple-300',
  },
]

export default function Differentiation() {
  const toast = useToast()
  const [classes, setClasses] = useState([])
  const [lessons, setLessons] = useState([])
  const [form, setForm] = useState({
    class_id: '',
    topic: 'Photosynthesis',
    lesson_plan_id: '',
    language: 'English',
  })
  const [material, setMaterial] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [exporting, setExporting] = useState(null)

  useEffect(() => {
    api.classes()
      .then((list) => {
        setClasses(list)
        if (list.length > 0) setForm((f) => ({ ...f, class_id: String(list[0].id) }))
      })
      .catch(() => setClasses([]))
  }, [])

  useEffect(() => {
    if (!form.class_id) return setLessons([])
    api.lessons(Number(form.class_id)).then(setLessons).catch(() => setLessons([]))
  }, [form.class_id])

  const generate = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.differentiate({
        topic: form.topic,
        class_id: form.class_id ? Number(form.class_id) : null,
        lesson_plan_id: form.lesson_plan_id ? Number(form.lesson_plan_id) : null,
        language: form.language,
      })
      setMaterial(result)
      toast.success('Three-level material created.')
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [form, toast])

  function handleExport(level, format) {
    setExporting(`${level}-${format}`)
    try {
      saveDocument(documentFor({ material, level, includeAnswers: true }), format)
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

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-ink-800">Differentiation</h1>
        <p className="mt-1 text-sm text-ink-500">
          One lesson, three versions — all teaching the same objective, at three different levels.
        </p>
      </div>

      <Card>
        <CardHeader title="Create material" icon={Layers} />
        <div className="card-pad grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Class">
            <select
              className="input"
              value={form.class_id}
              onChange={(e) => setForm({ ...form, class_id: e.target.value, lesson_plan_id: '' })}
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
          <Field label="Use a lesson plan" hint="Optional — uses its vocabulary and objectives.">
            <select
              className="input"
              value={form.lesson_plan_id}
              onChange={(e) => setForm({ ...form, lesson_plan_id: e.target.value })}
            >
              <option value="">None — use the topic only</option>
              {lessons.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
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
          <div className="sm:col-span-2 lg:col-span-4">
            {error && <ErrorBanner error={error} className="mb-3" />}
            <button className="btn-primary" onClick={generate} disabled={loading}>
              {loading ? <Spinner size={15} /> : <AiGlyph size={16} />}
              {loading ? 'Building three levels…' : 'Generate three levels'}
            </button>
          </div>
        </div>
      </Card>

      {loading ? (
        <Card>
          <LoadingPanel
            label="Differentiation agent is working…"
            hint="Rewriting the material three ways and building a worksheet for each."
          />
        </Card>
      ) : !material ? (
        <Card>
          <EmptyState
            icon={Layers}
            title="No material yet"
            description="Pick a class and topic, then generate. If you have graded the class, students are grouped automatically by their marks."
          />
        </Card>
      ) : (
        <>
          {/* Shared objective */}
          <Card className="border-brand-400/25 bg-brand-50/40">
            <div className="card-pad">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-wide text-brand-700">
                    All three levels teach this objective
                  </p>
                  <p className="mt-1 text-sm font-medium text-ink-800">
                    <T>{material.content?.learning_objective}</T>
                  </p>
                </div>
                <AiLabel />
              </div>
            </div>
          </Card>

          {/* Three columns */}
          <div className="grid gap-5 xl:grid-cols-3">
            {LEVELS.map(({ key, label, tagline, accent, header, chip }) => {
              const level = material[key] || {}
              return (
                <Card key={key} className={`flex flex-col ${accent}`}>
                  <div className="card-pad flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h3 className={`text-base font-bold ${header}`}>{label}</h3>
                        <p className="text-xs text-ink-500">{tagline}</p>
                      </div>
                      <span className={`chip ${chip}`}>
                        {(level.worksheet || []).length} questions
                      </span>
                    </div>

                    <div className="mt-3 rounded-lg border border-white/10 bg-ink-100/40 p-3">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
                        What changed
                      </p>
                      <p className="mt-0.5 text-sm text-ink-700">
                        <T>{level.what_changed}</T>
                      </p>
                    </div>

                    {level.content && (
                      <div className="mt-3">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
                          What to learn
                        </p>
                        <p className="mt-0.5 text-sm leading-relaxed text-ink-700">
                          <T>{level.content}</T>
                        </p>
                      </div>
                    )}

                    {(level.key_points || []).length > 0 && (
                      <div className="mt-3">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
                          Key points
                        </p>
                        <ul className="mt-1 space-y-0.5">
                          {level.key_points.map((point, index) => (
                            <li key={index} className="flex gap-1.5 text-sm text-ink-700">
                              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-current opacity-40" />
                              <T>{point}</T>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {(level.scaffolds || []).length > 0 && (
                      <div className="mt-3">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
                          Scaffolds &amp; hints
                        </p>
                        <ul className="mt-1 space-y-0.5">
                          {level.scaffolds.map((scaffold, index) => (
                            <li key={index} className="flex gap-1.5 text-sm text-ink-600">
                              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-ink-300" />
                              <T>{scaffold}</T>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {(level.worksheet || []).length > 0 && (
                      <details className="mt-4">
                        <summary className="cursor-pointer text-sm font-semibold text-ink-700">
                          View worksheet ({level.worksheet.length} questions)
                        </summary>
                        <ol className="mt-2 space-y-1.5">
                          {level.worksheet.map((question, index) => (
                            <li key={question.id} className="rounded border border-white/10 bg-ink-100/40 p-2 text-sm">
                              <span className="font-semibold text-ink-500">
                                {index + 1}.{' '}
                              </span>
                              <T>{question.question}</T>
                              {question.hint && (
                                <p className="mt-0.5 text-xs text-ink-500 italic">
                                  Hint: {question.hint}
                                </p>
                              )}
                            </li>
                          ))}
                        </ol>
                      </details>
                    )}
                  </div>

                  <div className="flex gap-2 border-t border-ink-200/70 px-5 py-3">
                    <button
                      className="btn-secondary btn-sm flex-1"
                      onClick={() => handleExport(key, 'pdf')}
                      disabled={exporting?.startsWith(key)}
                    >
                      <Download size={13} /> PDF
                    </button>
                    <button
                      className="btn-secondary btn-sm flex-1"
                      onClick={() => handleExport(key, 'docx')}
                      disabled={exporting?.startsWith(key)}
                    >
                      <Download size={13} /> DOCX
                    </button>
                  </div>
                </Card>
              )
            })}
          </div>

          {/* Groupings */}
          <Card>
            <CardHeader
              title="Suggested student groupings"
              subtitle={material.grouping_rationale}
              icon={Users}
              actions={
                <button className="btn-ghost btn-sm" onClick={generate} disabled={loading}>
                  <RefreshCw size={13} />
                  Re-group
                </button>
              }
            />
            <div className="card-pad grid gap-4 pt-4 md:grid-cols-3">
              {(material.groupings || []).map((grouping) => {
                const meta = LEVELS.find((l) => l.key === grouping.level)
                return (
                  <div key={grouping.level} className="rounded-lg border border-ink-200 p-3.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className={`chip ${meta?.chip || 'bg-ink-100 text-ink-700'}`}>
                        {meta?.label || grouping.level}
                      </span>
                      <span className="text-sm font-bold tabular-nums text-ink-700">
                        {grouping.students.length}
                      </span>
                    </div>
                    <ul className="mt-2.5 space-y-1">
                      {grouping.students.map((student) => (
                        <li key={student.student_id} className="text-sm text-ink-700">
                          {student.name}
                          {student.roll_no && (
                            <span className="ml-1.5 text-xs text-ink-400">#{student.roll_no}</span>
                          )}
                        </li>
                      ))}
                      {grouping.students.length === 0 && (
                        <li className="text-sm text-ink-400">No students at this level</li>
                      )}
                    </ul>
                  </div>
                )
              })}
            </div>
            <div className="card-pad pt-0">
              <p className="flex items-start gap-2 rounded-lg bg-ink-50 px-3.5 py-2.5 text-xs text-ink-600">
                <Info size={14} className="mt-0.5 shrink-0" />
                Groups are suggested from your marked papers, not enforced. Move anyone you disagree
                with — the agent only sees anonymous IDs, never student names.
              </p>
            </div>
          </Card>
        </>
      )}
    </div>
  )
}