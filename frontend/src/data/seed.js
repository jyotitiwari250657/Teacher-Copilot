/**
 * Seed content for the standalone (no-backend) build.
 *
 * Mirrors the demo dataset the FastAPI backend seeds, so the app tells the same
 * story either way: one class, twelve students, a Photosynthesis paper and a set
 * of answer scripts in three ability tiers.
 */

export const TEACHER = {
  id: 1,
  name: 'Priya Sharma',
  email: 'demo@teachercopilot.app',
  school_name: 'Delhi Public School',
  subject: 'Science',
  preferred_language: 'English',
  default_tone: 'warm',
}

/** 10 questions, 16 marks. */
export const QUESTIONS = [
  {
    id: 'Q1',
    question: 'Which part of the plant absorbs sunlight?',
    marks: 1,
    type: 'mcq',
    options: ['Root', 'Leaf', 'Stem', 'Flower'],
    answer_key: 'Leaf',
  },
  {
    id: 'Q2',
    question: 'The green pigment present in leaves is called',
    marks: 1,
    type: 'mcq',
    options: ['Haemoglobin', 'Chlorophyll', 'Melanin', 'Keratin'],
    answer_key: 'Chlorophyll',
  },
  {
    id: 'Q3',
    question: 'Which gas is released during photosynthesis?',
    marks: 1,
    type: 'mcq',
    options: ['Oxygen', 'Nitrogen', 'Carbon dioxide', 'Hydrogen'],
    answer_key: 'Oxygen',
  },
  {
    id: 'Q4',
    question: 'The tiny pores on the surface of a leaf are called',
    marks: 1,
    type: 'mcq',
    options: ['Veins', 'Stomata', 'Sepals', 'Petals'],
    answer_key: 'Stomata',
  },
  {
    id: 'Q5',
    question: 'The main food made by photosynthesis is',
    marks: 1,
    type: 'mcq',
    options: ['Protein', 'Glucose', 'Fat', 'Vitamin C'],
    answer_key: 'Glucose',
  },
  {
    id: 'Q6',
    question: 'Photosynthesis takes place only inside the chloroplasts.',
    marks: 1,
    type: 'true_false',
    answer_key: 'True',
  },
  {
    id: 'Q7',
    question: 'Write the word equation for photosynthesis.',
    marks: 2,
    type: 'short',
    model_answer:
      'Carbon dioxide plus water, in the presence of sunlight and chlorophyll, gives glucose plus oxygen.',
  },
  {
    id: 'Q8',
    question: 'Explain why most leaves are green in colour.',
    marks: 3,
    type: 'long',
    model_answer:
      'Leaves contain chlorophyll, a green pigment that traps sunlight. The green colour of chlorophyll masks the other colours, so leaves look green.',
  },
  {
    id: 'Q9',
    question: 'Name two conditions necessary for photosynthesis.',
    marks: 2,
    type: 'short',
    model_answer: 'Sunlight and carbon dioxide. Water and chlorophyll are also required.',
  },
  {
    id: 'Q10',
    question: 'Explain how a plant makes its own food, and why this matters.',
    marks: 3,
    type: 'long',
    model_answer:
      'Using sunlight, chlorophyll traps light energy. This energy splits water and joins carbon dioxide to make glucose and oxygen. It matters because plants are the base of every food chain.',
  },
]

export const TOTAL_MARKS = QUESTIONS.reduce((sum, q) => sum + q.marks, 0)

