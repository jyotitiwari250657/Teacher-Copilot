/**
 * The four agents, in plain JavaScript.
 *
 * These carry the same rules the Python agents do, and — importantly — the same
 * rules the *prompts* ask for:
 *   - lesson minutes must sum to the requested duration
 *   - exactly 3 exit tickets
 *   - MCQ is exact-match; subjective gets keyword partial credit
 *   - confidence below 0.6 forces a teacher-review flag
 *   - worksheets are 8-10 questions with a matching answer key
 *   - WhatsApp bodies are capped at 120 words
 *   - low score / low attendance flag a message for review
 *   - diagnostic and comparative wording is stripped
 */

export const CONFIDENCE_THRESHOLD = 0.6
export const WHATSAPP_WORD_LIMIT = 120
export const LOW_SCORE_THRESHOLD = 35
export const LOW_ATTENDANCE_THRESHOLD = 70

const hi = (en, hi_) => ({ English: en, Hindi: hi_ })
const pick = (text, language) => (language === 'Hindi' ? text.Hindi : text.English)

// ---------------------------------------------------------------------------
// Lesson Planner
// ---------------------------------------------------------------------------
const PHASES = [
  { key: 'hook', weight: 0.12 },
  { key: 'explain', weight: 0.25 },
  { key: 'activity', weight: 0.25 },
  { key: 'practice', weight: 0.18 },
  { key: 'assessment', weight: 0.12 },
  { key: 'recap', weight: 0.08 },
]

const MIN_PHASE_MINUTES = 3

/**
 * Largest-remainder split so the minutes always add up to the total exactly.
 *
 * Every phase is given a floor first, the remaining minutes are handed out by
 * weight, and the leftover (< the number of phases) is given one at a time to
 * the phases with the largest fractional remainder. The result is exact for any
 * total, which is the invariant the lesson planner promises.
 */
export function allocateMinutes(total) {
  const target = Math.max(1, Math.round(total))

  let phases = PHASES
  if (target < PHASES.length * MIN_PHASE_MINUTES) {
    // Too short for all six: keep the highest-weighted phases.
    const keep = Math.max(2, Math.floor(target / MIN_PHASE_MINUTES))
    phases = [...PHASES].sort((a, b) => b.weight - a.weight).slice(0, Math.min(keep, PHASES.length))
  }

  const count = phases.length
  // Cannot afford the full floor when the period is very short.
  const floorEach = target >= count * MIN_PHASE_MINUTES ? MIN_PHASE_MINUTES : 1
  const pool = target - count * floorEach

  const allocated = phases.map((phase) => ({
    key: phase.key,
    exact: phase.weight * pool,
    minutes: floorEach,
  }))
  allocated.forEach((phase) => {
    phase.minutes += Math.floor(phase.exact)
  })

  let remainder = target - allocated.reduce((sum, phase) => sum + phase.minutes, 0)
  const byRemainder = [...allocated]
    .map((phase, index) => ({ index, frac: phase.exact - Math.floor(phase.exact) }))
    .sort((a, b) => b.frac - a.frac)

  let cursor = 0
  while (remainder > 0 && byRemainder.length) {
    allocated[byRemainder[cursor % byRemainder.length].index].minutes += 1
    remainder -= 1
    cursor += 1
  }

  return allocated.map((phase) => ({ key: phase.key, minutes: phase.minutes }))
}

const PHASE_COPY = {
  hook: hi('Quick starter question to activate what students already know.', 'तुरंत शुरुआत करने वाला प्रश्न, जो पहले से ज्ञात ज्ञान जगाता है।'),
  explain: hi('Teacher-led explanation of the core idea, using the board.', 'बोर्ड का उपयोग करते हुए मुख्य विचार की शिक्षक-निर्देशित व्याख्या।'),
  activity: hi('Hands-on activity or demonstration students take part in.', 'हाथों से किया जाने वाला प्रदर्शन जिसमें विद्यार्थी भाग लेते हैं।'),
  practice: hi('Guided practice questions with peer checking.', 'साथी द्वारा जाँच के साथ निर्देशित अभ्यास प्रश्न।'),
  assessment: hi('Quick check to see what has been understood.', 'यह देखने के लिए त्वरित जाँच कि क्या समझ आया।'),
  recap: hi('Recap the key idea and preview the next lesson.', 'मुख्य विचार का सारांश और अगले पाठ का परिचय।'),
}

