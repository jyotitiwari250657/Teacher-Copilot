import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ClipboardCheck,
  CheckCircle2,
  Upload,
  BarChart3,
  Pencil,
  Save,
  AlertTriangle,
  FileSpreadsheet,
  Users,
} from 'lucide-react'
import { AiGlyph } from '../components/brand'
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
import { useToast } from '../components/Toast'
import {
  Card,
  CardHeader,
  Field,
  ErrorBanner,
  AiLabel,
  ConfidenceBadge,
  LoadingPanel,
  EmptyState,
  Tabs,
  Spinner,
  T,
} from '../components/ui'

// Steel-to-rust ramp: the top bands are polished steel, the bottom is red, so
// the distribution reads as one metal scale rather than five competing hues.
const BAND_COLORS = {
  '90-100': '#e8edf3',
  '75-89': '#c2cbd6',
  '50-74': '#98a3b0',
  '25-49': '#a8813a',
  '0-24': '#b25f5f',
}

export default function Grading() {
  const toast = useToast()
  const csvInput = useRef(null)

  const [tab, setTab] = useState('review')
  const [classes, setClasses] = useState([])
  const [classId, setClassId] = useState('')
  const [assessments, setAssessments] = useState([])
  const [assessmentId, setAssessmentId] = useState('')
  const [paper, setPaper] = useState(null)
  const [students, setStudents] = useState([])
  const [results, setResults] = useState([])
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading] = useState(true)
  const [grading, setGrading] = useState(false)
  const [error, setError] = useState(null)
  const [strictness, setStrictness] = useState('standard')
  const [edits, setEdits] = useState({})
  const [savingId, setSavingId] = useState(null)

  // ---- loading
  const loadAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const classList = await api.classes()
      setClasses(classList)
      if (classList.length === 0) {
        setLoading(false)
        return
      }
      const activeId = classId || String(classList[0].id)
      if (!classId) setClassId(activeId)

      const [studentList, assessmentList] = await Promise.all([
        api.students(activeId),
        api.assessments(activeId),
      ])
      setStudents(studentList)
      setAssessments(assessmentList)

      if (assessmentList.length > 0) {
        const activeAssessment = assessmentId || String(assessmentList[0].id)
        if (!assessmentId) setAssessmentId(activeAssessment)
        const [fullPaper, resultsData] = await Promise.all([
          api.assessment(activeAssessment),
          api.results(activeAssessment),
        ])
        setPaper(fullPaper)
        setResults(resultsData.results || [])
      } else {
        setPaper(null)
        setResults([])
      }
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [classId, assessmentId])

  useEffect(() => {
    loadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classId, assessmentId])

  const loadAnalysis = useCallback(async () => {
    if (!assessmentId) return setAnalysis(null)
    try {
      setAnalysis(await api.analysis(Number(assessmentId)))
    } catch {
      setAnalysis(null)
    }
  }, [assessmentId])

  useEffect(() => {
    if (tab === 'analysis') loadAnalysis()
  }, [tab, loadAnalysis])

  // ---- actions
  async function gradeAll() {
    setGrading(true)
    setError(null)
    try {
      const submissions = await api.submissions(Number(assessmentId))
      if (submissions.length === 0) {
        toast.error('No answers to grade. Paste answers on the Papers tab first.')
        return
      }
      const payload = {
        assessment_id: Number(assessmentId),
        strictness,
        submissions: submissions.map((submission) => ({
          student_id: submission.student_id,
          answers: submission.answers,
        })),
      }
      const outcome = await api.gradeBulk(payload)
      toast.success(
        `Graded ${outcome.graded} students${outcome.failed ? `, ${outcome.failed} failed` : ''}.`,
      )
      setEdits({})
      await loadAll()
      setTab('review')
    } catch (err) {
      setError(err)
    } finally {
      setGrading(false)
    }
  }

  async function saveOverrides(result) {
    const pending = edits[result.id]
    if (!pending || Object.keys(pending).length === 0) return
    setSavingId(result.id)
    try {
      const overrides = Object.entries(pending).map(([questionId, value]) => ({
        question_id: questionId,
        marks_awarded: Number(value),
      }))
      await api.overrideMarks(result.id, overrides)
      toast.success(`Marks updated for ${result.student_name}.`)
      setEdits((current) => {
        const next = { ...current }
        delete next[result.id]
        return next
      })
      await loadAll()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSavingId(null)
    }
  }

  async function approveResult(result) {
    try {
      await api.approveResult(result.id)
      toast.success(`Marks approved for ${result.student_name}.`)
      await loadAll()
    } catch (err) {
      toast.error(err.message)
    }
  }

  async function approveAll() {
    try {
      const outcome = await api.approveAllResults(Number(assessmentId))
      toast.success(`${outcome.approved} results approved.`)
      await loadAll()
    } catch (err) {
      toast.error(err.message)
    }
  }

  async function handleCsvUpload(event) {
    const file = event.target.files?.[0]
    if (!file) return
    setGrading(true)
    setError(null)
    try {
      const outcome = await api.gradeBulkCsv(Number(assessmentId), file, strictness)
      toast.success(
        `Graded ${outcome.graded} from CSV` +
          (outcome.skipped?.length ? `, ${outcome.skipped.length} rows skipped` : ''),
      )
      await loadAll()
      setTab('review')
    } catch (err) {
      setError(err)
    } finally {
      setGrading(false)
      if (csvInput.current) csvInput.current.value = ''
    }
  }

  // ---- derived
  const totals = useMemo(() => {
    const pending = results.filter((r) => !r.approved).length
    const flagged = results.filter((r) => r.needs_teacher_review && !r.approved).length
    const average = results.length
      ? Math.round(
          results.reduce((sum, r) => sum + r.percentage, 0) / results.length,
        )
      : 0
    return { pending, flagged, average }
  }, [results])

  if (loading) {
    return (
      <Card>
        <LoadingPanel label="Loading the grading desk…" />
      </Card>
    )
  }

  if (classes.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={Users}
          title="No classes yet"
          description="Create a class and add students before grading anything."
        />
      </Card>
    )
  }

  if (assessments.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={FileSpreadsheet}
          title="No question papers yet"
          description="Run the Weekly Workflow — it builds a paper and grades the seeded sample answers in one go."
        />
      </Card>
    )
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-ink-800">Grading</h1>
          <p className="mt-1 text-sm text-ink-500">
            AI marks are a starting point. You can change any mark, and nothing is final until you
            approve it.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            className="input w-auto"
            value={classId}
            onChange={(e) => {
              setClassId(e.target.value)
              setAssessmentId('')
              setResults([])
            }}
          >
            {classes.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
          <select
            className="input w-auto"
            value={assessmentId}
            onChange={(e) => setAssessmentId(e.target.value)}
          >
            {assessments.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && <ErrorBanner error={error} onRetry={loadAll} />}

      {/* Paper summary */}
      {paper && (
        <Card>
          <CardHeader
            title={paper.title}
            subtitle={`${paper.questions.length} questions · ${paper.total_marks} marks · ${results.length} of ${students.length} scripts graded`}
            icon={ClipboardCheck}
            actions={
              <>
                <select
                  className="input btn-sm w-auto"
                  value={strictness}
                  onChange={(e) => setStrictness(e.target.value)}
                  title="How strict the grader should be"
                >
                  <option value="lenient">Lenient</option>
                  <option value="standard">Standard</option>
                  <option value="strict">Strict</option>
                </select>
                <input
                  ref={csvInput}
                  type="file"
                  accept=".csv,text/csv"
                  onChange={handleCsvUpload}
                  className="hidden"
                />
                <button
                  className="btn-secondary btn-sm"
                  onClick={() => csvInput.current?.click()}
                  disabled={grading}
                >
                  <Upload size={14} />
                  Grade CSV
                </button>
                <button className="btn-primary btn-sm" onClick={gradeAll} disabled={grading}>
                  {grading ? <Spinner size={13} /> : <AiGlyph size={14} />}
                  {grading ? 'Grading…' : `Grade ${students.length} scripts`}
                </button>
              </>
            }
          />
          {totals.flagged > 0 && (
            <div className="flex items-start gap-2.5 border-b border-ink-200/70 bg-amber-50/60 px-5 py-2.5">
              <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-600" />
              <p className="text-sm text-amber-900">
                <strong>{totals.flagged}</strong> student
                {totals.flagged === 1 ? ' script has' : ' scripts have'} at least one answer the
                grader was unsure about. Those marks are highlighted below — please check them.
              </p>
            </div>
          )}
        </Card>
      )}

      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: 'review', label: 'Review marks', count: results.length },
          { key: 'paper', label: 'Question paper', count: paper?.questions.length },
          { key: 'analysis', label: 'Class analysis' },
        ]}
      />

      {grading && (
        <Card>
          <LoadingPanel
            label="Grading agent is working…"
            hint="Marking each answer and reporting how confident it is."
          />
        </Card>
      )}

      {/* ---------------- Review ---------------- */}
      {!grading && tab === 'review' && (
        <div className="space-y-4">
          {results.length === 0 ? (
            <Card>
              <EmptyState
                icon={ClipboardCheck}
                title="Nothing graded yet"
                description="Click “Grade 12 scripts” to grade the seeded sample answers, or upload a CSV of your own."
                action={
                  <button className="btn-primary btn-sm" onClick={gradeAll}>
                    <AiGlyph size={14} /> Grade now
                  </button>
                }
              />
            </Card>
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2 text-sm text-ink-600">
                  <span className="chip border-ink-300/60 bg-ink-200/50 text-ink-700">
                    Class average {totals.average}%
                  </span>
                  <span className="chip border-amber-200 bg-amber-50 text-amber-800">
                    {totals.pending} awaiting approval
                  </span>
                  {totals.flagged > 0 && (
                    <span className="chip border-red-200 bg-red-50 text-red-800">
                      {totals.flagged} need checking
                    </span>
                  )}
                  <AiLabel compact />
                </div>
                <button className="btn-secondary btn-sm" onClick={approveAll}>
                  <CheckCircle2 size={14} />
                  Approve all
                </button>
              </div>

              {results.map((result) => (
                <ResultCard
                  key={result.id}
                  result={result}
                  edits={edits[result.id] || {}}
                  onEdit={(questionId, value) =>
                    setEdits((current) => ({
                      ...current,
                      [result.id]: { ...(current[result.id] || {}), [questionId]: value },
                    }))
                  }
                  onSave={() => saveOverrides(result)}
                  onApprove={() => approveResult(result)}
                  saving={savingId === result.id}
                />
              ))}
            </>
          )}
        </div>
      )}

      {/* ---------------- Paper ---------------- */}
      {!grading && tab === 'paper' && paper && (
        <Card>
          <CardHeader title="Question paper" icon={FileSpreadsheet} />
          <div className="card-pad space-y-4">
            {paper.questions.map((question, index) => (
              <div key={question.id} className="rounded-lg border border-ink-200 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="font-medium text-ink-800">
                    <span className="mr-2 text-ink-400">{question.id}.</span>
                    <T>{question.question}</T>
                  </p>
                  <span className="chip shrink-0 border-ink-200 bg-ink-50 text-ink-600">
                    {question.marks} mark{question.marks === 1 ? '' : 's'}
                  </span>
                </div>
                {(question.options || []).length > 0 && (
                  <ul className="mt-2 grid gap-1 sm:grid-cols-2">
                    {question.options.map((option, i) => {
                      const isKey = option === question.answer_key
                      return (
                        <li
                          key={i}
                          className={`rounded px-2 py-1 text-sm ${
                            isKey
                              ? 'bg-brand-50 font-semibold text-brand-800'
                              : 'text-ink-600'
                          }`}
                        >
                          {isKey ? '✓ ' : '  '}
                          {option}
                        </li>
                      )
                    })}
                  </ul>
                )}
                {question.model_answer && (
                  <p className="mt-2 rounded bg-ink-50 px-3 py-2 text-sm text-ink-600">
                    <span className="font-semibold">Model answer: </span>
                    <T>{question.model_answer}</T>
                  </p>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* ---------------- Analysis ---------------- */}
      {!grading && tab === 'analysis' && (
        <div className="space-y-5">
          {!analysis || analysis.graded === 0 ? (
            <Card>
              <EmptyState
                icon={BarChart3}
                title="No analysis yet"
                description="Grade the class first, then come back for the class-level picture."
              />
            </Card>
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <SummaryCard label="Class average" value={`${analysis.average_percentage}%`} />
                <SummaryCard label="Median" value={`${analysis.median_percentage}%`} />
                <SummaryCard
                  label="Highest"
                  value={analysis.highest ? `${analysis.highest.percentage}%` : '—'}
                  hint={analysis.highest?.student_name}
                />
                <SummaryCard
                  label="Lowest"
                  value={analysis.lowest ? `${analysis.lowest.percentage}%` : '—'}
                  hint={analysis.lowest?.student_name}
                />
              </div>

              <div className="grid gap-5 lg:grid-cols-2">
                <Card>
                  <CardHeader title="Score distribution" icon={BarChart3} />
                  <div className="card-pad pt-4">
                    <div className="h-56">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={analysis.band_distribution}
                          margin={{ top: 4, right: 4, left: -22, bottom: 0 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke="#232830" vertical={false} />
                          <XAxis
                            dataKey="band"
                            tick={{ fontSize: 11, fill: '#79838f' }}
                            axisLine={{ stroke: '#232830' }}
                            tickLine={false}
                          />
                          <YAxis
                            allowDecimals={false}
                            tick={{ fontSize: 11, fill: '#79838f' }}
                            axisLine={false}
                            tickLine={false}
                          />
                          <Tooltip
                            contentStyle={{
                              borderRadius: 8,
                              border: '1px solid #232830',
                              background: '#0b0d10',
                              color: '#e6eaf0',
                              fontSize: 12,
                            }}
                            formatter={(value) => [value, 'Students']}
                          />
                          <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                            {analysis.band_distribution.map((entry, index) => (
                              <Cell key={index} fill={BAND_COLORS[entry.band] || '#98a3b0'} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </Card>

                <Card>
                  <CardHeader
                    title="Hardest questions"
                    subtitle="Lowest average score — teach these again."
                    icon={AlertTriangle}
                  />
                  <div className="card-pad pt-4">
                    <ul className="space-y-2.5">
                      {analysis.questions.map((question) => (
                        <li key={question.question_id} className="rounded-lg border border-ink-200 p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="text-xs font-semibold text-ink-500">
                                {question.question_id} · {question.max_marks} marks
                              </p>
                              <p className="truncate text-sm text-ink-700">
                                <T>{question.question}</T>
                              </p>
                            </div>
                            <span
                              className={`shrink-0 text-sm font-bold tabular-nums ${
                                question.average_percentage < 40
                                  ? 'text-red-600'
                                  : question.average_percentage < 70
                                    ? 'text-amber-600'
                                    : 'text-brand-700'
                              }`}
                            >
                              {question.average_percentage}%
                            </span>
                          </div>
                          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-ink-200">
                            <div
                              className={`h-full rounded-full ${
                                question.average_percentage < 40
                                  ? 'bg-red-400'
                                  : question.average_percentage < 70
                                    ? 'bg-amber-400'
                                    : 'bg-brand-500'
                              }`}
                              style={{ width: `${question.average_percentage}%` }}
                            />
                          </div>
                          {question.zero_rate > 0 && (
                            <p className="mt-1.5 text-xs text-ink-500">
                              {question.zero_rate}% of students scored zero
                            </p>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                </Card>
              </div>

              <Card>
                <CardHeader title="Common mistakes" subtitle="Themes across all scripts" />
                <div className="card-pad pt-4">
                  {analysis.common_mistakes.length === 0 ? (
                    <p className="text-sm text-ink-500">No recurring issues detected yet.</p>
                  ) : (
                    <ul className="space-y-2">
                      {analysis.common_mistakes.map((mistake) => (
                        <li
                          key={mistake.issue}
                          className="flex items-start justify-between gap-3 rounded-lg bg-ink-50 px-3 py-2"
                        >
                          <span className="text-sm text-ink-700">{mistake.issue}</span>
                          <span className="chip shrink-0 border-ink-300/60 bg-ink-200/50 text-ink-600">
                            {mistake.count} student{mistake.count === 1 ? '' : 's'}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </Card>

              <Card>
                <CardHeader title="All students" subtitle="Sorted by score" />
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="border-b border-ink-200 bg-ink-50 text-left text-xs uppercase tracking-wide text-ink-500">
                      <tr>
                        <th className="px-4 py-2.5 font-semibold">#</th>
                        <th className="px-4 py-2.5 font-semibold">Student</th>
                        <th className="px-4 py-2.5 font-semibold">Score</th>
                        <th className="px-4 py-2.5 font-semibold">Percentage</th>
                        <th className="px-4 py-2.5 font-semibold">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-200">
                      {analysis.students.map((student, index) => (
                        <tr key={student.student_id} className="hover:bg-ink-50/60">
                          <td className="px-4 py-2.5 tabular-nums text-ink-400">{index + 1}</td>
                          <td className="px-4 py-2.5 font-medium text-ink-800">
                            {student.student_name}
                          </td>
                          <td className="px-4 py-2.5 tabular-nums text-ink-600">
                            {student.total}
                          </td>
                          <td className="px-4 py-2.5">
                            <span
                              className={`font-semibold tabular-nums ${
                                student.percentage >= 50
                                  ? 'text-brand-700'
                                  : 'text-red-600'
                              }`}
                            >
                              {Math.round(student.percentage)}%
                            </span>
                          </td>
                          <td className="px-4 py-2.5">
                            {student.approved ? (
                              <span className="chip border-emerald-200 bg-emerald-50 text-emerald-800">
                                Approved
                              </span>
                            ) : student.needs_teacher_review ? (
                              <span className="chip border-red-200 bg-red-50 text-red-800">
                                Check marks
                              </span>
                            ) : (
                              <span className="chip border-amber-200 bg-amber-50 text-amber-800">
                                Awaiting approval
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
function SummaryCard({ label, value, hint }) {
  return (
    <Card className="card-pad">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">{label}</p>
      <p className="mt-1.5 text-2xl font-bold tabular-nums text-ink-800">{value}</p>
      {hint && <p className="mt-0.5 truncate text-xs text-ink-500">{hint}</p>}
    </Card>
  )
}

function ResultCard({ result, edits, onEdit, onSave, onApprove, saving }) {
  const [open, setOpen] = useState(false)
  const marks = result.result?.per_question_marks || []
  const hasEdits = Object.keys(edits).length > 0

  return (
    <Card className={result.needs_teacher_review && !result.approved ? 'border-red-200' : ''}>
      <div className="card-pad">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-ink-800">{result.student_name}</p>
              <p className="text-xs text-ink-500">
                {result.total} of {result.max_total} marks · {Math.round(result.percentage)}% ·
                anonymous ID {result.student_ref}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {result.needs_teacher_review && !result.approved && (
              <span className="chip border-red-200 bg-red-50 text-red-800">
                <AlertTriangle size={11} /> Check these marks
              </span>
            )}
            {result.approved ? (
              <span className="chip border-emerald-200 bg-emerald-50 text-emerald-800">
                <CheckCircle2 size={11} /> Approved
              </span>
            ) : (
              <button className="btn-primary btn-sm" onClick={onApprove}>
                <CheckCircle2 size={13} /> Approve
              </button>
            )}
            {hasEdits && (
              <button className="btn-secondary btn-sm" onClick={onSave} disabled={saving}>
                {saving ? <Spinner size={13} /> : <Save size={13} />} Save edits
              </button>
            )}
            <button className="btn-ghost btn-sm" onClick={() => setOpen((v) => !v)}>
              {open ? 'Hide' : 'Show'} answers
            </button>
          </div>
        </div>

        {result.result?.overall_feedback && (
          <p className="mt-3 rounded-lg bg-brand-50/70 px-3.5 py-2.5 text-sm text-brand-900">
            {result.result.overall_feedback}
          </p>
        )}

        <div className="mt-3 flex flex-wrap gap-2">
          {(result.result?.strengths || []).map((item, i) => (
            <span
              key={i}
              className="chip border-emerald-200 bg-emerald-50 text-emerald-800"
            >
              ✓ {item}
            </span>
          ))}
          {(result.result?.weaknesses || []).map((item, i) => (
            <span key={i} className="chip border-amber-200 bg-amber-50 text-amber-800">
              ! {item}
            </span>
          ))}
        </div>

        {open && (
          <div className="mt-4 space-y-2 border-t border-ink-200/70 pt-4">
            {marks.map((mark) => {
              const edited = edits[mark.question_id] !== undefined
              const lowConfidence = Number(mark.confidence) < 0.6
              return (
                <div
                  key={mark.question_id}
                  className={`rounded-lg border p-3 ${
                    lowConfidence ? 'border-red-200 bg-red-50/40' : 'border-ink-200'
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-ink-500">
                      {mark.question_id}
                      {mark.overridden && (
                        <span className="ml-2 font-normal text-brand-700">(your mark)</span>
                      )}
                    </span>
                    <div className="flex items-center gap-2">
                      <ConfidenceBadge confidence={mark.confidence} />
                      <label className="flex items-center gap-1.5">
                        <Pencil size={12} className="text-ink-400" />
                        <input
                          type="number"
                          step="0.5"
                          min="0"
                          max={mark.max_marks}
                          defaultValue={mark.marks_awarded}
                          onChange={(e) => onEdit(mark.question_id, e.target.value)}
                          className="input w-16 px-2 py-1 text-center text-xs"
                        />
                        <span className="text-xs text-ink-400">/ {mark.max_marks}</span>
                      </label>
                    </div>
                  </div>
                  <p className="mt-1.5 text-sm text-ink-600">
                    <T>{mark.feedback}</T>
                  </p>
                  {edited && (
                    <p className="mt-1 text-xs font-medium text-brand-700">
                      Changed to {edits[mark.question_id]} — remember to save.
                    </p>
                  )}
                  {lowConfidence && (
                    <p className="mt-1.5 flex items-start gap-1.5 text-xs text-red-700">
                      <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                      The grader was unsure about this one. Please check it.
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </Card>
  )
}