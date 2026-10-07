import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Plus,
  Users,
  Trash2,
  Pencil,
  Upload,
  Download,
  X,
  GraduationCap,
  FolderPlus,
} from 'lucide-react'
import { api } from '../api/client'
import { useToast } from '../components/Toast'
import {
  Card,
  CardHeader,
  Field,
  ErrorBanner,
  SkeletonTable,
  EmptyState,
  AiLabel,
} from '../components/ui'

const EMPTY_STUDENT = {
  name: '',
  roll_no: '',
  parent_name: '',
  parent_phone: '',
  parent_email: '',
  preferred_language: 'English',
  attendance_pct: 100,
  teacher_notes: '',
}

export default function Classes() {
  const toast = useToast()
  const fileInput = useRef(null)

  const [classes, setClasses] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [students, setStudents] = useState([])
  const [loadingClasses, setLoadingClasses] = useState(true)
  const [loadingStudents, setLoadingStudents] = useState(false)
  const [error, setError] = useState(null)

  const [showClassForm, setShowClassForm] = useState(false)
  const [classForm, setClassForm] = useState({ name: '', grade: '', section: '', subject: '' })
  const [editingStudent, setEditingStudent] = useState(null)
  const [studentForm, setStudentForm] = useState(EMPTY_STUDENT)
  const [busy, setBusy] = useState(false)
  const [importing, setImporting] = useState(false)

  const loadClasses = useCallback(async () => {
    setLoadingClasses(true)
    try {
      const data = await api.classes()
      setClasses(data)
      setSelectedId((current) =>
        current && data.some((item) => item.id === current) ? current : data[0]?.id ?? null,
      )
    } catch (err) {
      setError(err)
    } finally {
      setLoadingClasses(false)
    }
  }, [])

  const loadStudents = useCallback(async (classId) => {
    if (!classId) return setStudents([])
    setLoadingStudents(true)
    try {
      setStudents(await api.students(classId))
    } catch (err) {
      setError(err)
      setStudents([])
    } finally {
      setLoadingStudents(false)
    }
  }, [])

  useEffect(() => {
    loadClasses()
  }, [loadClasses])

  useEffect(() => {
    loadStudents(selectedId)
  }, [selectedId, loadStudents])

  const selectedClass = useMemo(
    () => classes.find((item) => item.id === selectedId) || null,
    [classes, selectedId],
  )

  // ---- class actions
  async function createClass(event) {
    event.preventDefault()
    setBusy(true)
    try {
      const created = await api.createClass(classForm)
      setClasses((current) => [...current, created].sort((a, b) => a.name.localeCompare(b.name)))
      setSelectedId(created.id)
      setClassForm({ name: '', grade: '', section: '', subject: '' })
      setShowClassForm(false)
      toast.success(`Class "${created.name}" created.`)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function deleteClass() {
    if (!selectedClass) return
    const confirmed = window.confirm(
      `Delete "${selectedClass.name}" and all ${selectedClass.student_count} students? This cannot be undone.`,
    )
    if (!confirmed) return
    try {
      await api.deleteClass(selectedClass.id)
      toast.success('Class deleted.')
      setSelectedId(null)
      loadClasses()
    } catch (err) {
      toast.error(err.message)
    }
  }

  // ---- student actions
  async function saveStudent(event) {
    event.preventDefault()
    setBusy(true)
    try {
      if (editingStudent?.id) {
        await api.updateStudent(editingStudent.id, studentForm)
        toast.success('Student updated.')
      } else {
        await api.createStudent(selectedId, studentForm)
        toast.success('Student added.')
      }
      setEditingStudent(null)
      setStudentForm(EMPTY_STUDENT)
      loadStudents(selectedId)
      loadClasses()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function removeStudent(student) {
    if (!window.confirm(`Remove ${student.name} from this class?`)) return
    try {
      await api.deleteStudent(student.id)
      toast.success(`${student.name} removed.`)
      loadStudents(selectedId)
      loadClasses()
    } catch (err) {
      toast.error(err.message)
    }
  }

  function editStudent(student) {
    setEditingStudent(student)
    setStudentForm({
      name: student.name,
      roll_no: student.roll_no || '',
      parent_name: student.parent_name || '',
      parent_phone: student.parent_phone || '',
      parent_email: student.parent_email || '',
      preferred_language: student.preferred_language || 'English',
      attendance_pct: student.attendance_pct ?? 100,
      teacher_notes: student.teacher_notes || '',
    })
  }

  async function handleCsv(event) {
    const file = event.target.files?.[0]
    if (!file) return
    setImporting(true)
    try {
      const result = await api.importStudents(selectedId, file)
      toast.success(
        `Imported ${result.created} student${result.created === 1 ? '' : 's'}` +
          (result.errors?.length ? ` (${result.errors.length} rows skipped)` : ''),
      )
      loadStudents(selectedId)
      loadClasses()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setImporting(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  async function downloadTemplate() {
    try {
      const template = await api.studentCsvTemplate()
      const blob = new Blob([template.content], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = template.filename
      anchor.click()
      setTimeout(() => URL.revokeObjectURL(url), 2000)
    } catch (err) {
      toast.error(err.message)
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-ink-800">Classes &amp; Students</h1>
          <p className="mt-1 text-sm text-ink-500">
            Student names are never sent to the AI — only anonymous IDs are.
          </p>
        </div>
        <button className="btn-primary" onClick={() => setShowClassForm((v) => !v)}>
          {showClassForm ? <X size={16} /> : <Plus size={16} />}
          {showClassForm ? 'Cancel' : 'New class'}
        </button>
      </div>

      {error && <ErrorBanner error={error} onRetry={loadClasses} />}

      {showClassForm && (
        <Card>
          <CardHeader title="Create a class" icon={FolderPlus} />
          <form onSubmit={createClass} className="card-pad grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Class name" required>
              <input
                className="input"
                value={classForm.name}
                onChange={(e) => setClassForm({ ...classForm, name: e.target.value })}
                placeholder="Class 8-B"
                required
              />
            </Field>
            <Field label="Grade">
              <input
                className="input"
                value={classForm.grade}
                onChange={(e) => setClassForm({ ...classForm, grade: e.target.value })}
                placeholder="8"
              />
            </Field>
            <Field label="Section">
              <input
                className="input"
                value={classForm.section}
                onChange={(e) => setClassForm({ ...classForm, section: e.target.value })}
                placeholder="B"
              />
            </Field>
            <Field label="Subject">
              <input
                className="input"
                value={classForm.subject}
                onChange={(e) => setClassForm({ ...classForm, subject: e.target.value })}
                placeholder="Science"
              />
            </Field>
            <div className="sm:col-span-2 lg:col-span-4">
              <button className="btn-primary" disabled={busy}>
                {busy ? 'Creating…' : 'Create class'}
              </button>
            </div>
          </form>
        </Card>
      )}

      {loadingClasses ? (
        <Card>
          <SkeletonTable rows={4} cols={3} />
        </Card>
      ) : classes.length === 0 ? (
        <Card>
          <EmptyState
            icon={Users}
            title="No classes yet"
            description="Create your first class to add students and start using the AI agents."
            action={
              <button className="btn-primary" onClick={() => setShowClassForm(true)}>
                <Plus size={16} /> New class
              </button>
            }
          />
        </Card>
      ) : (
        <div className="grid gap-5 lg:grid-cols-3">
          {/* Class list */}
          <Card className="lg:col-span-1">
            <CardHeader title="Your classes" icon={Users} />
            <div className="space-y-1.5 p-3">
              {classes.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setSelectedId(item.id)}
                  className={`w-full rounded-lg border p-3 text-left transition ${
                    selectedId === item.id
                      ? 'border-brand-400 bg-brand-50'
                      : 'border-ink-200 hover:border-ink-300 hover:bg-ink-50'
                  }`}
                >
                  <p className="text-sm font-semibold text-ink-800">{item.name}</p>
                  <p className="text-xs text-ink-500">
                    Grade {item.grade || '—'} · {item.subject || 'General'} ·{' '}
                    {item.student_count} students
                  </p>
                </button>
              ))}
            </div>
          </Card>

          {/* Students */}
          <div className="space-y-5 lg:col-span-2">
            <Card>
              <CardHeader
                title={selectedClass ? `${selectedClass.name} students` : 'Students'}
                subtitle={
                  selectedClass
                    ? `${students.length} students · Grade ${selectedClass.grade || '—'}`
                    : undefined
                }
                icon={GraduationCap}
                actions={
                  selectedClass ? (
                    <>
                      <input
                        ref={fileInput}
                        type="file"
                        accept=".csv,text/csv"
                        onChange={handleCsv}
                        className="hidden"
                      />
                      <button
                        className="btn-secondary btn-sm"
                        onClick={() => fileInput.current?.click()}
                        disabled={importing}
                      >
                        <Upload size={14} />
                        {importing ? 'Importing…' : 'Import CSV'}
                      </button>
                      <button className="btn-secondary btn-sm" onClick={downloadTemplate}>
                        <Download size={14} />
                        Template
                      </button>
                      <button
                        className="btn-secondary btn-sm"
                        onClick={() => {
                          setEditingStudent(null)
                          setStudentForm(EMPTY_STUDENT)
                        }}
                      >
                        <Plus size={14} />
                        Add
                      </button>
                      <button className="btn-ghost btn-sm text-red-600" onClick={deleteClass}>
                        <Trash2 size={14} />
                      </button>
                    </>
                  ) : null
                }
              />

              {(editingStudent || studentForm.name !== '') && (
                <form
                  onSubmit={saveStudent}
                  className="grid gap-3 border-b border-ink-200 bg-ink-50/60 p-4 sm:grid-cols-2 lg:grid-cols-4"
                >
                  <Field label="Name" required>
                    <input
                      className="input"
                      value={studentForm.name}
                      onChange={(e) => setStudentForm({ ...studentForm, name: e.target.value })}
                      required
                    />
                  </Field>
                  <Field label="Roll no">
                    <input
                      className="input"
                      value={studentForm.roll_no}
                      onChange={(e) => setStudentForm({ ...studentForm, roll_no: e.target.value })}
                    />
                  </Field>
                  <Field label="Parent name">
                    <input
                      className="input"
                      value={studentForm.parent_name}
                      onChange={(e) =>
                        setStudentForm({ ...studentForm, parent_name: e.target.value })
                      }
                    />
                  </Field>
                  <Field label="Parent phone">
                    <input
                      className="input"
                      value={studentForm.parent_phone}
                      onChange={(e) =>
                        setStudentForm({ ...studentForm, parent_phone: e.target.value })
                      }
                      placeholder="+91…"
                    />
                  </Field>
                  <Field label="Parent email">
                    <input
                      className="input"
                      type="email"
                      value={studentForm.parent_email}
                      onChange={(e) =>
                        setStudentForm({ ...studentForm, parent_email: e.target.value })
                      }
                    />
                  </Field>
                  <Field label="Preferred language">
                    <select
                      className="input"
                      value={studentForm.preferred_language}
                      onChange={(e) =>
                        setStudentForm({ ...studentForm, preferred_language: e.target.value })
                      }
                    >
                      <option>English</option>
                      <option>Hindi</option>
                    </select>
                  </Field>
                  <Field label="Attendance %">
                    <input
                      className="input"
                      type="number"
                      min="0"
                      max="100"
                      value={studentForm.attendance_pct}
                      onChange={(e) =>
                        setStudentForm({
                          ...studentForm,
                          attendance_pct: Number(e.target.value),
                        })
                      }
                    />
                  </Field>
                  <Field label="Teacher notes" hint="Used to personalise parent messages.">
                    <input
                      className="input"
                      value={studentForm.teacher_notes}
                      onChange={(e) =>
                        setStudentForm({ ...studentForm, teacher_notes: e.target.value })
                      }
                    />
                  </Field>
                  <div className="flex items-center gap-2 sm:col-span-2 lg:col-span-4">
                    <button className="btn-primary btn-sm" disabled={busy}>
                      {editingStudent ? 'Save changes' : 'Add student'}
                    </button>
                    <button
                      type="button"
                      className="btn-secondary btn-sm"
                      onClick={() => {
                        setEditingStudent(null)
                        setStudentForm(EMPTY_STUDENT)
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}

              {loadingStudents ? (
                <SkeletonTable rows={6} cols={5} />
              ) : students.length === 0 ? (
                <EmptyState
                  icon={GraduationCap}
                  title="No students in this class"
                  description="Add them one by one, or import a CSV file using the template."
                  action={
                    <div className="flex gap-2">
                      <button
                        className="btn-primary btn-sm"
                        onClick={() => {
                          setEditingStudent(null)
                          setStudentForm(EMPTY_STUDENT)
                        }}
                      >
                        <Plus size={14} /> Add student
                      </button>
                      <button
                        className="btn-secondary btn-sm"
                        onClick={() => fileInput.current?.click()}
                      >
                        <Upload size={14} /> Import CSV
                      </button>
                    </div>
                  }
                />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="border-b border-ink-200 bg-ink-50 text-left text-xs uppercase tracking-wide text-ink-500">
                      <tr>
                        <th className="px-4 py-2.5 font-semibold">#</th>
                        <th className="px-4 py-2.5 font-semibold">Name</th>
                        <th className="px-4 py-2.5 font-semibold">Parent</th>
                        <th className="px-4 py-2.5 font-semibold">Contact</th>
                        <th className="px-4 py-2.5 font-semibold">Language</th>
                        <th className="px-4 py-2.5 text-right font-semibold">Attendance</th>
                        <th className="px-4 py-2.5" />
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-200">
                      {students.map((student, index) => (
                        <tr key={student.id} className="hover:bg-ink-50/60">
                          <td className="px-4 py-2.5 tabular-nums text-ink-400">
                            {student.roll_no || index + 1}
                          </td>
                          <td className="px-4 py-2.5 font-medium text-ink-800">
                            {student.name}
                          </td>
                          <td className="px-4 py-2.5 text-ink-600">{student.parent_name || '—'}</td>
                          <td className="px-4 py-2.5 text-xs text-ink-500">
                            {student.parent_phone || student.parent_email || '—'}
                          </td>
                          <td className="px-4 py-2.5">
                            <span className="chip border-ink-200 bg-ink-50 text-ink-600">
                              {student.preferred_language}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-right tabular-nums">
                            <span
                              className={
                                student.attendance_pct < 70
                                  ? 'font-semibold text-red-600'
                                  : 'text-ink-600'
                              }
                            >
                              {Math.round(student.attendance_pct)}%
                            </span>
                          </td>
                          <td className="px-4 py-2.5">
                            <div className="flex justify-end gap-1">
                              <button
                                className="btn-ghost btn-sm"
                                onClick={() => editStudent(student)}
                                aria-label={`Edit ${student.name}`}
                              >
                                <Pencil size={14} />
                              </button>
                              <button
                                className="btn-ghost btn-sm text-red-600"
                                onClick={() => removeStudent(student)}
                                aria-label={`Remove ${student.name}`}
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <div className="flex items-start gap-2.5 rounded-lg border border-ink-200/70 bg-ink-200/40 p-3.5">
              <AiLabel compact />
              <p className="text-xs text-ink-600">
                When an agent needs to talk about a student, it receives an anonymous ID like
                <code className="mx-1 rounded bg-ink-100 px-1 py-0.5">S03</code>
                and the real name is added back afterwards, on this machine.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}