export function lessonPlanner({ subject = 'Science', topic, grade = '8', duration_minutes = 40, language = 'English' }) {
  const allocation = allocateMinutes(duration_minutes)
  const objectiveCopy = hi(
    [
      `Explain what ${topic} is and why it matters.`,
      `Describe the main steps in ${topic}.`,
      `Apply the idea of ${topic} to a new example.`,
    ],
    [
      `${topic} क्या है और यह क्यों महत्वपूर्ण है, यह समझाना।`,
      `${topic} के मुख्य चरणों का वर्णन करना।`,
      `${topic} के विचार को नए उदाहरण पर लागू करना।`,
    ],
  )

  return {
    title: `${topic} - ${subject} Lesson (${grade} class)`,
    learning_objectives: objectiveCopy[language] || objectiveCopy.English,
    lesson_flow: allocation.map(({ key, minutes }) => ({
      phase: key,
      minutes,
      description: (PHASE_COPY[key] || PHASE_COPY.explain)[language] || PHASE_COPY.explain.English,
    })),
    assessment_rubric: [
      { criterion: pick(hi('Correct understanding', 'सही समझ'), language), marks: 5 },
      { criterion: pick(hi('Clear explanation in own words', 'अपने शब्दों में स्पष्ट व्याख्या'), language), marks: 3 },
      { criterion: pick(hi('Diagram or labelled work', 'चित्र या लेबल किया गया कार्य'), language), marks: 2 },
    ],
    exit_ticket: [
      pick(hi(`Name one thing you learned about ${topic}.`, `${topic} के बारे में एक बात बताइए जो आपने सीखी।`), language),
      pick(hi('Write one question you still have.', 'एक प्रश्न लिखिए जो आपके मन में अभी है।'), language),
      pick(hi('Rate your confidence out of 3.', 'अपने आत्मविश्वास को 3 में से दें।'), language),
    ],
    homework: pick(
      hi(
        `Draw a labelled diagram related to ${topic} and write three sentences about it.`,
        `${topic} से संबंधित एक लेबलयुक्त चित्र बनाइए और उस पर तीन वाक्य लिखिए।`,
      ),
      language,
    ),
  }
}

// ---------------------------------------------------------------------------
// Grader
// ---------------------------------------------------------------------------
const STRICTNESS = { lenient: 1.15, standard: 1, strict: 0.88 }

function normalise(value) {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/^[\s(\[*]+/, '')
    .replace(/[\s)\].*]+$/, '')
}

function gradeObjective(question, given) {
  const key = String(question.answer_key ?? '').trim()
  const student = String(given ?? '').trim()

  // A blank answer is a certainty, not a guess: full confidence, no marks.
  if (!student) return { marks: 0, confidence: 0.95 }

  if (question.type === 'numeric') {
    const expected = parseFloat(key)
    const actual = parseFloat(student)
    if (Number.isNaN(expected) || Number.isNaN(actual)) return { marks: 0, confidence: 0.8 }
    const exact = Math.abs(expected - actual) < 0.51
    return { marks: exact ? question.marks : 0, confidence: exact ? 0.96 : 0.82 }
  }

  if (question.type === 'true_false') {
    const truthy = ['true', 'yes', 'correct', '1']
    const falsy = ['false', 'no', 'incorrect', '0']
    // Canonicalise both sides so "yes" matches a key of "True".
    const side = (value) => (truthy.includes(value) ? 'true' : falsy.includes(value) ? 'false' : null)
    const value = side(normalise(student))
    const expected = side(normalise(key))
    if (value === null) return { marks: 0, confidence: 0.45 }
    return { marks: value === expected ? question.marks : 0, confidence: 0.97 }
  }

  // MCQ: exact match, case and whitespace tolerant, letters included.
  if (normalise(student) === normalise(key)) return { marks: question.marks, confidence: 0.97 }

  // Some papers list lettered options; accept "B" for the keyed option.
  const options = question.options || []
  const letterIndex = options.findIndex((option) => normalise(option) === normalise(key))
  if (letterIndex >= 0) {
    const letter = String.fromCharCode(65 + letterIndex)
    if (normalise(student) === letter.toLowerCase()) return { marks: question.marks, confidence: 0.94 }
  }
  return { marks: 0, confidence: 0.92 }
}

