/**
 * Samples a local image through a canvas so the palette can be derived from the
 * actual picture rather than guessed at.
 *
 *   node analyze-image.mjs <path-to-image>
 */
import { spawn } from 'node:child_process'
import { createServer } from 'node:http'
import { mkdtempSync, readFileSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve, basename, extname } from 'node:path'

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const target = process.argv[2]
if (!target) {
  console.error('usage: node analyze-image.mjs <image>')
  process.exit(2)
}

const TYPES = {
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
}

// Headless Edge refuses to decode images loaded from file:// and taints the
// canvas on cross-origin loads, so the page and the image are served together
// from one loopback origin.
const body = readFileSync(resolve(target))
const mime = TYPES[extname(target).toLowerCase()] || 'application/octet-stream'
const server = createServer((req, res) => {
  if (req.url.startsWith('/img')) {
    res.writeHead(200, { 'Content-Type': mime, 'Content-Length': body.length })
    res.end(body)
    return
  }
  const html = `<!doctype html><meta charset="utf-8"><title>analyze</title><body></body>`
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
  res.end(html)
})
await new Promise((r) => server.listen(9390, '127.0.0.1', r))
const fileUrl = 'http://127.0.0.1:9390/img'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const profile = mkdtempSync(join(tmpdir(), 'tc_img_'))
const edge = spawn(EDGE, [
  '--headless=new',
  '--disable-gpu',
  '--no-sandbox',
  `--remote-debugging-port=9345`,
  `--user-data-dir=${profile}`,
  'about:blank',
])
edge.stderr.on('data', () => {})

let targetWs = null
for (let i = 0; i < 40 && !targetWs; i += 1) {
  await sleep(500)
  try {
    const list = await (await fetch('http://127.0.0.1:9345/json/list')).json()
    const page = list.find((t) => t.type === 'page')
    if (page) targetWs = page.webSocketDebuggerUrl
  } catch {
    /* still booting */
  }
}

const ws = new WebSocket(targetWs)
await new Promise((res, rej) => {
  ws.onopen = res
  ws.onerror = rej
})

let nextId = 1
const pending = new Map()
ws.onmessage = (event) => {
  const m = JSON.parse(event.data)
  if (m.id && pending.has(m.id)) {
    const { resolve: done, reject } = pending.get(m.id)
    pending.delete(m.id)
    m.error ? reject(new Error(m.error.message)) : done(m.result)
  }
}
const send = (method, params = {}) =>
  new Promise((res, rej) => {
    const id = nextId++
    pending.set(id, { resolve: res, reject: rej })
    ws.send(JSON.stringify({ id, method, params }))
  })

await send('Runtime.enable')
await send('Page.enable')
await send('Page.navigate', { url: 'http://127.0.0.1:9390/' })
await sleep(1500)
const out = await send('Runtime.evaluate', {
  expression: `(async () => {
    const img = new Image()
    img.src = ${JSON.stringify(fileUrl)}
    await img.decode()

    const W = 160, H = 160
    const canvas = document.createElement('canvas')
    canvas.width = W; canvas.height = H
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    ctx.drawImage(img, 0, 0, W, H)
    const { data } = ctx.getImageData(0, 0, W, H)

    const hex = (r, g, b) =>
      '#' + [r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('')

    let sr = 0, sg = 0, sb = 0
    const buckets = new Map()
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i], g = data[i + 1], b = data[i + 2]
      sr += r; sg += g; sb += b
      // quantise to 16 steps per channel to find dominant families
      const key = [r, g, b].map((v) => Math.round(v / 16) * 16).join(',')
      const cur = buckets.get(key) || { n: 0, r: 0, g: 0, b: 0 }
      cur.n++; cur.r += r; cur.g += g; cur.b += b
      buckets.set(key, cur)
    }
    const n = data.length / 4
    const avg = [sr / n, sg / n, sb / n]

    const top = [...buckets.values()]
      .sort((a, b) => b.n - a.n)
      .slice(0, 12)
      .map((c) => ({
        hex: hex(Math.round(c.r / c.n), Math.round(c.g / c.n), Math.round(c.b / c.n)),
        pct: Math.round((c.n / n) * 1000) / 10,
      }))

    const at = (x, y) => {
      const i = (Math.round(y * (H - 1)) * W + Math.round(x * (W - 1))) * 4
      return hex(data[i], data[i + 1], data[i + 2])
    }

    // brightness + saturation feel
    const lum = (0.2126 * avg[0] + 0.7152 * avg[1] + 0.0722 * avg[2]) / 255
    const maxc = Math.max(...avg), minc = Math.min(...avg)
    const sat = maxc === 0 ? 0 : (maxc - minc) / maxc

    return {
      natural: img.naturalWidth + 'x' + img.naturalHeight,
      ratio: (img.naturalWidth / img.naturalHeight).toFixed(3),
      average: hex(Math.round(avg[0]), Math.round(avg[1]), Math.round(avg[2])),
      avgRGB: avg.map((v) => Math.round(v)),
      luminance: Math.round(lum * 1000) / 1000,
      saturation: Math.round(sat * 1000) / 1000,
      corners: { tl: at(0, 0), tr: at(1, 0), bl: at(0, 1), br: at(1, 1) },
      centre: at(0.5, 0.5),
      topColours: top,
    }
  })()`,
  awaitPromise: true,
  returnByValue: true,
})

if (out.exceptionDetails) {
  console.error('ERROR:', out.exceptionDetails.exception?.description)
} else {
  const r = out.result.value
  console.log('size      ', r.natural, ' ratio', r.ratio)
  console.log('average   ', r.average, ' rgb', r.avgRGB.join(','))
  console.log('luminance ', r.luminance, ' saturation', r.saturation)
  console.log('corners   ', JSON.stringify(r.corners))
  console.log('centre    ', r.centre)
  console.log('top colours:')
  r.topColours.forEach((c) => console.log('   ', c.hex.padEnd(9), c.pct + '%'))
}

ws.close()
edge.kill()
server.close()
process.exit(0)