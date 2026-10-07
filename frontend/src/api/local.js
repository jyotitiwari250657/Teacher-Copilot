/**
 * A complete, standalone implementation of the TeacherCopilot API.
 *
 * The app runs entirely in the browser: this module owns the state, persists it
 * to localStorage, and runs the same four agents the FastAPI backend would.
 * There is no server to start.
 *
 * It deliberately mirrors the backend's response shapes (including `problems`
 * validation errors and 401s) so every page works unchanged.
 */
import {
  CLASSES,
  QUESTIONS,
  STUDENTS,
  SUBMISSIONS,
  TEACHER,
  TOTAL_MARKS,
} from '../data/seed.js'
import {
  differentiate,
  gradeSubmission,
  lessonPlanner,
  parentUpdate,
  levelFor,
  sanitise,
  WHATSAPP_WORD_LIMIT,
} from '../data/agents.js'

const DB_KEY = 'teachercopilot.db.v1'
const SESSION_KEY = 'teachercopilot.session'

/** Time-saved estimates, matching the backend's defaults. */
const ESTIMATES = {
  lesson_plan_minutes: 45,
  grading_minutes_per_paper: 3,
  differentiation_minutes: 60,
  parent_message_minutes: 5,
}

const STEPS = [
  { number: 1, step_key: 'lesson_plan', title: 'Plan the lesson', agent: 'lesson_planner' },
  { number: 2, step_key: 'differentiate', title: 'Build three levels', agent: 'differentiation' },
  { number: 3, step_key: 'grade', title: 'Grade every script', agent: 'grader' },
  { number: 4, step_key: 'regroup', title: 'Regroup the class', agent: 'orchestrator' },
  { number: 5, step_key: 'parent_messages', title: 'Draft parent messages', agent: 'parent_update' },
]

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------
export class ApiError extends Error {
  constructor(message, status = 400, problems = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.problems = problems
  }
}

const unauthorized = () =>
  new ApiError('Your session has expired. Please log in again.', 401)

const notFound = (what = 'Not found') => new ApiError(what, 404)

// ---------------------------------------------------------------------------
// Persistence
// ---------------------------------------------------------------------------
function freshDb() {
  return {
    version: 1,
    counters: { lesson: 1, material: 1, result: 1, message: 1, run: 1, log: 1, class: 2, student: 100 },
    teacher: { ...TEACHER },
    classes: CLASSES.map((c) => ({ ...c })),
    students: STUDENTS.map((s) => ({ ...s })),
    assessment: {
      id: 1,
      class_id: 1,
      title: 'Photosynthesis - Class Test',
      subject: 'Science',
      duration_minutes: 30,
      total_marks: TOTAL_MARKS,
      created_at: iso(-6 * 864e5),
      questions: QUESTIONS.map((q) => ({ ...q })),
    },
    submissions: SUBMISSIONS.map((s) => ({ ...s })),
    lessons: [],
    materials: [],
    results: [],
    messages: [],
    workflowRuns: [],
    logs: [],
    timeSaved: [],
  }
}

let cache = null

function iso(offsetMs = 0) {
  return new Date(Date.now() + offsetMs).toISOString()
}

export function loadDb() {
  if (cache) return cache
  try {
    const raw = localStorage.getItem(DB_KEY)
    if (raw) {
      cache = JSON.parse(raw)
      return cache
    }
  } catch {
    /* corrupt or unavailable storage - fall through to a fresh database */
  }
  cache = freshDb()
  save()
  return cache
}

export function save() {
  if (!cache) return
  try {
    localStorage.setItem(DB_KEY, JSON.stringify(cache))
  } catch {
    /* private browsing - the session still works, it just will not persist */
  }
}

export function resetDb() {
  cache = freshDb()
  save()
  return cache
}

const nextId = (kind) => cache.counters[kind]++

// ---------------------------------------------------------------------------
// Session
// ---------------------------------------------------------------------------
export function getToken() {
  try {
    return localStorage.getItem(SESSION_KEY) || sessionStorage.getItem(SESSION_KEY)
  } catch {
    return null
  }
}

/** `remember: false` keeps the session in sessionStorage - gone on close. */
export function setToken(token, remember = true) {
  try {
    localStorage.removeItem(SESSION_KEY)
    sessionStorage.removeItem(SESSION_KEY)
    if (token) (remember ? localStorage : sessionStorage).setItem(SESSION_KEY, token)
  } catch {
    /* ignore */
  }
}

function requireSession() {
  if (!getToken()) throw unauthorized()
}

// ---------------------------------------------------------------------------
// Lookups
// ---------------------------------------------------------------------------
const findStudent = (id) => cache.students.find((s) => s.id === id)
const findClass = (id) => cache.classes.find((c) => c.id === id)

function refToStudentId(ref) {
  const student = cache.students.find((s) => s.ref === ref)
  return student ? student.id : null
}

/** The privacy boundary: names are only ever attached here, after "generation". */
function withName(entity) {
  const student = findStudent(entity.student_id)
  return { ...entity, student_name: student ? student.name : 'Unknown' }
}

function logTimeSaved(taskType, minutes) {
  cache.timeSaved.push({
    id: cache.timeSaved.length + 1,
    task_type: taskType,
    minutes_saved: minutes,
    created_at: iso(),
  })
}

function logAgent(agent, success, durationMs, summary, error) {
  const entry = {
    id: nextId('log'),
    agent,
    success,
    duration_ms: durationMs,
    tokens: success ? 0 : 0,
    output_summary: summary || '',
    error: error || '',
    created_at: iso(),
  }
  cache.logs.push(entry)
  return entry
}

// ---------------------------------------------------------------------------
// Grading helpers
// ---------------------------------------------------------------------------
function applyOverrides(result) {
  const overrides = result.teacher_overrides || []
  if (overrides.length === 0) return result.result
  const merged = {
    ...result.result,
    per_question_marks: result.result.per_question_marks.map((mark) => {
      const override = overrides.find((o) => o.question_id === mark.question_id)
      if (!override) return mark
      // A teacher's mark is authoritative: full confidence, and flagged as theirs.
      return { ...mark, marks_awarded: override.marks_awarded, confidence: 1, overridden: true }
    }),
  }
  const total = Math.round(merged.per_question_marks.reduce((s, m) => s + m.marks_awarded, 0) * 100) / 100
  return { ...merged, total, percentage: result.max_total ? (total / result.max_total) * 100 : 0 }
}