const STOPWORDS = new Set([
  'the', 'a', 'an', 'is', 'are', 'was', 'were', 'of', 'and', 'to', 'in', 'it', 'for',
  'on', 'that', 'this', 'with', 'as', 'by', 'at', 'from', 'be', 'has', 'have', 'they',
])

/** Keyword-coverage partial credit - deliberately conservative. */
function gradeSubjective(question, given, strictness) {
  const model = normalise(question.model_answer)
  const answer = normalise(given)
  const max = question.marks

  if (!answer) return { marks: 0, confidence: 0.93 }
  if (answer === model) return { marks: max, confidence: 0.9 }

  const keywords = [
    ...new Set(
      model
        .split(/[^a-z0-9]+/)
        .filter((word) => word.length > 3 && !STOPWORDS.has(word)),
    ),
  ]
  if (keywords.length === 0) {
    return { marks: answer.length > 3 ? Math.round(max * 0.5 * 10) / 10 : 0, confidence: 0.55 }
  }

  const covered = keywords.filter((word) => answer.includes(word)).length
  const coverage = covered / keywords.length
  const lengthFactor = Math.min(1, answer.split(/\s+/).length / Math.max(6, keywords.length))
  const raw = coverage * 0.85 + lengthFactor * 0.15
  const marks = Math.max(0, Math.min(max, Math.round(raw * strictness * max * 10) / 10))

  // Short or keyword-thin answers are exactly where a human should look.
  const confidence = Math.min(0.93, 0.42 + coverage * 0.55)
  return { marks, confidence }
}

export function gradeSubmission({ questions, answers, student_ref, strictness = 'standard' }) {
  const factor = STRICTNESS[strictness] ?? 1
  const perQuestion = questions.map((question) => {
    const given = answers?.[question.id] ?? ''
    const { marks, confidence } =
      question.type === 'mcq' || question.type === 'true_false' || question.type === 'numeric'
        ? gradeObjective(question, given)
        : gradeSubjective(question, given, factor)

    return {
      question_id: question.id,
      marks_awarded: marks,
      max_marks: question.marks,
      feedback: feedbackFor(question, given, marks),
      confidence: Math.round(confidence * 100) / 100,
      overridden: false,
    }
  })

  const total = Math.round(perQuestion.reduce((sum, mark) => sum + mark.marks_awarded, 0) * 100) / 100
  const maxTotal = questions.reduce((sum, question) => sum + question.marks, 0)
  const flagged = perQuestion.filter((mark) => mark.confidence < CONFIDENCE_THRESHOLD)
  const percentages = perQuestion.map((mark) => (mark.max_marks ? mark.marks_awarded / mark.max_marks : 0))

  return {
    student_ref: student_ref || 'S01',
    per_question_marks: perQuestion,
    total,
    max_total: maxTotal,
    percentage: maxTotal ? Math.round((total / maxTotal) * 1000) / 10 : 0,
    needs_teacher_review: flagged.length > 0,
    low_confidence_questions: flagged.map((mark) => mark.question_id),
    overall_feedback: overallFeedback(total, maxTotal, flagged.length),
    strengths: strengthsFrom(perQuestion, questions),
    weaknesses: weaknessesFrom(perQuestion, questions),
  }
}

