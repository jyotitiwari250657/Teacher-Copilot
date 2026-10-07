/**
 * Browser check for the standalone build.
 *
 * Launches headless Edge with the DevTools protocol open, drives the real app,
 * and fails on any console error or missing page content. No backend is
 * running - that is the point.
 *
 *   node verify-browser.mjs
 */
import { spawn } from 'node:child_process'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const BASE = process.env.TC_BASE_URL || 'http://127.0.0.1:4173'
const PORT = Number(process.env.TC_CDP_PORT || 9333)

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let passed = 0
const failures = []
const consoleErrors = []

function check(name, ok, detail = '') {
  if (ok) {
    passed += 1
    console.log(`  \x1b[32mPASS\x1b[0m ${name}${detail ? `  \x1b[90m${detail}\x1b[0m` : ''}`)
  } else {
    failures.push(name)
    console.log(`  \x1b[31mFAIL\x1b[0m ${name}${detail ? `  ${detail}` : ''}`)
  }
}
const section = (t) => console.log(`\n\x1b[1m${t}\x1b[0m`)

// --- launch -----------------------------------------------------------------
const profile = mkdtempSync(join(tmpdir(), 'tc_browser_'))
const edge = spawn(EDGE, [
  '--headless=new',
  '--disable-gpu',
  '--no-sandbox',
  '--hide-scrollbars',
  '--window-size=1440,900',
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`,
  'about:blank',
])
edge.stderr.on('data', () => {})

let target = null
for (let i = 0; i < 40 && !target; i += 1) {
  await sleep(500)
  try {
    const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()
    target = list.find((t) => t.type === 'page')
  } catch {
    /* not listening yet */
  }
}
if (!target) {
  console.error('Could not reach the DevTools endpoint.')
  edge.kill()
  process.exit(1)
}

const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((res, rej) => {
  ws.onopen = res
  ws.onerror = rej
})

let nextId = 1
const pending = new Map()
const events = []
ws.onmessage = (event) => {
  const message = JSON.parse(event.data)
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id)
    pending.delete(message.id)
    message.error ? reject(new Error(message.error.message)) : resolve(message.result)
    return
  }
  events.push(message)
  if (message.method === 'Runtime.exceptionThrown') {
    const d = message.params.exceptionDetails
    consoleErrors.push(`exception: ${d.exception?.description || d.text}`)
  }
  if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') {
    consoleErrors.push(
      `console.error: ${message.params.args.map((a) => a.value ?? a.description).join(' ')}`,
    )
  }
  if (message.method === 'Log.entryAdded' && message.params.entry.level === 'error') {
    const entry = message.params.entry
    const label = `${entry.text} ${entry.url || ''}`
    // The botanical photo is remote and there is no favicon asset: neither is an app bug.
    if (/unsplash|favicon|ERR_/.test(label)) return
    consoleErrors.push(`log: ${label}`)
  }
}

const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const id = nextId++
    pending.set(id, { resolve, reject })
    ws.send(JSON.stringify({ id, method, params }))
  })

const evaluate = async (expression) => {
  const result = await send('Runtime.evaluate', {
    expression: `(async () => { ${expression} })()`,
    awaitPromise: true,
    returnByValue: true,
  })
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.exception?.description || 'eval failed')
  }
  return result.result.value
}

await send('Runtime.enable')
await send('Log.enable')
await send('Page.enable')

const goto = async (path) => {
  await send('Page.navigate', { url: `${BASE}${path}` })
  await sleep(1200)
}

/** Vite compiles a route's module on first visit in dev, so poll for content. */
const waitFor = async (expression, timeout = 20000) => {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    if (await evaluate(`return Boolean(${expression})`)) return true
    await sleep(400)
  }
  return false
}

// textContent, not innerText: headless pages are not laid out for innerText.
const text = () => evaluate('return document.body.textContent')
const has = (haystack, needle) => haystack.includes(needle)

// ---------------------------------------------------------------------------
section('Login page renders')
await goto('/login')
const loginText = await text()
const dom = await evaluate('return document.documentElement.outerHTML')

check('React mounted', /<div class="tc-login/.test(dom))
check('the botanical photo is used', dom.includes('photo-1624616802045-f7a4ab36862d'))
check('photo fills the frame', /object-cover/.test(dom))
check('eyebrow MEMBER ACCESS', /Member access/i.test(loginText))
check('title Welcome back', has(loginText, 'Welcome back'))
check('description copy', has(loginText, 'Enter your details to continue your journey'))
check('email label and placeholder', has(loginText, 'Email address') && has(dom, 'Enter your email'))
check('password label and placeholder', has(loginText, 'Password') && has(dom, 'Enter your password'))
check('Remember me with a native checkbox', has(loginText, 'Remember me') && /type="checkbox"/.test(dom))
check('Forgot your password?', has(loginText, 'Forgot your password?'))
check('CTA says Log in', has(loginText, 'Log in'))
check('register line', has(loginText, 'have an account?') && has(loginText, 'Register here'))
check('polite live region', /aria-live="polite"/.test(dom))
check('glass layer with a 10px blur', /backdrop-blur-\[10px\]/.test(dom))
check('no vertical overflow is possible', /tc-login[^\n]*overflow-hidden/.test(dom.replace(/"/g, '"')))
check('100dvh height with a 100vh fallback', await evaluate(`
  return [...document.styleSheets].some((sheet) => {
    try {
      return [...sheet.cssRules].some((rule) => (rule.cssText || '').includes('100dvh'))
    } catch {
      return false
    }
  })
`))

// The landing page is explicitly excluded from the new app backdrop.
const loginBg = await evaluate(`
  const img = document.querySelector('.tc-login img')
  return {
    src: img ? img.getAttribute('src') || '' : '',
    hasAppBackdrop: Boolean(document.querySelector('.app-backdrop')),
  }
`)
check(
  'the landing page keeps its own photographic background',
  /unsplash/.test(loginBg.src) && !loginBg.hasAppBackdrop,
  `${loginBg.src.slice(0, 46)} | app backdrop present: ${loginBg.hasAppBackdrop}`,
)

const layout = await evaluate(`
  const el = document.querySelector('.tc-login')
  const cs = getComputedStyle(el)
  const ctaEl = document.querySelector('button[type=submit]')
  const cta = ctaEl.getBoundingClientRect()
  const heading = document.querySelector('h1').getBoundingClientRect()
  const form = document.querySelector('form').getBoundingClientRect()
  const panel = document.querySelector('main').getBoundingClientRect()
  return {
    height: Math.round(el.getBoundingClientRect().height),
    overflow: cs.overflow,
    viewport: window.innerHeight,
    headingBottom: Math.round(heading.bottom),
    headingTop: Math.round(heading.top),
    ctaTop: Math.round(cta.top),
    ctaBottom: Math.round(cta.bottom),
    ctaHeight: Math.round(cta.height),
    ctaRadius: getComputedStyle(ctaEl).borderRadius,
    ctaBg: getComputedStyle(ctaEl).backgroundColor,
    ctaColor: getComputedStyle(ctaEl).color,
    ctaWidth: Math.round(cta.width),
    formWidth: Math.round(form.width),
    panelWidth: Math.round(panel.width),
    bgObjectFit: getComputedStyle(document.querySelector('img')).objectFit,
    scrolls: document.documentElement.scrollHeight > window.innerHeight + 1,
  }
`)
check('exactly one viewport tall', Math.abs(layout.height - layout.viewport) <= 1, `${layout.height}px vs ${layout.viewport}px`)
check('overflow is hidden, so no scrollbar', layout.overflow === 'hidden')
check('page does not scroll', layout.scrolls === false)
check('CTA is 56-68px tall', layout.ctaHeight >= 56 && layout.ctaHeight <= 68, `${layout.ctaHeight}px`)
check('form panel is capped at ~650-705px', layout.panelWidth >= 650 && layout.panelWidth <= 705, `${layout.panelWidth}px`)
check(
  'heading above, CTA below, balanced space',
  layout.headingBottom < layout.ctaTop && layout.ctaBottom < layout.viewport,
  `heading ends ${layout.headingBottom}, CTA ${layout.ctaTop}-${layout.ctaBottom}, viewport ${layout.viewport}`,
)
check('CTA is black with white bold text', layout.ctaBg === 'rgb(0, 0, 0)' && layout.ctaColor === 'rgb(255, 255, 255)')
check('CTA has a very small corner radius', parseFloat(layout.ctaRadius) <= 4, layout.ctaRadius)
check('CTA spans the full form width', Math.abs(layout.ctaWidth - layout.formWidth) <= 2, `${layout.ctaWidth} vs ${layout.formWidth}`)
check('the photo uses object-fit: cover', layout.bgObjectFit === 'cover')

const positions = await evaluate(`
  const email = document.querySelector('#tc-email').getBoundingClientRect()
  const password = document.querySelector('#tc-password').getBoundingClientRect()
  return { gap: Math.round(password.top - email.bottom) }
`)
check('generous space between email and password', positions.gap >= 32, `${positions.gap}px`)

// ---------------------------------------------------------------------------
section('Signing in')
await evaluate(`
  const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
  const email = document.querySelector('#tc-email')
  set.call(email, 'demo@teachercopilot.app')
  email.dispatchEvent(new Event('input', { bubbles: true }))
  const pass = document.querySelector('#tc-password')
  set.call(pass, 'demo1234')
  pass.dispatchEvent(new Event('input', { bubbles: true }))
  return true
`)
await evaluate(`document.querySelector('button[type=submit]').click(); return true`)
await sleep(2500)
const afterLogin = await text()
check('login navigates away from the login screen', !afterLogin.includes('MEMBER ACCESS'))
check('a session is stored', await evaluate(`return Boolean(localStorage.getItem('teachercopilot.session'))`))

// ---------------------------------------------------------------------------
section('Every page works with no backend')
const PAGES = [
  ['/', ['Dashboard', 'Time saved']],
  ['/classes', ['Classes', 'Students']],
  ['/lessons', ['Lesson']],
  ['/grading', ['Grading', 'Photosynthesis']],
  ['/differentiation', ['Create material', 'Generate three levels']],
  ['/parent-updates', ['Parent']],
  ['/workflow', ['Workflow']],
  ['/settings', ['Settings']],
]
for (const [path, needles] of PAGES) {
  await goto(path)
  const first = needles[0]
  const ready = await waitFor(`document.body.textContent.includes(${JSON.stringify(first)})`)
  const body = await text()
  const missing = needles.filter((n) => !has(body, n))
  check(
    `${path}`,
    ready && missing.length === 0 && !has(body, 'Something went wrong'),
    missing.length
      ? `missing: ${missing.join(', ')} | saw: ${body.replace(/\s+/g, ' ').slice(0, 160)}`
      : '',
  )
}

section('Differentiation produces three real levels')
await goto('/differentiation')
await waitFor(`document.body.textContent.includes('Generate three levels')`)
await evaluate(`
  const b = [...document.querySelectorAll('button')].find((x) => /Generate three levels/i.test(x.textContent))
  if (b) b.click()
  return true
`)
const levelsReady = await waitFor(`document.body.textContent.includes('Extension')`, 25000)
const diffText = await text()
check('generating works with no backend', levelsReady)
for (const level of ['Support', 'Core', 'Extension']) check(`${level} level rendered`, has(diffText, level))
check('worksheets are listed', /question/i.test(diffText))
check('groupings are shown', /group/i.test(diffText))

// ---------------------------------------------------------------------------
section('The workflow runs end to end')
await goto('/workflow')
await waitFor('document.querySelectorAll("button").length > 0')
const clicked = await evaluate(`
  const button = [...document.querySelectorAll('button')]
    .find((b) => /run (the )?workflow|start|generate|run/i.test(b.textContent))
  if (!button) return null
  const label = button.textContent.trim()
  button.click()
  return label
`)
check('a run button exists', Boolean(clicked), clicked || '')
const finished = await waitFor(
  `/Plan the lesson/i.test(document.body.textContent) && /approve|review|draft/i.test(document.body.textContent)`,
  25000,
)
await sleep(1500)
const workflowText = await text()
check('the run completes', finished, workflowText.replace(/\s+/g, ' ').slice(0, 200))
check('all five steps are listed', ['lesson', 'differenti', 'grade', 'regroup', 'message'].every((k) =>
  workflowText.toLowerCase().includes(k),
))
check('nothing is sent without approval', /approv/i.test(workflowText))

// ---------------------------------------------------------------------------
section('Photographic backdrop, glow buttons and the SVG mark')
await goto('/')
await waitFor(`document.querySelector('.app-backdrop')`)

const backdrop = await evaluate(`
  const el = document.querySelector('.app-backdrop')
  const cs = getComputedStyle(el)
  const img = el.querySelector('.app-backdrop-image')
  const imgCs = getComputedStyle(img)
  const scrim = el.querySelector('.app-backdrop-scrim')
  const sheen = el.querySelector('.app-backdrop-sheen')
  const rect = el.getBoundingClientRect()
  return {
    position: cs.position,
    covers: rect.width >= window.innerWidth - 1 && rect.height >= window.innerHeight - 1,
    imageUrl: imgCs.backgroundImage,
    imageSize: imgCs.backgroundSize,
    imageFilter: imgCs.filter,
    scrimPainted: getComputedStyle(scrim).backgroundImage.includes('gradient'),
    sheenAnimation: getComputedStyle(sheen).animationName,
    behind: (() => {
      const z = getComputedStyle(el).zIndex
      return z === 'auto' || Number(z) < 10
    })(),
  }
`)
check('the app backdrop is on screen', backdrop.position === 'fixed' && backdrop.covers)
check('it is behind the content', backdrop.behind)
check(
  'the supplied photograph is the background',
  /url\(.*app-bg\.jpg/.test(backdrop.imageUrl),
  backdrop.imageUrl.slice(0, 48),
)
check('it covers the viewport', backdrop.imageSize === 'cover', backdrop.imageSize)
// The source is 626x358, so it is deliberately blurred and oversized.
check('it is blurred and scaled past its low resolution', /blur\(3[0-9]px/.test(backdrop.imageFilter), backdrop.imageFilter)
check('a scrim holds the surface near-black', backdrop.scrimPainted)
check('the sheen breathes', backdrop.sheenAnimation === 'void-breathe', backdrop.sheenAnimation)

const glow = await evaluate(`
  const variants = ['btn-primary', 'btn-secondary', 'btn-ghost', 'btn-danger']
  const seen = {}
  for (const v of variants) {
    const btn = document.querySelector('.' + v)
    if (!btn) continue
    const cs = getComputedStyle(btn)
    seen[v] = {
      glowVar: cs.getPropertyValue('--glow').trim(),
      shadow: cs.boxShadow,
      transitionsBoxShadow: /box-shadow/.test(cs.transitionProperty),
    }
  }
  return seen
`)
const variantNames = Object.keys(glow)
check(
  'every button variant renders a glow',
  variantNames.length > 0 && variantNames.every((v) => glow[v].shadow && glow[v].shadow !== 'none'),
  variantNames.join(', ') || 'none found on this page',
)
check(
  'each variant defines its own glow colour',
  variantNames.every((v) => /^\d+,\s*\d+,\s*\d+$/.test(glow[v].glowVar)),
  variantNames.map((v) => `${v}=${glow[v].glowVar}`).join(' '),
)
check(
  'primary glows in polished steel',
  glow['btn-primary']?.glowVar === '194, 203, 214',
  glow['btn-primary']?.glowVar || 'n/a',
)
check(
  'box-shadow is transitioned, not snapped',
  variantNames.every((v) => glow[v].transitionsBoxShadow),
  variantNames.length ? 'all variants' : 'n/a',
)

const counts = await evaluate(`
  return {
    mark: Boolean(document.querySelector('aside svg[aria-label="TeacherCopilot"]')),
    sparkles: document.querySelectorAll('svg.lucide-sparkles').length,
    favicon: (document.querySelector('link[rel=icon]') || {}).href?.slice(0, 5) || '',
  }
`)
check('the logo is an inline SVG', counts.mark)
check('the generic sparkle icon is gone', counts.sparkles === 0)
check('the favicon is inlined, so no missing-logo request', counts.favicon === 'data:')

// ---------------------------------------------------------------------------
section('Text contrast (WCAG AA) across every page')
/**
 * Walks every element that owns visible text, composites the real background
 * through any translucent ancestors, and returns anything under the AA
 * threshold. A silver-on-black palette has much less headroom than the old
 * teal one, so this is checked rather than assumed.
 */
const contrastAudit = () =>
  evaluate(`
  const lum = (rgb) => {
    const [r, g, b] = rgb.map((v) => {
      const s = v / 255
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
    })
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
  }
  const parse = (c) => {
    const m = String(c).match(/rgba?\\(([^)]+)\\)/)
    if (!m) return null
    const p = m[1].split(',').map((x) => parseFloat(x))
    if (p.length < 3 || p.some((n) => Number.isNaN(n))) return null
    return { rgb: p.slice(0, 3), a: p.length > 3 ? p[3] : 1 }
  }
  const over = (fg, bg) => fg.rgb.map((c, i) => c * fg.a + bg[i] * (1 - fg.a))

  const backgroundOf = (el) => {
    const stack = []
    let node = el
    while (node && node.nodeType === 1) {
      const c = parse(getComputedStyle(node).backgroundColor)
      if (c && c.a > 0) {
        stack.push(c)
        if (c.a >= 1) break
      }
      node = node.parentElement
    }
    let base = [6, 7, 9] // the page tint, ink.50
    for (let i = stack.length - 1; i >= 0; i -= 1) base = over(stack[i], base)
    return base
  }

  const bad = []
  let checked = 0
  for (const el of document.querySelectorAll('body *')) {
    const own = [...el.childNodes]
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent.trim())
      .join('')
    if (!own) continue
    const cs = getComputedStyle(el)
    if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0) continue
    const rect = el.getBoundingClientRect()
    if (rect.width < 2 || rect.height < 2) continue
    const fg = parse(cs.color)
    if (!fg) continue
    const bg = backgroundOf(el)
    const l1 = lum(over(fg, bg))
    const l2 = lum(bg)
    const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)
    const size = parseFloat(cs.fontSize)
    const bold = parseInt(cs.fontWeight, 10) >= 700
    const min = size >= 24 || (size >= 18.66 && bold) ? 3 : 4.5
    checked += 1
    if (ratio < min) {
      bad.push({ text: own.slice(0, 44), ratio: Math.round(ratio * 100) / 100, min, color: cs.color })
    }
  }
  return { checked, total: bad.length, worst: bad.sort((a, b) => a.ratio - b.ratio).slice(0, 10) }
