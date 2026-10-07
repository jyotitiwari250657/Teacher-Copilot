/**
 * API surface for the app.
 *
 * TeacherCopilot runs standalone in the browser: state lives in localStorage and
 * the agents run in `local.js`, so there is no backend to start. The exported
 * names deliberately match the HTTP client the pages were written against, so
 * nothing else in the app needs to know.
 */
import { localApi, getToken, setToken, ApiError, buildLessonDoc, buildWorksheetDoc, loadDb, resetDb } from './local.js'

export const api = localApi
export { getToken, setToken, ApiError, buildLessonDoc, buildWorksheetDoc, loadDb, resetDb }

/** Generate a document for `plan` (a lesson) or `material` + `level` (a worksheet). */
export function documentFor({ plan, material, level, includeAnswers }) {
  if (plan) return buildLessonDoc(plan, loadDb().teacher)
  if (material && level) return buildWorksheetDoc(material, level, includeAnswers !== false)
  throw new Error('Nothing to export.')
}