function feedbackFor(question, given, marks) {
  if (!String(given ?? '').trim()) return 'No answer was written for this question.'
  if (marks >= question.marks) return 'Correct. Well done.'
  if (marks > 0) return `Partly correct — ${marks} of ${question.marks} marks. Add the missing detail.`
  return 'Not correct. Re-read the question and revise this answer.'
}

function overallFeedback(total, maxTotal, flagged) {
  const pct = maxTotal ? Math.round((total / maxTotal) * 100) : 0
  const base =
    pct >= 80
      ? 'Strong work overall — the core idea is understood.'
      : pct >= 60
        ? 'A solid attempt. The main idea is there; a little more detail would lift the score.'
        : pct >= 40
          ? 'Several basics are in place, but key parts are missing. Let us revise this together.'
          : 'This topic needs more practice before moving on.'
  return flagged
    ? `${base} Some answers were scored with low confidence — please check the highlighted marks.`
    : base
}

function strengthsFrom(marks, questions) {
  const full = marks.filter((mark) => mark.marks_awarded >= mark.max_marks)
  if (full.length === 0) return ['Attempted every question']
  const byId = new Map(questions.map((q) => [q.id, q]))
  const subjective = full.find((mark) => byId.get(mark.question_id)?.type !== 'mcq')
  return subjective
    ? ['Explained the longer answers in full sentences']
    : [`Answered ${full.length} question${full.length === 1 ? '' : 's'} correctly`]
}

function weaknessesFrom(marks, questions) {
  const byId = new Map(questions.map((q) => [q.id, q]))
  const issues = new Set()
  marks.forEach((mark) => {
    const question = byId.get(mark.question_id)
    if (mark.marks_awarded >= mark.max_marks) return
    if (!String(mark.feedback).includes('No answer')) {
      if (question?.type === 'mcq' || question?.type === 'true_false') issues.add('Careless mistakes in objective questions')
      else issues.add('Longer answers are missing important detail')
    }
  })
  if (marks.some((mark) => mark.confidence < CONFIDENCE_THRESHOLD)) {
    issues.add('Handwriting or phrasing made some answers hard to read')
  }
  return [...issues].slice(0, 3)
}