/** name, roll, parent, phone, email, language, attendance, tier */
const ROSTER = [
  ['Aarav Sharma', 1, 'Mr. Sharma', '+919810000101', 'aarav.parent@example.com', 'English', 96, 'strong'],
  ['Diya Patel', 2, 'Mrs. Patel', '+919810000102', 'diya.parent@example.com', 'Hindi', 92, 'strong'],
  ['Vihaan Mehta', 3, 'Mr. Mehta', '+919810000103', 'vihaan.parent@example.com', 'English', 88, 'strong'],
  ['Ananya Iyer', 4, 'Mrs. Iyer', '+919810000104', 'ananya.parent@example.com', 'English', 95, 'strong'],
  ['Kabir Singh', 5, 'Mr. Singh', '+919810000105', 'kabir.parent@example.com', 'Hindi', 85, 'average'],
  ['Sara Khan', 6, 'Mrs. Khan', '+919810000106', 'sara.parent@example.com', 'Hindi', 90, 'strong'],
  ['Ishaan Verma', 7, 'Mr. Verma', '+919810000107', 'ishaan.parent@example.com', 'English', 68, 'weak'],
  ['Rohan Gupta', 8, 'Mr. Gupta', '+919810000108', 'rohan.parent@example.com', 'English', 82, 'average'],
  ['Meera Nair', 9, 'Mrs. Nair', '+919810000109', 'meera.parent@example.com', 'English', 94, 'strong'],
  ['Arjun Reddy', 10, 'Mr. Reddy', '+919810000110', 'arjun.parent@example.com', 'English', 78, 'average'],
  ['Zoya Ali', 11, 'Mrs. Ali', '+919810000111', 'zoya.parent@example.com', 'Hindi', 71, 'average'],
  ['Ira Menon', 12, 'Mrs. Menon', '+919810000112', 'ira.parent@example.com', 'English', 60, 'weak'],
]

export const STUDENTS = ROSTER.map(
  ([name, roll_no, parent_name, parent_phone, parent_email, preferred_language, attendance_pct, tier], i) => ({
    id: i + 1,
    class_id: 1,
    ref: `S${String(i + 1).padStart(2, '0')}`,
    name,
    roll_no,
    parent_name,
    parent_phone,
    parent_email,
    preferred_language,
    attendance_pct,
    notes: '',
    tier,
  }),
)

export const CLASSES = [
  {
    id: 1,
    name: 'Class 8-B',
    grade: '8',
    subject: 'Science',
    board: 'CBSE',
    teacher_id: 1,
    student_count: STUDENTS.length,
  },
]

// --- answer scripts, one per ability tier ---------------------------------
const ANSWERS = {
  strong: {
    Q1: 'Leaf',
    Q2: 'Chlorophyll',
    Q3: 'Oxygen',
    Q4: 'Stomata',
    Q5: 'Glucose',
    Q6: 'True',
    Q7: 'Carbon dioxide plus water in sunlight gives glucose plus oxygen.',
    Q8: 'Leaves contain chlorophyll, a green pigment that traps sunlight energy. The green of chlorophyll hides the other colours in the leaf, so leaves look green.',
    Q9: 'Sunlight and carbon dioxide are needed. Water and chlorophyll are also necessary.',
    Q10: 'Chlorophyll in the leaf traps sunlight. The light energy splits water into hydrogen and oxygen, and joins carbon dioxide to make glucose. Plants are the base of every food chain, so this process feeds almost all life on earth.',
  },
  average: {
    Q1: 'Leaf',
    Q2: 'Chlorophyll',
    Q3: 'Oxygen',
    Q4: 'Stomata',
    Q5: 'Glucose',
    Q6: 'True',
    Q7: 'Water and carbon dioxide make glucose and oxygen in sunlight.',
    Q8: 'Leaves are green because they have chlorophyll. Chlorophyll traps sunlight.',
    Q9: 'Sunlight and water.',
    Q10: 'Plants use sunlight to make food. This food is used by animals and humans.',
  },
  weak: {
    Q1: 'Leaf',
    Q2: 'Chlorophyll',
    Q3: 'Oxygen',
    Q4: 'Veins',
    Q5: 'Glucose',
    Q6: 'True',
    Q7: 'Sunlight makes food.',
    Q8: 'Because of chlorophyll.',
    Q9: 'Sunlight',
    Q10: 'Plants make their own food in leaves.',
  },
}

/** Spread the tiers across the roster so the class has a realistic spread. */
const TIER_CYCLE = [
  'strong', 'strong', 'average', 'strong', 'average', 'strong',
  'weak', 'average', 'strong', 'average', 'average', 'weak',
]

export const SUBMISSIONS = STUDENTS.map((student, index) => ({
  student_id: student.id,
  student_name: student.name,
  student_ref: student.ref,
  answers: { ...ANSWERS[TIER_CYCLE[index]] },
}))