function gradeOne(assessment, studentId, answers, strictness) {
  const student = findStudent(studentId)
  const graded = gradeSubmission({
    questions: assessment.questions,
    answers,
    student_ref: student ? student.ref : 'S01',
    strictness,
  })

  const existing = cache.results.find(
    (r) => r.assessment_id === assessment.id && r.student_id === studentId,
  )
  if (existing) {
    existing.result = graded
    existing.total = graded.total
    existing.percentage = graded.percentage
    existing.needs_teacher_review = graded.needs_teacher_review
    existing.approved = false
    existing.approved_at = null
    existing.teacher_overrides = []
    return existing
  }

  const record = {
    id: nextId('result'),
    assessment_id: assessment.id,
    class_id: assessment.class_id,
    student_id: studentId,
    student_ref: graded.student_ref,
    result: graded,
    total: graded.total,
    max_total: graded.max_total,
    percentage: graded.percentage,
    needs_teacher_review: graded.needs_teacher_review,
    approved: false,
    approved_at: null,
    teacher_overrides: [],
    created_at: iso(),
  }
  cache.results.push(record)
  return record
}

const resultOut = (record) => ({
  ...withName(record),
  result: applyOverrides(record),
  total: applyOverrides(record).total,
  percentage: Math.round(applyOverrides(record).percentage * 10) / 10,
})

// ---------------------------------------------------------------------------
// Documents (lesson plans + worksheets)
// ---------------------------------------------------------------------------
export const buildLessonDoc = (plan, teacher) => ({
  filename: `${plan.title.replace(/[^\w-]+/g, '_')}.doc`,
  title: plan.title,
  html: `<h1>${esc(plan.title)}</h1>
    <p class="muted">${esc(teacher?.school_name || '')} &middot; ${esc(teacher?.name || '')}</p>
    <h2>Learning objectives</h2><ol>${(plan.content.learning_objectives || []).map((o) => `<li>${esc(o)}</li>`).join('')}</ol>
    <h2>Lesson flow (${(plan.content.lesson_flow || []).reduce((s, p) => s + p.minutes, 0)} minutes)</h2>
    <table><tr><th>Phase</th><th>Minutes</th><th>What happens</th></tr>
    ${(plan.content.lesson_flow || []).map((p) => `<tr><td>${esc(p.phase)}</td><td>${p.minutes}</td><td>${esc(p.description)}</td></tr>`).join('')}
    </table>
    <h2>Exit tickets</h2><ul>${(plan.content.exit_ticket || []).map((t) => `<li>${esc(t)}</li>`).join('')}</ul>
    <h2>Assessment rubric</h2>
    <table><tr><th>Criterion</th><th>Marks</th></tr>${(plan.content.assessment_rubric || []).map((r) => `<tr><td>${esc(r.criterion)}</td><td>${r.marks}</td></tr>`).join('')}</table>
    <h2>Homework</h2><p>${esc(plan.content.homework || '')}</p>`,
})

export const buildWorksheetDoc = (material, level, includeAnswers) => {
  const section = material[level] || {}
  return {
    filename: `${material.topic.replace(/[^\w-]+/g, '_')}_${level}.doc`,
    title: `${material.topic} - ${level[0].toUpperCase()}${level.slice(1)} worksheet`,
    html: `<h1>${esc(material.topic)} &mdash; ${esc(level)} level</h1>
    <p class="muted">${esc(material.learning_objective || '')}</p>
    <p><strong>What changed:</strong> ${esc(section.what_changed || '')}</p>
    <h2>What to learn</h2><p>${esc(section.content || '')}</p>
    ${(section.key_points || []).length ? `<h2>Key points</h2><ul>${section.key_points.map((k) => `<li>${esc(k)}</li>`).join('')}</ul>` : ''}
    <h2>Questions</h2><ol>${(section.worksheet || []).map((q) => `<li>${esc(q.question)}${q.hint ? `<div class="hint">Hint: ${esc(q.hint)}</div>` : ''}</li>`).join('')}</ol>
    ${includeAnswers && (section.answer_key || []).length ? `<h2>Answer key</h2><ol>${section.answer_key.map((a) => `<li>${esc(a.answer)}</li>`).join('')}</ol>` : ''}`,
  }
}