// ---------------------------------------------------------------------------
// Differentiation
// ---------------------------------------------------------------------------
const LEVEL_COPY = {
  support: {
    what_changed: hi(
      'Same topic, shorter sentences and a labelled diagram to hold the answer.',
      'वही विषय, छोटे वाक्य और उत्तर याद रखने के लिए एक लेबलयुक्त चित्र।',
    ),
    content: hi(
      'Leaves make food. Sunlight, water and carbon dioxide come together inside a leaf to make glucose, and oxygen is released.',
      'पत्ते भोजन बनाते हैं। सूर्य प्रकाश, पानी और कार्बन डाइऑक्साइड पत्ते के अंदर मिलकर ग्लूकोज़ बनाते हैं और ऑक्सीज़ निकलती है।',
    ),
    keyPoints: [
      hi('Leaves are the kitchen of the plant', 'पत्ते पौधे का रसोई हैं'),
      hi('Sunlight is the fuel', 'सूर्य प्रकाश ईंधन है'),
      hi('Oxygen goes out through the stomata', 'ऑक्सीज़ रंध्रों से बाहर जाती है'),
    ],
    scaffolds: [
      hi('Every sentence has fewer than 12 words', 'हर वाक्य 12 शब्दों से कम है'),
      hi('One labelled diagram beside every answer', 'हर उत्तर के साथ एक लेबलयुक्त चित्र'),
      hi('Word bank given at the top of the sheet', 'पत्रक के शीर्ष पर शब्द भंडार दिया गया है'),
    ],
  },
  core: {
    what_changed: hi(
      'Full explanation with labelled steps, and questions that need one clear reason each.',
      'पूर्ण व्याख्या और चरणों के साथ, तथा ऐसे प्रश्न जिनका उत्तर एक स्पष्ट कारण देता है।',
    ),
    content: hi(
      'Photosynthesis is the process by which green plants use sunlight energy to combine carbon dioxide and water into glucose, releasing oxygen.',
      'प्रकाश संश्लेषण वह प्रक्रिया है जिसमें हरे पौधे सूर्य ऊर्जा का उपयोग करके कार्बन डाइऑक्साइड और पानी से ग्लूकोज़ बनाते हैं और ऑक्सीज़ छोड़ते हैं।',
    ),
    keyPoints: [
      hi('Chlorophyll traps the light', 'क्लोरोफिल प्रकाश को पकड़ता है'),
      hi('Glucose stores the energy', 'ग्लूकोज़ ऊर्जा संग्रह करता है'),
      hi('Plants are the base of every food chain', 'पौधे हर आहार शृंखला के आधार हैं'),
    ],
    scaffolds: [
      hi('Flow diagram for the process', 'प्रक्रिया का प्रवाह आरेख'),
      hi('Model answer available for one question', 'एक प्रश्न के लिए आदर्श उत्तर दिया गया है'),
    ],
  },
  extension: {
    what_changed: hi(
      'Same content, but questions ask for a limitation, an exception and an original argument.',
      'वही सामग्री, पर प्रश्न सीमाओं, अपवाद और मौलिक तर्क पर केंद्रित हैं।',
    ),
    content: hi(
      'Photosynthesis converts light energy into chemical energy stored in glucose. Rate depends on light intensity, carbon dioxide concentration and temperature.',
      'प्रकाश संश्लेषण प्रकाश ऊर्जा को ग्लूकोज़ में संचित रासायनिक ऊर्जा में बदलता है। इसकी दर प्रकाश की तीव्रता, कार्बन डाइऑक्साइड की सांद्रता और तापमान पर निर्भर करती है।',
    ),
    keyPoints: [
      hi('Limiting factors control the rate', 'सीमित कारक दर को नियंत्रित करते हैं'),
      hi('Energy is conserved, only transformed', 'ऊर्जा नष्ट नहीं होती, केवल बदलती है'),
      hi('Compare C3 and C4 pathways', 'C3 और C4 मार्गों की तुलना करें'),
    ],
    scaffolds: [
      hi('Data table to interpret', 'व्याख्या के लिए आँकड़ा तालिका'),
      hi('Extension reading list', 'विस्तारित अध्ययन सूची'),
    ],
  },
}

const WORKSHEETS = {
  support: [
    ['Tick the part of the plant that traps sunlight.', 'One word answer.'],
    ['Circle the gas that leaves the leaf.', 'One word answer.'],
    ['Fill in the blank: plants make their food in the _____.', ''],
    ['Write the two things a leaf needs to make food.', 'Number 1 and 2.'],
    ['Draw a leaf and label it.', 'Label at least two parts.'],
    ['True or false: leaves are green because of chlorophyll.', ''],
    ['Name the tiny pores found on a leaf.', 'One word answer.'],
    ['Write one sentence: why do we need plants?', ''],
    ['Circle the correct word: plants give out oxygen or carbon dioxide.', ''],
  ],
  core: [
    ['State the word equation for photosynthesis.', 'Include both gases.'],
    ['Explain why leaves are green in colour.', 'Two marks for a full sentence pair.'],
    ['Name two conditions needed for photosynthesis.', 'Name them clearly.'],
    ['Describe how oxygen reaches the outside of the leaf.', 'Use the word stomata.'],
    ['Why do you think plants are called producers?', 'One clear reason.'],
    ['Explain the role of chlorophyll.', 'Two marks.'],
    ['What happens to the glucose after it is made?', 'Two marks.'],
    ['Differentiate between respiration and photosynthesis.', 'Any two correct points.'],
    ['A plant is kept in a dark cupboard for a week. What happens to it?', 'Explain your answer.'],
  ],
  extension: [
    [
      'A farmer grows a crop under a polyhouse and adds carbon dioxide. Explain the expected effect on yield.',
      'Refer to the limiting factor principle.',
    ],
    ['Discuss why photosynthesis is described as an endothermic process.', 'Minimum three points.'],
    ['Compare and contrast photosynthesis in C3 and C4 plants.', 'Use a table if helpful.'],
    [
      'Evaluate the statement: "All the energy in a plant comes from the sun."',
      'Give at least one counter-example.',
    ],
    [
      'Suggest why aquatic plants that live in deep water are green rather than red.',
      'Relate to light wavelengths.',
    ],
    ['Explain how a change in temperature affects the rate of photosynthesis.', 'Name the enzyme involved.'],
    ['Assess the claim that plants respire only at night.', 'Provide evidence both ways.'],
    [
      'Design an experiment to show the effect of light intensity on the rate of photosynthesis.',
      'State the independent and dependent variables.',
    ],
    ['Discuss the ecological consequences of a fall in plant photosynthesis.', 'At least four points.'],
  ],
}

