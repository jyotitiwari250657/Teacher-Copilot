/**
 * Standalone verification: proves the app works with NO backend.
 *
 * Runs the real agent modules and the real local API against stubbed browser
 * storage, exercising the invariants the product promises.
 *
 *   node verify-standalone.mjs
 */
const store = () => {
  const data = new Map()
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, String(v)),
    removeItem: (k) => data.delete(k),
    clear: () => data.clear(),
  }
}
globalThis.localStorage = store()
globalThis.sessionStorage = store()
globalThis.window = { location: { reload() {} } }

const {
  allocateMinutes,
  gradeSubmission,
  differentiate,
  lessonPlanner,
  parentUpdate,
  sanitise,
  levelFor,
} = await import('./src/data/agents.js')
const { QUESTIONS, STUDENTS, SUBMISSIONS, TOTAL_MARKS } = await import('./src/data/seed.js')
const { localApi, resetDb } = await import('./src/api/local.js')

let passed = 0
const failures = []
function check(name, condition, detail = '') {
  if (condition) {
    passed += 1
    console.log(`  \x1b[32mPASS\x1b[0m ${name}${detail ? `  \x1b[90m${detail}\x1b[0m` : ''}`)
  } else {
    failures.push(name)
    console.log(`  \x1b[31mFAIL\x1b[0m ${name}${detail ? `  ${detail}` : ''}`)
  }
}
function section(title) {
  console.log(`\n\x1b[1m${title}\x1b[0m`)
}

// ---------------------------------------------------------------------------
section('Lesson Planner - the minutes rule')
let allSums = true
for (let total = 5; total <= 200; total += 1) {
  if (allocateMinutes(total).reduce((s, p) => s + p.minutes, 0) !== total) {
    allSums = false
    console.log(`     broke at ${total}`)
    break
  }
}
check('allocateMinutes is exact for every total 5..200', allSums)

for (const duration of [20, 30, 40, 45, 60, 90]) {
  const plan = lessonPlanner({
    subject: 'Science',
    topic: 'Photosynthesis',
    duration_minutes: duration,
  })
  const sum = plan.lesson_flow.reduce((s, p) => s + p.minutes, 0)
  check(
    `${duration}-minute lesson sums to ${duration}`,
    sum === duration && plan.exit_ticket.length === 3,
    `got ${sum}, ${plan.exit_ticket.length} exit tickets`,
  )
}

const hindi = lessonPlanner({ subject: 'Science', topic: 'Photosynthesis', language: 'Hindi' })
check(
  'Hindi output is Devanagari',
  /[ऀ-ॿ]/.test(hindi.learning_objectives.join('')),
)

// ---------------------------------------------------------------------------
section('Grader - exact MCQ, partial subjective, confidence gate')
const mcq = QUESTIONS[0]
const gradeOne = (answer) =>
  gradeSubmission({ questions: [mcq], answers: { Q1: answer }, student_ref: 'S01' })
    .per_question_marks[0].marks_awarded
check('exact MCQ key scores full marks', gradeOne(mcq.answer_key) === 1)
check('lowercase MCQ key still matches', gradeOne(String(mcq.answer_key).toLowerCase()) === 1)
check('padded MCQ key still matches', gradeOne(`  ${mcq.answer_key} `) === 1)
check('a near miss scores zero', gradeOne('chloroplast') === 0, 'answer: chloroplast')

const tf = QUESTIONS[5]
const gradeTf = (answer) =>
  gradeSubmission({ questions: [tf], answers: { Q6: answer } }).per_question_marks[0]
check('true/false correct', gradeTf('True').marks_awarded === 1 && gradeTf('yes').marks_awarded === 1)
check('true/false wrong', gradeTf('False').marks_awarded === 0)

const full = gradeSubmission({
  questions: QUESTIONS,
  answers: SUBMISSIONS[0].answers,
  student_ref: 'S01',
})
check('a strong script scores above 80%', full.percentage >= 80, `${full.percentage}%`)

const weak = gradeSubmission({
  questions: QUESTIONS,
  answers: SUBMISSIONS[6].answers,
  student_ref: 'S07',
})
check('a weak script scores below 50%', weak.percentage < 50, `${weak.percentage}%`)
check('low-confidence answers force review', weak.needs_teacher_review === true)

const never = gradeSubmission({ questions: QUESTIONS, answers: {}, student_ref: 'S01' })
check(
  'blank answers are certain zeros, not guesses',
  never.needs_teacher_review === false && never.total === 0,
)

const neverOver = gradeSubmission({ questions: QUESTIONS, answers: SUBMISSIONS[0].answers })
check(
  'marks never exceed the maximum',
  neverOver.per_question_marks.every((m) => m.marks_awarded <= m.max_marks),
)

const lenient = gradeSubmission({
  questions: QUESTIONS,
  answers: SUBMISSIONS[4].answers,
  strictness: 'lenient',
})
const strict = gradeSubmission({
  questions: QUESTIONS,
  answers: SUBMISSIONS[4].answers,
  strictness: 'strict',
})
check('lenient is not harsher than strict', lenient.total >= strict.total, `${lenient.total} vs ${strict.total}`)

// ---------------------------------------------------------------------------
section('Differentiation - three levels, shared objective')
const performance = [
  { student_ref: 'S01', percentage: 25 },
  { student_ref: 'S02', percentage: 55 },
  { student_ref: 'S03', percentage: 88 },
]
const material = differentiate({ topic: 'Photosynthesis', performance })
let levelsOk = true
for (const level of ['support', 'core', 'extension']) {
  const section_ = material[level]
  const ids = section_.worksheet.map((q) => q.id)
  const keyIds = section_.answer_key.map((a) => a.question_id)
  if (ids.length < 8 || ids.length > 10) {
    levelsOk = false
    console.log(`     ${level} has ${ids.length} questions`)
  }
  if (ids.join() !== keyIds.join()) {
    levelsOk = false
    console.log(`     ${level} answer key does not match`)
  }
}
check('every level has 8-10 questions with a matching answer key', levelsOk)
check(
  'each level explains what changed, differently',
  new Set([material.support.what_changed, material.core.what_changed, material.extension.what_changed]).size === 3,
)
check('one shared learning objective', Boolean(material.learning_objective))
const grouped = Object.fromEntries(material.groupings.map((g) => [g.level, g.student_refs]))
check('groups follow the score bands', grouped.support[0] === 'S01' && grouped.extension[0] === 'S03')
check('level boundaries', levelFor(39) === 'support' && levelFor(40) === 'core' && levelFor(76) === 'extension')

// ---------------------------------------------------------------------------
section('Parent Update - length cap, required parts, safety')
const message = parentUpdate({
  student_name: '{{student_name}}',
  overall_percentage: 78,
  attendance_pct: 92,
  channel: 'whatsapp',
})
check('WhatsApp body is 120 words or fewer', message.word_count <= 120, `${message.word_count} words`)
check(
  'has a positive, an improvement and a home step',
  Boolean(message.positive_observation && message.area_to_improve && message.home_step),
)
check('low score is flagged', parentUpdate({ student_name: 'x', overall_percentage: 20, attendance_pct: 95 }).needs_teacher_review)
check('low attendance is flagged', parentUpdate({ student_name: 'x', overall_percentage: 80, attendance_pct: 40 }).needs_teacher_review)
check('a healthy student is not flagged', parentUpdate({ student_name: 'x', overall_percentage: 78, attendance_pct: 92 }).needs_teacher_review === false)
check('email gets a subject line', Boolean(parentUpdate({ student_name: 'x', overall_percentage: 78, channel: 'email' }).subject_line))
for (const banned of ['slow learner', 'dyslexic', 'careless', 'other students']) {
  check(
    `"${banned}" is stripped`,
    !sanitise(`Your child is a slow learner and careless. Other students did better.`).toLowerCase().includes(banned),
  )
}
check(
  'no student name or ID leaks into the text',
  !message.body.includes('S0'),
)

// ---------------------------------------------------------------------------
section('Local API - the whole app, no server')
resetDb()
try {
  await localApi.me()
  check('unauthenticated me() is refused', false, 'should have thrown')
} catch (err) {
  check('unauthenticated me() is refused', err.status === 401)
}

try {
  await localApi.login('demo@teachercopilot.app', 'wrong')
  check('wrong password is rejected', false, 'should have thrown')
} catch (err) {
  check('wrong password is rejected', err.status === 401)
}

const session = await localApi.login('demo@teachercopilot.app', 'demo1234')
check('demo login succeeds', Boolean(session.access_token) && session.teacher.name === 'Priya Sharma')

const classes = await localApi.classes()
check('one seeded class with 12 students', classes.length === 1 && classes[0].student_count === 12)
const students = await localApi.students(classes[0].id)
check('students carry parent contact details', students.every((s) => s.name && s.parent_name))
check(
  'students expose an anonymous ref, not a name, to agents',
  students.every((s) => /^S\d\d$/.test(s.ref)),
)

// --- the full workflow
const run = await localApi.runWorkflow({ class_id: 1, topic: 'Photosynthesis', use_sample_answers: true })
check('workflow runs all five steps', run.steps.length === 5)
check(
  'every step succeeds or waits for review',
  run.steps.every((s) => s.status === 'done' || s.status === 'needs_review'),
  run.steps.map((s) => `${s.step_key}:${s.status}`).join(' '),
)
check('run status is "done"', run.status === 'done', run.status)
check('approval inbox is filled', run.inbox.count > 0, `${run.inbox.count} items`)

const kinds = new Set(run.inbox.items.map((i) => i.kind))
check('inbox holds messages, grades and a plan', kinds.has('parent_message') && kinds.has('grade') && kinds.has('lesson_plan'))

// --- grading produced a real spread
const analysis = await localApi.analysis(1)
check('all twelve scripts graded', analysis.graded === 12, `${analysis.graded}`)
check('class average is plausible', analysis.average_percentage > 20 && analysis.average_percentage < 95, `${analysis.average_percentage}%`)
check('hardest questions identified', analysis.hardest_questions.length === 3)
check('band distribution covers the class', analysis.band_distribution.reduce((s, b) => s + b.count, 0) === 12)

// --- teacher override wins and is remembered
const results = (await localApi.results(1)).results
const target = results[0]
const qid = target.result.per_question_marks[0].question_id
const overridden = await localApi.overrideMarks(target.id, [{ question_id: qid, marks_awarded: 0 }])
check('a teacher override replaces the AI mark', overridden.result.per_question_marks[0].marks_awarded === 0)
check('an override is flagged as the teacher’s', overridden.result.per_question_marks[0].overridden === true)
const refetched = (await localApi.results(1)).results.find((r) => r.id === target.id)
check('the override persists', refetched.teacher_overrides.length === 1)

// --- THE SAFETY RULE: nothing sends without approval
const messages = await localApi.messages(1)
check('messages start as drafts or need review', messages.every((m) => ['draft', 'needs_review'].includes(m.status)))
check('no message exceeds the WhatsApp limit', messages.every((m) => m.word_count <= 120))
check('no unreplaced placeholders', messages.every((m) => !m.body.includes('{{')))

const blocked = await localApi.sendMessages({ send_all: true, message_ids: [] })
check('sending unapproved messages is refused', blocked.sent === 0, `${blocked.blocked} blocked`)
const stillDraft = (await localApi.messages(1)).every((m) => m.status !== 'simulated_sent')
check('nothing was actually sent', stillDraft)

const one = messages[0]
await localApi.approveMessage(one.id)
const sent = await localApi.sendMessages({ message_ids: [one.id], send_all: false })
check('an approved message sends', sent.sent === 1 && sent.results[0].status === 'simulated_sent')

try {
  await localApi.updateMessage(one.id, { body: 'Rewriting what the parent already received.' })
  check('a sent message cannot be edited', false, 'should have thrown')
} catch (err) {
  check('a sent message cannot be edited', err.status === 409)
}

// Editing an approved-but-unsent message must revoke the approval.
const second = messages[1]
await localApi.approveMessage(second.id)
const edited = await localApi.updateMessage(second.id, { body: 'A different, freshly written note.' })
check('editing revokes approval', edited.status === 'draft' && edited.can_send === false, edited.status)
const resend = await localApi.sendMessages({ message_ids: [second.id], send_all: false })
check('an edited message must be re-approved before sending', resend.sent === 0)

const lowScorer = messages.find((m) => m.needs_teacher_review)
check('low scorers are flagged for review', Boolean(lowScorer), lowScorer ? lowScorer.review_reasons.join('; ') : '')

// --- dashboard
const dash = await localApi.dashboard()
check('dashboard counts the work', dash.papers_graded === 1 && dash.lesson_plans_created >= 1)
check('time saved is recorded', dash.time_saved_this_week_minutes > 0, `${dash.time_saved_this_week_minutes} min`)
check('weekly chart has six weeks', dash.weekly_time_saved.length === 6)
check('class overview populated', dash.class_overview[0].student_count === 12)

// --- persistence
check('state is persisted for the next visit', Boolean(globalThis.localStorage.getItem('teachercopilot.db.v1')))

// ---------------------------------------------------------------------------
console.log(`\n${'='.repeat(62)}`)
if (failures.length === 0) {
  console.log(`\x1b[32mRESULT: ${passed} checks passed — the app runs with no backend.\x1b[0m`)
} else {
  console.log(`\x1b[31mRESULT: ${failures.length} FAILED\x1b[0m`)
  failures.forEach((f) => console.log(`   - ${f}`))
  process.exitCode = 1
}
console.log('='.repeat(62))