function esc(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

// ---------------------------------------------------------------------------
// Approval inbox (shared by /workflow/{id}/inbox and the sidebar badge)
// ---------------------------------------------------------------------------
function buildInbox() {
  const items = []

  cache.messages
    .filter((m) => m.status === 'draft' || m.status === 'needs_review')
    .forEach((message) => {
      const student = findStudent(message.student_id)
      items.push({
        kind: 'parent_message',
        id: message.id,
        title: `Message to ${student ? student.parent_name : 'parent'}`,
        subtitle: `About ${student ? student.name : 'a student'} - ${message.channel}`,
        status: message.status,
        needs_review: message.needs_teacher_review,
        reasons: message.review_reasons || [],
        preview: message.body.slice(0, 240),
      })
    })

  cache.results
    .filter((r) => !r.approved)
    .forEach((record) => {
      const student = findStudent(record.student_id)
      items.push({
        kind: 'grade',
        id: record.id,
        title: `Marks for ${student ? student.name : 'a student'}`,
        subtitle: `${round(record.total)} of ${round(record.max_total)} (${Math.round(record.percentage)}%) - not yet approved`,
        status: record.needs_teacher_review ? 'needs_review' : 'draft',
        needs_review: record.needs_teacher_review,
        reasons: record.needs_teacher_review
          ? ['The grader was unsure about at least one answer.']
          : ['Teacher approval required before marks are final.'],
        preview: '',
      })
    })

  cache.lessons
    .filter((p) => p.status === 'draft')
    .forEach((plan) => {
      items.push({
        kind: 'lesson_plan',
        id: plan.id,
        title: `Lesson plan: ${plan.title}`,
        subtitle: 'Draft - approve before you teach from it',
        status: 'draft',
        needs_review: false,
        reasons: [],
        preview: '',
      })
    })

  cache.materials.forEach((material) => {
    items.push({
      kind: 'material',
      id: material.id,
      title: `Three-level material: ${material.topic}`,
      subtitle: 'Support / Core / Extension - check the groupings',
      status: material.status,
      needs_review: false,
      reasons: [],
      preview: '',
    })
  })

  return {
    count: items.length,
    needs_attention: items.filter((i) => i.needs_review).length,
    items,
  }
}

const round = (n) => Math.round(Number(n) * 10) / 10

// ---------------------------------------------------------------------------
// The public API surface (same method names as the HTTP client)
// ---------------------------------------------------------------------------
export const localApi = {
  async login(email, password, remember = true) {
    loadDb()
    await wait(420)
    const match = String(email).trim().toLowerCase()
    if (match !== cache.teacher.email || password !== 'demo1234') {
      throw new ApiError('Incorrect email or password. Use the demo account below.', 401)
    }
    const token = `local.${Date.now()}`
    setToken(token, remember)
    return { access_token: token, token_type: 'bearer', teacher: { ...cache.teacher } }
  },

  async me() {
    loadDb()
    requireSession()
    return { ...cache.teacher }
  },

  async updateMe(patch) {
    loadDb()
    requireSession()
    cache.teacher = { ...cache.teacher, ...patch }
    save()
    return { ...cache.teacher }
  },

  async config() {
    loadDb()
    return {
      llm: {
        provider: 'local',
        model: 'built-in agents (no network)',
        base_url: 'in-browser',
        api_key_configured: false,
        mock_mode: false,
      },
      messaging: {
        mode: 'simulated',
        simulated: true,
        smtp_configured: false,
        whatsapp_configured: false,
      },
      time_saved_estimates: ESTIMATES,
      rate_limit: { max_calls: 40, window_seconds: 60 },
      storage: 'localStorage',
    }
  },

  // ---- classes & students
  async classes() {
    loadDb()
    requireSession()
    return cache.classes.map((c) => ({
      ...c,
      student_count: cache.students.filter((s) => s.class_id === c.id).length,
    }))
  },

  async createClass(body) {
    loadDb()
    requireSession()
    const created = { id: nextId('class'), student_count: 0, teacher_id: 1, ...body }
    cache.classes.push(created)
    save()
    return { ...created, student_count: 0 }
  },

  async updateClass(id, body) {
    loadDb()
    requireSession()
    const target = findClass(id)
    if (!target) throw notFound('Class not found.')
    Object.assign(target, body)
    save()
    return { ...target }
  },

  async deleteClass(id) {
    loadDb()
    requireSession()
    cache.classes = cache.classes.filter((c) => c.id !== id)
    cache.students = cache.students.filter((s) => s.class_id !== id)
    save()
    return { deleted: true }
  },

  async students(classId) {
    loadDb()
    requireSession()
    return cache.students
      .filter((s) => !classId || s.class_id === Number(classId))
      .map(({ tier, ...student }) => student)
  },

  async createStudent(classId, body) {
    loadDb()
    requireSession()
    const siblings = cache.students.filter((s) => s.class_id === Number(classId))
    const created = {
      id: nextId('student'),
      class_id: Number(classId),
      ref: `S${String(siblings.length + 1).padStart(2, '0')}`,
      preferred_language: 'English',
      attendance_pct: 100,
      notes: '',
      ...body,
    }
    cache.students.push(created)
    save()
    const { tier, ...rest } = created
    return rest
  },

  async updateStudent(id, body) {
    loadDb()
    requireSession()
    const student = findStudent(id)
    if (!student) throw notFound('Student not found.')
    Object.assign(student, body)
    save()
    const { tier, ...rest } = student
    return rest
  },

  async deleteStudent(id) {
    loadDb()
    requireSession()
    cache.students = cache.students.filter((s) => s.id !== id)
    cache.results = cache.results.filter((r) => r.student_id !== id)
    cache.messages = cache.messages.filter((m) => m.student_id !== id)
    save()
    return { deleted: true }
  },

  async importStudents(classId, file) {
    loadDb()
    requireSession()
    const text = await file.text()
    const rows = parseCsv(text)
    if (!rows.length || !rows[0].some((h) => h.trim().toLowerCase() === 'name')) {
      throw new ApiError('The CSV needs a "name" column.', 400)
    }
    const headers = rows[0].map((h) => h.trim().toLowerCase())
    let created = 0
    let updated = 0
    rows.slice(1).forEach((row) => {
      const record = Object.fromEntries(headers.map((h, i) => [h, (row[i] || '').trim()]))
      if (!record.name) return
      const existing = cache.students.find(
        (s) => s.class_id === Number(classId) && s.name.toLowerCase() === record.name.toLowerCase(),
      )
      if (existing) {
        Object.assign(existing, {
          parent_name: record.parent_name || existing.parent_name,
          parent_phone: record.parent_phone || existing.parent_phone,
          parent_email: record.parent_email || existing.parent_email,
          preferred_language: record.preferred_language || existing.preferred_language,
          attendance_pct: Number(record.attendance_pct) || existing.attendance_pct,
        })
        updated += 1
      } else {
        const siblings = cache.students.filter((s) => s.class_id === Number(classId))
        cache.students.push({
          id: nextId('student'),
          class_id: Number(classId),
          ref: `S${String(siblings.length + 1).padStart(2, '0')}`,
          roll_no: record.roll_no || String(siblings.length + 1),
          parent_name: record.parent_name || 'Parent',
          parent_phone: record.parent_phone || '',
          parent_email: record.parent_email || '',
          preferred_language: record.preferred_language || 'English',
          attendance_pct: Number(record.attendance_pct) || 100,
          notes: '',
          name: record.name,
        })
        created += 1
      }
    })
    save()
    return { created, updated, failed: 0, total: created + updated }
  },

  async studentCsvTemplate() {
    return {
      filename: 'students_template.csv',
      csv: 'name,roll_no,parent_name,parent_phone,parent_email,preferred_language,attendance_pct\nAsha Rao,20,Mr Rao,+919999999901,Hindi,88\n',
    }
  },

  // ---- lesson plans
  async generateLesson(body) {
    loadDb()
    requireSession()
    const started = Date.now()
    const content = lessonPlanner(body)
    const plan = {
      id: nextId('lesson'),
      class_id: body.class_id || null,
      title: content.title,
      subject: body.subject || content.title.split(' - ')[1] || 'Subject',
      topic: body.topic || '',
      language: body.language || 'English',
      duration_minutes: Number(body.duration_minutes) || 40,
      status: 'draft',
      content,
      created_at: iso(),
      approved_at: null,
    }
    cache.lessons.push(plan)
    logTimeSaved('lesson_plan', ESTIMATES.lesson_plan_minutes)
    logAgent('lesson_planner', true, Date.now() - started, `Lesson plan '${content.title}' created`)
    save()
    return { ...plan }
  },

  async lessons(classId) {
    loadDb()
    requireSession()
    return cache.lessons
      .filter((p) => !classId || p.class_id === Number(classId))
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
  },

  async lesson(id) {
    loadDb()
    requireSession()
    const plan = cache.lessons.find((p) => p.id === Number(id))
    if (!plan) throw notFound('Lesson plan not found.')
    return { ...plan }
  },

  async updateLesson(id, body) {
    loadDb()
    requireSession()
    const plan = cache.lessons.find((p) => p.id === Number(id))
    if (!plan) throw notFound('Lesson plan not found.')
    if (body.content) plan.content = { ...plan.content, ...body.content }
    if (body.title) plan.title = body.title
    save()
    return { ...plan }
  },

  async approveLesson(id) {
    loadDb()
    requireSession()
    const plan = cache.lessons.find((p) => p.id === Number(id))
    if (!plan) throw notFound('Lesson plan not found.')
    if (plan.status === 'approved') throw new ApiError('This plan is already approved.', 409)
    plan.status = 'approved'
    plan.approved_at = iso()
    save()
    return { ...plan }
  },

  async regenerateLesson(id) {
    loadDb()
    requireSession()
    const plan = cache.lessons.find((p) => p.id === Number(id))
    if (!plan) throw notFound('Lesson plan not found.')
    plan.content = lessonPlanner({
      subject: plan.subject,
      topic: plan.topic,
      duration_minutes: plan.duration_minutes,
      language: plan.language,
    })
    plan.status = 'draft'
    plan.approved_at = null
    save()
    return { ...plan }
  },

  // ---- grading
  async assessments(classId) {
    loadDb()
    requireSession()
    const list = cache.assessment ? [cache.assessment] : []
    return list
      .filter((a) => !classId || a.class_id === Number(classId))
      .map(({ questions, ...rest }) => ({
        ...rest,
        question_count: questions.length,
        graded_count: cache.results.filter((r) => r.assessment_id === rest.id).length,
      }))
  },

  async assessment(id) {
    loadDb()
    requireSession()
    const found = cache.assessment && cache.assessment.id === Number(id) ? cache.assessment : null
    if (!found) throw notFound('Assessment not found.')
    return { ...found }
  },

  async createAssessment(body) {
    loadDb()
    requireSession()
    const questions = body.questions || []
    if (questions.length === 0) {
      throw new ApiError('Please check the highlighted fields.', 422, ['questions: at least one question is required'])
    }
    cache.assessment = {
      id: 1,
      class_id: body.class_id || 1,
      title: body.title || 'Untitled paper',
      subject: body.subject || 'General',
      duration_minutes: body.duration_minutes || 30,
      total_marks: questions.reduce((sum, q) => sum + (Number(q.marks) || 0), 0),
      questions,
      created_at: iso(),
    }
    cache.results = cache.results.filter((r) => r.assessment_id !== 1)
    save()
    return { ...cache.assessment }
  },

  async submissions(assessmentId) {
    loadDb()
    requireSession()
    return cache.submissions.map((s) => ({ ...s }))
  },

  async gradeOne(body) {
    loadDb()
    requireSession()
    const record = gradeOne(cache.assessment, Number(body.student_id), body.answers || {}, body.strictness)
    logAgent('grader', true, 120, `Graded ${record.student_ref}`)
    save()
    return resultOut(record)
  },

  async gradeBulk(body) {
    loadDb()
    requireSession()
    const started = Date.now()
    const results = []
    const failures = []
    ;(body.submissions || []).forEach((submission) => {
      try {
        results.push(
          gradeOne(cache.assessment, Number(submission.student_id), submission.answers || {}, body.strictness),
        )
      } catch (err) {
        failures.push({ student_id: submission.student_id, error: err.message })
      }
    })
    const flagged = results.filter((r) => r.needs_teacher_review).length
    if (results.length) {
      logTimeSaved('grading', ESTIMATES.grading_minutes_per_paper * results.length)
    }
    logAgent(
      'grader',
      failures.length === 0,
      Date.now() - started,
      `Graded ${results.length} script(s), ${flagged} flagged for review`,
    )
    save()
    await wait(500)
    return {
      assessment_id: cache.assessment.id,
      graded: results.length,
      failed: failures.length,
      failures,
      results: results.map(resultOut),
    }
  },

  async gradeBulkCsv(assessmentId, file, strictness) {
    loadDb()
    requireSession()
    const rows = parseCsv(await file.text())
    if (rows.length < 2) throw new ApiError('The CSV needs a header and at least one row.', 400)
    const headers = rows[0].map((h) => h.trim())
    const idIndex = headers.findIndex((h) => ['student_id', 'roll_no', 'student'].includes(h.toLowerCase()))
    if (idIndex === -1) {
      throw new ApiError('The CSV needs a student_id column.', 400)
    }
    const submissions = []
    const skipped = []
    rows.slice(1).forEach((row) => {
      const raw = (row[idIndex] || '').trim()
      const student =
        cache.students.find((s) => String(s.id) === raw) ||
        cache.students.find((s) => String(s.roll_no) === raw)
      if (!student) {
        skipped.push({ row: raw, error: 'unknown student' })
        return
      }
      const answers = {}
      headers.forEach((header, index) => {
        if (index === idIndex) return
        const match = cache.assessment.questions.find((q) => q.id.toLowerCase() === header.toLowerCase())
        if (match) answers[match.id] = row[index] || ''
      })
      submissions.push({ student_id: student.id, answers })
    })
    const outcome = await this.gradeBulk({
      assessment_id: Number(assessmentId),
      strictness,
      submissions,
    })
    return { ...outcome, skipped }
  },

  async results(assessmentId) {
    loadDb()
    requireSession()
    return {
      results: cache.results
        .filter((r) => !assessmentId || r.assessment_id === Number(assessmentId))
        .map(resultOut),
    }
  },

  async overrideMarks(resultId, overrides) {
    loadDb()
    requireSession()
    const record = cache.results.find((r) => r.id === Number(resultId))
    if (!record) throw notFound('Result not found.')
    record.teacher_overrides = (overrides || []).map((o) => ({
      question_id: o.question_id,
      marks_awarded: Number(o.marks_awarded),
      created_at: iso(),
    }))
    const merged = applyOverrides(record)
    record.total = merged.total
    record.percentage = merged.percentage
    save()
    return resultOut(record)
  },

  async approveResult(resultId) {
    loadDb()
    requireSession()
    const record = cache.results.find((r) => r.id === Number(resultId))
    if (!record) throw notFound('Result not found.')
    record.approved = true
    record.approved_at = iso()
    record.needs_teacher_review = false
    save()
    return resultOut(record)
  },

  async approveAllResults(assessmentId) {
    loadDb()
    requireSession()
    const targets = cache.results.filter(
      (r) => (!assessmentId || r.assessment_id === Number(assessmentId)) && !r.approved,
    )
    targets.forEach((record) => {
      record.approved = true
      record.approved_at = iso()
      record.needs_teacher_review = false
    })
    save()
    return { approved: targets.length }
  },

  async analysis(assessmentId) {
    loadDb()
    requireSession()
    const rows = cache.results.filter((r) => r.assessment_id === Number(assessmentId))
    const assessment = cache.assessment
    if (rows.length === 0) {
      return {
        assessment_id: Number(assessmentId),
        graded: 0,
        average_percentage: 0,
        median_percentage: 0,
        highest: null,
        lowest: null,
        questions: [],
        hardest_questions: [],
        common_mistakes: [],
        band_distribution: [],
      }
    }

    const students = rows.map((record) => {
      const merged = applyOverrides(record)
      const student = findStudent(record.student_id)
      return {
        student_id: record.student_id,
        student_name: student ? student.name : 'Unknown',
        roll_no: student ? student.roll_no : '',
        percentage: merged.percentage,
        total: merged.total,
        needs_teacher_review: record.needs_teacher_review,
        approved: record.approved,
        weaknesses: merged.weaknesses || [],
      }
    })

    const perQuestion = new Map()
    rows.forEach((record) => {
      applyOverrides(record).per_question_marks.forEach((mark) => {
        const bucket = perQuestion.get(mark.question_id) || {
          question_id: mark.question_id,
          max_marks: mark.max_marks,
          awarded_total: 0,
          attempts: 0,
          zero_count: 0,
          full_count: 0,
        }
        bucket.awarded_total += mark.marks_awarded
        bucket.attempts += 1
        if (mark.max_marks && mark.marks_awarded <= 0) bucket.zero_count += 1
        if (mark.max_marks && mark.marks_awarded >= mark.max_marks - 1e-9) bucket.full_count += 1
        perQuestion.set(mark.question_id, bucket)
      })
    })

    const questionText = new Map((assessment?.questions || []).map((q) => [q.id, q.question]))
    const questions = [...perQuestion.values()].map((bucket) => ({
      ...bucket,
      question: questionText.get(bucket.question_id) || '',
      average_marks: round(bucket.awarded_total / (bucket.attempts || 1)),
      average_percentage: bucket.max_marks
        ? Math.round((bucket.awarded_total / (bucket.attempts || 1) / bucket.max_marks) * 1000) / 10
        : 0,
      zero_rate: Math.round((bucket.zero_count / (bucket.attempts || 1)) * 1000) / 10,
      full_mark_rate: Math.round((bucket.full_count / (bucket.attempts || 1)) * 1000) / 10,
    }))
    questions.sort((a, b) => a.average_percentage - b.average_percentage)

    const percentages = students.map((s) => s.percentage).sort((a, b) => a - b)
    const middle = Math.floor(percentages.length / 2)
    const median =
      percentages.length % 2
        ? percentages[middle]
        : Math.round((percentages[middle - 1] + percentages[middle]) * 10) / 20

    const counts = new Map()
    rows.forEach((record) => {
      ;(applyOverrides(record).weaknesses || []).forEach((issue) => {
        counts.set(issue, (counts.get(issue) || 0) + 1)
      })
    })

    return {
      assessment_id: Number(assessmentId),
      assessment_title: assessment ? assessment.title : '',
      graded: students.length,
      average_percentage: Math.round((percentages.reduce((a, b) => a + b, 0) / percentages.length) * 10) / 10,
      median_percentage: median,
      highest: students.reduce((a, b) => (b.percentage > a.percentage ? b : a)),
      lowest: students.reduce((a, b) => (b.percentage < a.percentage ? b : a)),
      students: [...students].sort((a, b) => b.percentage - a.percentage),
      questions,
      hardest_questions: questions.slice(0, 3),
      common_mistakes: [...counts.entries()]
        .sort((a, b) => b[1] - a[1])
        .slice(0, 6)
        .map(([issue, count]) => ({ issue, count })),
      band_distribution: [
        { band: '90-100', count: percentages.filter((p) => p >= 90).length },
        { band: '75-89', count: percentages.filter((p) => p >= 75 && p < 90).length },
        { band: '50-74', count: percentages.filter((p) => p >= 50 && p < 75).length },
        { band: '25-49', count: percentages.filter((p) => p >= 25 && p < 50).length },
        { band: '0-24', count: percentages.filter((p) => p < 25).length },
      ],
    }
  },

  // ---- differentiation
  async differentiate(body) {
    loadDb()
    requireSession()
    const started = Date.now()
    const classId = Number(body.class_id) || 1

    // Group from the most recent marks, exactly like the backend does.
    const recent = cache.results
      .filter((r) => r.class_id === classId)
      .map((record) => ({
        student_ref: record.student_ref,
        percentage: applyOverrides(record).percentage,
      }))
    const performance = recent.length
      ? recent
      : cache.students
          .filter((s) => s.class_id === classId)
          .map((s) => ({ student_ref: s.ref, percentage: null }))

    const generated = differentiate({
      topic: body.topic || 'Photosynthesis',
      language: body.language || 'English',
      performance,
      manual_levels: body.manual_levels || {},
    })

    const material = {
      id: nextId('material'),
      class_id: classId,
      topic: generated.topic,
      language: body.language || 'English',
      status: 'draft',
      created_at: iso(),
      ...generated,
    }
    // Resolve anonymous refs back to real names - locally, after generation.
    material.groupings = material.groupings.map((group) => ({
      ...group,
      students: group.student_refs
        .map((ref) => {
          const student = cache.students.find((s) => s.ref === ref)
          return student
            ? { student_id: student.id, name: student.name, roll_no: student.roll_no }
            : null
        })
        .filter(Boolean),
    }))

    cache.materials.push(material)
    logTimeSaved('differentiation', ESTIMATES.differentiation_minutes)
    logAgent('differentiation', true, Date.now() - started, `Three levels created for ${material.topic}`)
    save()
    await wait(450)
    return { ...material }
  },

  async materials(classId) {
    loadDb()
    requireSession()
    return cache.materials
      .filter((m) => !classId || m.class_id === Number(classId))
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
  },

  async material(id) {
    loadDb()
    requireSession()
    const found = cache.materials.find((m) => m.id === Number(id))
    if (!found) throw notFound('Material not found.')
    return { ...found }
  },

  // ---- parent updates
  async generateMessages(body) {
    loadDb()
    requireSession()
    const started = Date.now()
    const classId = Number(body.class_id) || 1
    const students = cache.students.filter((s) => s.class_id === classId)
    const created = []
    const failures = []

    students.forEach((student) => {
      try {
        const record = cache.results.find((r) => r.student_id === student.id)
        const merged = record ? applyOverrides(record) : null
        const generated = parentUpdate({
          student_name: `{{student_name}}`,
          subject: body.subject || 'Science',
          overall_percentage: merged ? merged.percentage : student.tier === 'weak' ? 38 : student.tier === 'average' ? 64 : 88,
          attendance_pct: student.attendance_pct,
          tone: body.tone || 'warm',
          language: body.language || 'English',
          channel: body.channel || 'whatsapp',
          teacher_note: body.teacher_note || '',
        })

        const message = {
          id: nextId('message'),
          student_id: student.id,
          class_id: classId,
          workflow_run_id: body.workflow_run_id || null,
          channel: generated.channel,
          language: generated.language,
          tone: generated.tone,
          subject: generated.subject_line,
          body: sanitise(generated.body).split('{{student_name}}').join(student.name),
          word_count: generated.word_count,
          positive_observation: sanitise(generated.positive_observation).split('{{student_name}}').join(student.name),
          area_to_improve: generated.area_to_improve,
          home_step: generated.home_step,
          status: generated.needs_teacher_review ? 'needs_review' : 'draft',
          needs_teacher_review: generated.needs_teacher_review,
          review_reasons: generated.review_reasons,
          created_at: iso(),
          sent_at: null,
        }
        cache.messages = cache.messages.filter(
          (m) => m.student_id !== student.id || m.status === 'sent' || m.status === 'simulated_sent',
        )
        cache.messages.push(message)
        created.push({ ...message, student_name: student.name })
      } catch (err) {
        failures.push({ student_id: student.id, error: err.message })
      }
    })

    if (created.length) {
      logTimeSaved('parent_message', ESTIMATES.parent_message_minutes * created.length)
    }
    const flagged = created.filter((m) => m.needs_teacher_review).length
    logAgent(
      'parent_update',
      failures.length === 0,
      Date.now() - started,
      `${created.length} message(s) drafted, ${flagged} flagged`,
    )
    save()
    await wait(500)
    return {
      class_id: classId,
      generated: created.length,
      failed: failures.length,
      failures,
      messages: created,
      requires_approval: true,
      whatsapp_word_limit: WHATSAPP_WORD_LIMIT,
    }
  },

  async messages(classId, status) {
    loadDb()
    requireSession()
    return cache.messages
      .filter((m) => !classId || m.class_id === Number(classId))
      .filter((m) => !status || m.status === status)
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
      .map(withName)
  },

  async message(id) {
    loadDb()
    requireSession()
    const found = cache.messages.find((m) => m.id === Number(id))
    if (!found) throw notFound('Message not found.')
    return { ...withName(found), can_send: found.status === 'approved' }
  },

  async updateMessage(id, body) {
    loadDb()
    requireSession()
    const message = cache.messages.find((m) => m.id === Number(id))
    if (!message) throw notFound('Message not found.')
    if (message.status === 'sent' || message.status === 'simulated_sent') {
      // The parent already has this text; editing it would misrepresent what
      // was sent. Draft a new message instead.
      throw new ApiError('This message was already sent and can no longer be edited.', 409)
    }
    if (body.body !== undefined) message.body = body.body
    if (body.subject !== undefined) message.subject = body.subject
    message.word_count = message.body.trim().split(/\s+/).filter(Boolean).length
    // Editing invalidates an approval: it must be re-read before sending.
    message.status = 'draft'
    message.approved_at = null
    message.needs_teacher_review = false
    save()
    return { ...withName(message), can_send: false }
  },

  async approveMessage(id) {
    loadDb()
    requireSession()
    const message = cache.messages.find((m) => m.id === Number(id))
    if (!message) throw notFound('Message not found.')
    if (message.status === 'approved') {
      throw new ApiError('This message is already approved.', 409)
    }
    message.status = 'approved'
    message.approved_at = iso()
    message.needs_teacher_review = false
    save()
    return { ...withName(message), can_send: true }
  },

  async approveAllMessages(classId) {
    loadDb()
    requireSession()
    const targets = cache.messages.filter(
      (m) => (!classId || m.class_id === Number(classId)) &&
        (m.status === 'draft' || m.status === 'needs_review'),
    )
    targets.forEach((message) => {
      message.status = 'approved'
      message.approved_at = iso()
      message.needs_teacher_review = false
    })
    save()
    return { approved: targets.length }
  },

  async sendMessages(body) {
    loadDb()
    requireSession()
    const ids = body.send_all ? null : body.message_ids || []
    const targets = cache.messages.filter((m) =>
      ids ? ids.includes(m.id) : m.status === 'approved',
    )
    const results = []
    targets.forEach((message) => {
      if (message.status !== 'approved') {
        results.push({
          id: message.id,
          status: message.status,
          error: `A message must be approved before it can be sent. This one is '${message.status}'.`,
        })
      } else {
        message.status = 'simulated_sent'
        message.sent_at = iso()
        results.push({ id: message.id, status: 'simulated_sent', error: null })
      }
    })
    const sent = results.filter((r) => r.status === 'simulated_sent').length
    save()
    return { sent, blocked: results.length - sent, failed: 0, results, simulated: true }
  },

  async approvalInbox(classId) {
    loadDb()
    requireSession()
    const inbox = buildInbox()
    if (!classId) return inbox
    const students = new Set(
      cache.students.filter((s) => s.class_id === Number(classId)).map((s) => s.id),
    )
    const items = inbox.items.filter((item) => {
      if (item.kind === 'parent_message' || item.kind === 'grade') {
        const record =
          item.kind === 'parent_message'
            ? cache.messages.find((m) => m.id === item.id)
            : cache.results.find((r) => r.id === item.id)
        return record ? students.has(record.student_id) : false
      }
      return true
    })
    return { count: items.length, needs_attention: items.filter((i) => i.needs_review).length, items }
  },

  // ---- workflow
  async stepDefinitions() {
    return STEPS.map((step) => ({ ...step }))
  },

  async runWorkflow(body) {
    loadDb()
    requireSession()
    const started = Date.now()
    const classId = Number(body.class_id) || 1
    const run = {
      id: nextId('run'),
      class_id: classId,
      topic: body.topic || 'Photosynthesis',
      subject: body.subject || 'Science',
      language: body.language || 'English',
      status: 'running',
      error: '',
      lesson_plan_id: null,
      assessment_id: cache.assessment.id,
      material_id: null,
      steps: STEPS.map((step) => ({
        ...step,
        status: 'pending',
        detail: '',
        duration_ms: 0,
        output: {},
      })),
      logs: [],
      created_at: iso(),
      finished_at: null,
    }

    const mark = (key, patch) => {
      const step = run.steps.find((s) => s.step_key === key)
      Object.assign(step, patch)
    }

    // 1. Lesson plan
    let stepStart = Date.now()
    try {
      const content = lessonPlanner({
        subject: run.subject,
        topic: run.topic,
        grade: '8',
        duration_minutes: Number(body.duration_minutes) || 40,
        language: run.language,
      })
      const plan = {
        id: nextId('lesson'),
        class_id: classId,
        title: content.title,
        subject: run.subject,
        topic: run.topic,
        language: run.language,
        duration_minutes: Number(body.duration_minutes) || 40,
        status: 'draft',
        content,
        created_at: iso(),
        approved_at: null,
      }
      cache.lessons.push(plan)
      run.lesson_plan_id = plan.id
      logTimeSaved('lesson_plan', ESTIMATES.lesson_plan_minutes)
      run.logs.push(logAgent('lesson_planner', true, Date.now() - stepStart, `Lesson plan '${content.title}' created`))
      mark('lesson_plan', {
        status: 'needs_review',
        duration_ms: Date.now() - stepStart,
        detail: `Lesson plan '${content.title}' created with ${content.lesson_flow.length} phases totalling ${content.lesson_flow.reduce((s, p) => s + p.minutes, 0)} minutes. Waiting for your approval.`,
        output: { lesson_plan_id: plan.id },
      })
    } catch (err) {
      mark('lesson_plan', { status: 'failed', detail: err.message, duration_ms: Date.now() - stepStart })
    }

    // 2. Differentiation
    stepStart = Date.now()
    try {
      const performance = cache.students
        .filter((s) => s.class_id === classId)
        .map((s) => ({ student_ref: s.ref, percentage: null }))
      const generated = differentiate({ topic: run.topic, language: run.language, performance })
      const material = {
        id: nextId('material'),
        class_id: classId,
        topic: generated.topic,
        language: run.language,
        status: 'draft',
        created_at: iso(),
        ...generated,
        groupings: generated.groupings.map((group) => ({
          ...group,
          students: group.student_refs
            .map((ref) => {
              const student = cache.students.find((s) => s.ref === ref)
              return student ? { student_id: student.id, name: student.name, roll_no: student.roll_no } : null
            })
            .filter(Boolean),
        })),
      }
      cache.materials.push(material)
      run.material_id = material.id
      logTimeSaved('differentiation', ESTIMATES.differentiation_minutes)
      run.logs.push(logAgent('differentiation', true, Date.now() - stepStart, `Three levels created for ${material.topic}`))
      mark('differentiate', {
        status: 'done',
        duration_ms: Date.now() - stepStart,
        detail: `Three levels and three worksheets created (${material.support.worksheet.length}/${material.core.worksheet.length}/${material.extension.worksheet.length} questions).`,
        output: { material_id: material.id },
      })
    } catch (err) {
      mark('differentiate', { status: 'failed', detail: err.message, duration_ms: Date.now() - stepStart })
    }

    // 3. Grade
    stepStart = Date.now()
    try {
      const submissions = body.use_sample_answers === false ? [] : cache.submissions
      if (submissions.length === 0) {
        mark('grade', { status: 'skipped', detail: 'No submissions to grade.', duration_ms: Date.now() - stepStart })
      } else {
        const graded = submissions.map((s) =>
          gradeOne(cache.assessment, s.student_id, s.answers, body.strictness || 'standard'),
        )
        const flagged = graded.filter((r) => r.needs_teacher_review).length
        logTimeSaved('grading', ESTIMATES.grading_minutes_per_paper * graded.length)
        run.logs.push(logAgent('grader', true, Date.now() - stepStart, `Graded ${graded.length} script(s)`))
        mark('grade', {
          status: 'needs_review',
          duration_ms: Date.now() - stepStart,
          detail: `${graded.length} of ${submissions.length} students graded. ${flagged} flagged for your review (low confidence).`,
          output: { graded: graded.length, flagged },
        })
      }
    } catch (err) {
      mark('grade', { status: 'failed', detail: err.message, duration_ms: Date.now() - stepStart })
    }

    // 4. Regroup
    stepStart = Date.now()
    const groupSizes = {}
    try {
      const marked = cache.results.filter((r) => r.class_id === classId)
      if (marked.length === 0) {
        mark('regroup', { status: 'skipped', detail: 'Grade the class first to get suggested groups.', duration_ms: Date.now() - stepStart })
      } else {
        const groups = { support: [], core: [], extension: [] }
        marked.forEach((record) => {
          groups[levelFor(applyOverrides(record).percentage)].push(record.id)
        })
        marked.forEach((record) => {
          const level = levelFor(applyOverrides(record).percentage)
          record.group_level = level
        })
        Object.entries(groups).forEach(([level, ids]) => {
          groupSizes[level] = ids.length
        })
        run.logs.push(logAgent('orchestrator', true, Date.now() - stepStart, 'Regrouped students from the latest marks'))
        mark('regroup', {
          status: 'needs_review',
          duration_ms: Date.now() - stepStart,
          detail: `Students grouped from the latest marks: support ${groupSizes.support || 0}, core ${groupSizes.core || 0}, extension ${groupSizes.extension || 0}.`,
          output: { group_sizes: groupSizes },
        })
      }
    } catch (err) {
      mark('regroup', { status: 'failed', detail: err.message, duration_ms: Date.now() - stepStart })
    }

    // 5. Parent messages
    stepStart = Date.now()
    try {
      const outcome = await this.generateMessages({
        class_id: classId,
        workflow_run_id: run.id,
        channel: body.channel || 'whatsapp',
        tone: body.tone || 'warm',
        language: run.language,
        subject: run.subject,
        teacher_note: body.teacher_note || '',
      })
      mark('parent_messages', {
        status: 'needs_review',
        duration_ms: Date.now() - stepStart,
        detail: `${outcome.generated} draft messages created. ${outcome.messages.filter((m) => m.needs_teacher_review).length} flagged for your review before sending. Nothing is sent without your approval.`,
        output: { generated: outcome.generated },
      })
    } catch (err) {
      mark('parent_messages', { status: 'failed', detail: err.message, duration_ms: Date.now() - stepStart })
    }

    // needs_review is a success state; only failed/skipped downgrade the run.
    const broken = run.steps.filter((s) => s.status === 'failed' || s.status === 'skipped')
    run.status = broken.length === 0 ? 'done' : broken.length < run.steps.length ? 'done_with_errors' : 'failed'
    run.finished_at = iso()
    run.duration_ms = Date.now() - started
    cache.workflowRuns.unshift(run)
    save()

    run.inbox = buildInbox()
    await wait(700)
    return { ...run }
  },

  async workflowStatus(id) {
    loadDb()
    requireSession()
    const run = cache.workflowRuns.find((r) => r.id === Number(id))
    if (!run) throw notFound('Run not found.')
    return { ...run, logs: run.logs, inbox: buildInbox() }
  },

  async workflowRuns(classId) {
    loadDb()
    requireSession()
    return cache.workflowRuns
      .filter((r) => !classId || r.class_id === Number(classId))
      .map(({ logs, ...run }) => ({ ...run }))
  },

  async workflowInbox() {
    loadDb()
    requireSession()
    return buildInbox()
  },

  async rerunStep(id, stepKey) {
    loadDb()
    requireSession()
    const run = cache.workflowRuns.find((r) => r.id === Number(id))
    if (!run) throw notFound('Run not found.')
    if (!STEPS.some((s) => s.step_key === stepKey)) {
      throw new ApiError(`'${stepKey}' is not a step in this workflow.`, 400)
    }

    const step = run.steps.find((s) => s.step_key === stepKey)
    const started = Date.now()
    step.status = 'running'
    step.detail = 'Re-running…'

    if (stepKey === 'parent_messages') {
      cache.messages = cache.messages.filter(
        (m) => m.workflow_run_id !== run.id || m.status === 'sent' || m.status === 'simulated_sent',
      )
      const outcome = await this.generateMessages({
        class_id: run.class_id,
        workflow_run_id: run.id,
        language: run.language,
        subject: run.subject,
      })
      step.status = 'needs_review'
      step.duration_ms = Date.now() - started
      step.detail = `${outcome.generated} draft messages regenerated. Nothing is sent without your approval.`
      step.output = { generated: outcome.generated }
    } else if (stepKey === 'grade') {
      const graded = cache.submissions.map((s) => gradeOne(cache.assessment, s.student_id, s.answers, 'standard'))
      step.status = 'needs_review'
      step.duration_ms = Date.now() - started
      step.detail = `${graded.length} of ${graded.length} students re-graded.`
      step.output = { graded: graded.length }
    } else if (stepKey === 'differentiate') {
      const performance = cache.students
        .filter((s) => s.class_id === run.class_id)
        .map((s) => ({ student_ref: s.ref, percentage: null }))
      const generated = differentiate({ topic: run.topic, language: run.language, performance })
      const material = {
        id: nextId('material'),
        class_id: run.class_id,
        topic: generated.topic,
        language: run.language,
        status: 'draft',
        created_at: iso(),
        ...generated,
        groupings: generated.groupings.map((group) => ({
          ...group,
          students: group.student_refs
            .map((ref) => {
              const student = cache.students.find((s) => s.ref === ref)
              return student ? { student_id: student.id, name: student.name, roll_no: student.roll_no } : null
            })
            .filter(Boolean),
        })),
      }
      cache.materials.push(material)
      run.material_id = material.id
      step.status = 'done'
      step.duration_ms = Date.now() - started
      step.detail = `Three levels regenerated for ${material.topic}.`
      step.output = { material_id: material.id }
    } else if (stepKey === 'regroup') {
      const marked = cache.results.filter((r) => r.class_id === run.class_id)
      const groups = { support: 0, core: 0, extension: 0 }
      marked.forEach((record) => {
        const level = levelFor(applyOverrides(record).percentage)
        record.group_level = level
        groups[level] += 1
      })
      step.status = marked.length ? 'needs_review' : 'skipped'
      step.duration_ms = Date.now() - started
      step.detail = marked.length
        ? `Students regrouped: support ${groups.support}, core ${groups.core}, extension ${groups.extension}.`
        : 'Grade the class first to get suggested groups.'
      step.output = { group_sizes: groups }
    } else {
      const content = lessonPlanner({
        subject: run.subject,
        topic: run.topic,
        duration_minutes: 40,
        language: run.language,
      })
      const plan = {
        id: nextId('lesson'),
        class_id: run.class_id,
        title: content.title,
        subject: run.subject,
        topic: run.topic,
        language: run.language,
        duration_minutes: 40,
        status: 'draft',
        content,
        created_at: iso(),
        approved_at: null,
      }
      cache.lessons.push(plan)
      run.lesson_plan_id = plan.id
      step.status = 'needs_review'
      step.duration_ms = Date.now() - started
      step.detail = `Lesson plan '${content.title}' regenerated.`
      step.output = { lesson_plan_id: plan.id }
    }

    const broken = run.steps.filter((s) => s.status === 'failed' || s.status === 'skipped')
    run.status = broken.length === 0 ? 'done' : broken.length < run.steps.length ? 'done_with_errors' : 'failed'
    run.finished_at = iso()
    save()
    return { ...run, rerun_step: stepKey, inbox: buildInbox() }
  },

  // ---- dashboard
  async dashboard() {
    loadDb()
    requireSession()

    const approvedGrades = cache.results.filter((r) => r.approved)
    const sent = cache.messages.filter((m) => m.status === 'sent' || m.status === 'simulated_sent')
    const pendingMessages = cache.messages.filter(
      (m) => m.status === 'draft' || m.status === 'needs_review' || m.status === 'approved',
    )

    const byTask = cache.timeSaved.reduce((acc, row) => {
      acc[row.task_type] = (acc[row.task_type] || 0) + row.minutes_saved
      return acc
    }, {})

    return {
      lesson_plans_created: cache.lessons.length,
      lesson_plans_approved: cache.lessons.filter((p) => p.status === 'approved').length,
      papers_graded: new Set(cache.results.map((r) => r.assessment_id)).size,
      students_graded: approvedGrades.length,
      results_needing_review: cache.results.filter((r) => r.needs_teacher_review && !r.approved).length,
      messages_sent: sent.length,
      messages_pending: pendingMessages.length,
      worksheets_created: cache.materials.length,
      time_saved_this_week_minutes: thisWeekMinutes(),
      time_saved_all_time_minutes: cache.timeSaved.reduce((s, r) => s + r.minutes_saved, 0),
      time_saved_by_task: byTask,
      weekly_time_saved: weeklyChart(),
      class_overview: cache.classes.map((c) => {
        const students = cache.students.filter((s) => s.class_id === c.id)
        const results = cache.results.filter((r) => r.class_id === c.id)
        const average = results.length
          ? Math.round(results.reduce((sum, r) => sum + applyOverrides(r).percentage, 0) / results.length)
          : 0
        const attendance = students.length
          ? Math.round(students.reduce((sum, s) => sum + (s.attendance_pct || 0), 0) / students.length)
          : 0
        return {
          class_id: c.id,
          class_name: c.name,
          grade: c.grade,
          subject: c.subject,
          student_count: students.length,
          graded_count: results.length,
          average_percentage: average,
          average_attendance: attendance,
          pending_messages: cache.messages.filter(
            (m) => m.class_id === c.id && (m.status === 'draft' || m.status === 'needs_review'),
          ).length,
        }
      }),
      recent_activity: cache.workflowRuns
        .slice(0, 5)
        .map((run) => ({
          id: run.id,
          kind: 'workflow',
          title: `Weekly workflow - ${run.topic}`,
          detail: `${run.steps.length} steps, ${run.status.replace(/_/g, ' ')}`,
          created_at: run.created_at,
        })),
      approval_inbox_count: buildInbox().count,
    }
  },

  // ---- convenience
  async resetDemo() {
    resetDb()
    return { reset: true }
  },
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------
function thisWeekMinutes() {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  // Monday of the current week.
  const weekday = (start.getDay() + 6) % 7
  start.setDate(start.getDate() - weekday)
  return cache.timeSaved
    .filter((row) => new Date(row.created_at) >= start)
    .reduce((sum, row) => sum + row.minutes_saved, 0)
}

function weeklyChart() {
  const weeks = []
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  const weekday = (now.getDay() + 6) % 7
  now.setDate(now.getDate() - weekday)

  for (let index = 5; index >= 0; index -= 1) {
    const weekStart = new Date(now)
    weekStart.setDate(weekStart.getDate() - index * 7)
    const weekEnd = new Date(weekStart)
    weekEnd.setDate(weekEnd.getDate() + 7)
    const minutes = cache.timeSaved
      .filter((row) => {
        const created = new Date(row.created_at)
        return created >= weekStart && created < weekEnd
      })
      .reduce((sum, row) => sum + row.minutes_saved, 0)
    weeks.push({
      week_start: weekStart.toISOString(),
      label: weekStart.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }),
      minutes,
    })
  }
  return weeks
}

function parseCsv(text) {
  return String(text)
    .split(/\r?\n/)
    .filter((line) => line.trim().length)
    .map((line) => line.split(',').map((cell) => cell.replace(/^"|"$/g, '')))
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