const ANSWER_KEYS = {
  support: [
    'Leaf', 'Oxygen', 'leaf', 'Sunlight and water (either order)', 'A drawing of a leaf labelled with blade and vein.',
    'True', 'Stomata', 'Any sensible sentence about food or oxygen.', 'oxygen',
  ],
  core: [
    'Carbon dioxide + water —(sunlight, chlorophyll)→ glucose + oxygen.',
    'Leaves contain chlorophyll, a green pigment that traps sunlight; its green colour masks other colours.',
    'Sunlight and carbon dioxide (water and chlorophyll also correct).',
    'Oxygen diffuses out through the stomata, which are the tiny pores on the leaf surface.',
    'They make their own food using sunlight instead of eating other organisms.',
    'Chlorophyll is the pigment that absorbs and traps light energy for the reaction.',
    'It is used for growth and respiration, and some is stored as starch.',
    'Respiration breaks down glucose for energy all the time; photosynthesis stores energy from light.',
    'It becomes pale and weak, because without light it cannot make food and depends on stored food.',
  ],
  extension: [
    'Yield rises, because carbon dioxide was a limiting factor; once it is abundant, another factor caps the rate.',
    'It needs light energy to break water and join carbon dioxide, so energy is absorbed from the surroundings.',
    'C4 plants fix carbon into a 4-carbon acid first, so they work efficiently in high light and heat; C3 plants fix directly and photorespire.',
    'Not entirely — plants also store chemical energy from soil minerals and from chemosynthetic organisms in food chains.',
    'Green chlorophyll absorbs red and blue light strongly; at depth only blue-green wavelengths reach, favouring those pigments.',
    'The rate rises to an optimum and then falls, because the enzymes involved denature once it gets too hot.',
    'The claim is false — plants respire in daylight as well, using some of the glucose they have just made.',
    'Vary the distance from a lamp (independent), measure oxygen output or bubble rate (dependent), and control temperature.',
    'Less glucose enters the food chain, herbivore populations fall, and carbon already in the atmosphere stays there longer.',
  ],
}