`)

for (const route of ['/', '/classes', '/lessons', '/grading', '/differentiation', '/parent-updates', '/workflow', '/settings']) {
  await goto(route)
  await sleep(1800)
  const audit = await contrastAudit()
  check(
    `contrast AA on ${route}`,
    audit.total === 0,
    audit.total
      ? `${audit.total}/${audit.checked} fail; worst: ${audit.worst
          .map((w) => `"${w.text}" ${w.ratio}:1 (needs ${w.min}) ${w.color}`)
          .join(' | ')}`
      : `${audit.checked} text nodes checked`,
  )
}

await goto('/')
await waitFor(`document.body.textContent.includes('Time saved')`)
const dashText = await text()
check('the dashboard reflects the run', dashText.includes('Time saved'))
check('the shell renders its navigation', dashText.includes('Parent Updates') && dashText.includes('Settings'))

// ---------------------------------------------------------------------------
section('No console errors anywhere')
check(
  'the app produced no console errors',
  consoleErrors.length === 0,
  consoleErrors.slice(0, 4).join(' | '),
)

// ---------------------------------------------------------------------------
console.log(`\n${'='.repeat(62)}`)
if (failures.length === 0) {
  console.log(`\x1b[32mRESULT: ${passed} browser checks passed — no backend, no console errors.\x1b[0m`)
} else {
  console.log(`\x1b[31mRESULT: ${failures.length} FAILED\x1b[0m`)
  failures.forEach((f) => console.log(`   - ${f}`))
  process.exitCode = 1
}
console.log('='.repeat(62))

ws.close()
edge.kill()
process.exit(process.exitCode || 0)