export function differentiate({ topic, language = 'English', performance = [], manual_levels = {} }) {
  const copy = (key) => {
    const entry = LEVEL_COPY[key]
    const whatChanged = pick(entry.what_changed, language)
    const content = pick(entry.content, language)
    const points = entry.keyPoints.map((pair) => pick(pair, language))
    const scaffolds = entry.scaffolds.map((pair) => pick(pair, language))
    const rawQuestions = WORKSHEETS[key]
    const worksheet = rawQuestions.map(([question, hint], index) => ({
      id: `${key[0].toUpperCase()}${index + 1}`,
      question: key === 'support' && language === 'Hindi' ? question : question,
      hint,
    }))
    return {
      level: key,
      what_changed: whatChanged,
      content,
      key_points: points,
      scaffolds,
      worksheet,
      answer_key: worksheet.map((question, index) => ({
        question_id: question.id,
        answer: ANSWER_KEYS[key][index],
      })),
    }
  }

  const groups = { support: [], core: [], extension: [] }
  performance.forEach((entry) => {
    const level = manual_levels[entry.student_ref] || levelFor(entry.percentage)
    if (groups[level]) groups[level].push(entry.student_ref)
  })

  const learningObjective = pick(
    hi(
      `Explain what ${topic} is and describe the main steps involved.`,
      `${topic} क्या है और इसमें शामिल मुख्य चरणों का वर्णन करें।`,
    ),
    language,
  )

  return {
    topic,
    learning_objective: learningObjective,
    support: copy('support'),
    core: copy('core'),
    extension: copy('extension'),
    groupings: [
      { level: 'support', student_refs: groups.support, rationale: 'Below 40% — scaffolded access.' },
      { level: 'core', student_refs: groups.core, rationale: '40-75% — on grade level.' },
      { level: 'extension', student_refs: groups.extension, rationale: 'Above 75% — stretch questions.' },
    ],
    grouping_rationale: pick(
      hi(
        'Suggested from your marked papers. Groups are a starting point — move anyone you disagree with.',
        'आपकी चिह्नित कागज़पत्रों से सुझाया गया। समूह केवल शुरुआती सुझाव हैं — जिसे आप सहमत न हों, उसे हटा दें।',
      ),
      language,
    ),
  }
}

export function levelFor(percentage) {
  if (percentage < 40) return 'support'
  if (percentage <= 75) return 'core'
  return 'extension'
}

// ---------------------------------------------------------------------------
// Parent Update
// ---------------------------------------------------------------------------
const FORBIDDEN = [
  [/\bslow learner\b/gi, 'needs more practice'],
  [/\bdyslex(ic|a)\b/gi, 'is still learning to read fluently'],
  [/\badhd\b/gi, 'is working on concentration'],
  [/\bautis(tic|m)\b/gi, 'is learning at their own pace'],
  [/\bcareless\b/gi, 'forgets some details'],
  [/\billiterate\b/gi, 'is still building reading fluency'],
  [/\bdumb\b/gi, 'is still developing'],
  [/\bstupid\b/gi, 'is still developing'],
  [/\blazy\b/gi, 'needs a reminder to begin work'],
  [/other students[^.]*\./gi, ''],
  [/\bcompared to (others|peers|classmates)\b[^.]*\./gi, ''],
  [/\bbetter than (others|peers|classmates)\b[^.]*\./gi, ''],
  [/\bin (my|our) class\b[^.]*\./gi, ''],
]

/** Strip diagnostic and comparative wording, then tidy the grammar. */
export function sanitise(text) {
  let out = String(text ?? '')
  // Repair "He is careless" -> "He is forgets some details" before the bare form.
  out = out.replace(/\b(is|are)\s+(careless|lazy|dumb|stupid|slow)\b/gi, (match, verb, word) =>
    word.toLowerCase() === 'lazy' ? `${verb} ${'needs a reminder to begin work'}` : `${verb} ${'needs more practice'}`,
  )
  FORBIDDEN.forEach(([pattern, replacement]) => {
    out = out.replace(pattern, replacement)
  })
  return out
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/\s+([.,!?])/g, '$1')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

export function flagSensitive(percentage, attendance) {
  const reasons = []
  if (percentage !== undefined && percentage !== null && percentage < LOW_SCORE_THRESHOLD) {
    reasons.push('Mark is below 35% — please read this one carefully before sending.')
  }
  if (attendance !== undefined && attendance !== null && attendance < LOW_ATTENDANCE_THRESHOLD) {
    reasons.push('Attendance is below 70% — mention it supportively.')
  }
  return reasons
}

function wordCount(text) {
  return String(text).trim().split(/\s+/).filter(Boolean).length
}

function truncateWords(text, limit) {
  const words = String(text).trim().split(/\s+/)
  if (words.length <= limit) return text.trim()
  return `${words.slice(0, limit).join(' ').replace(/[.,;]$/, '')}.`
}

const PARENT_COPY = {
  strong: hi(
    'attends every class carefully and attempts each question with confidence',
    'हर कक्षा में ध्यान से उपस्थित होते हैं और प्रत्येक प्रश्न का आत्मविश्वास से उत्तर देते हैं',
  ),
  average: hi(
    'puts in steady effort and has understood the main idea of the topic',
    'निरंतर प्रयास करते हैं और विषय का मुख्य विचार समझ लिया है',
  ),
  weak: hi(
    'attends regularly and has completed all the work for this unit',
    'नियमित रूप से उपस्थित होते हैं और इस इकाई का सारा कार्य पूरा किया है',
  ),
}

const IMPROVE = hi(
  'One thing to work on: writing longer, more complete answers in the subjective questions.',
  'एक बात पर ध्यान दें: गैर-वस्तुनिष्ठ प्रश्नों में लंबे और पूर्ण उत्तर लिखना।',
)

const HOME_STEP = hi(
  'At home, you could ask them to explain one part of this topic to you in their own words.',
  'घर पर, आप उनसे इस विषय का एक भाग अपने शब्दों में समझाने को कह सकते हैं।',
)

export function parentUpdate({ student_name, subject = 'Science', overall_percentage = 0, attendance_pct = 0, tone = 'warm', language = 'English', channel = 'whatsapp', teacher_note = '' }) {
  const band = overall_percentage >= 75 ? 'strong' : overall_percentage >= 50 ? 'average' : 'weak'
  const reasons = flagSensitive(overall_percentage, attendance_pct)

  const positive = pick(
    band === 'strong' ? PARENT_COPY.strong : band === 'average' ? PARENT_COPY.average : PARENT_COPY.weak,
    language,
  )
  const improve = pick(IMPROVE, language)
  const homeStep = pick(HOME_STEP, language)

  let body
  if (channel === 'email') {
    body = [
      `Dear parent,`,
      ``,
      `This is a short update about ${student_name} in ${subject}.`,
      ``,
      `What went well: ${student_name} ${positive}.`,
      ``,
      improve,
      ``,
      homeStep,
      ``,
      teacher_note ? `Note from the teacher: ${teacher_note}` : `Please reply if you would like to talk about this.`,
      ``,
      `Warm regards,`,
      `Class Teacher`,
    ].join('\n')
  } else {
    body = [
      `Dear parent, a quick update on ${student_name}.`,
      `Well done: ${student_name} ${positive}.`,
      improve,
      homeStep,
      `Thank you,`,
      `Class Teacher`,
    ].join(' ')
  }

  body = sanitise(body)

  let subject_line = ''
  if (channel === 'email') {
    subject_line = pick(
      hi(
        `A quick update on ${student_name}'s progress in ${subject}`,
        `${student_name} की ${subject} में प्रगति पर एक छोटा अद्यतन`,
      ),
      language,
    )
  }

  if (channel === 'whatsapp') body = truncateWords(body, WHATSAPP_WORD_LIMIT)

  const count = wordCount(body)
  if (count > WHATSAPP_WORD_LIMIT) {
    reasons.push('Message was shortened to fit the WhatsApp limit — please check it reads well.')
  }

  return {
    student_ref: '',
    channel,
    language,
    tone,
    subject_line,
    body,
    word_count: count,
    positive_observation: sanitise(`${student_name} ${positive}.`),
    area_to_improve: sanitise(improve),
    home_step: sanitise(homeStep),
    needs_teacher_review: reasons.length > 0,
    review_reasons: reasons,
  }
}

export const AGENTS = { lessonPlanner, gradeSubmission, differentiate, parentUpdate }
