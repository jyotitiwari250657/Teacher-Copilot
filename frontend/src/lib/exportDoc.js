/**
 * Save a generated document without pulling in a PDF/DOCX library.
 *
 * 'docx'  -> a Word-compatible HTML file (.doc). Word, LibreOffice and Google
 *            Docs all open it, and it keeps Devanagari intact.
 * 'pdf'   -> a print-ready window; the browser's own "Save as PDF" produces the
 *            file. This is the only way to get a true PDF with no dependency.
 */

const PRINT_CSS = `
  @page { margin: 18mm; }
  body {
    font-family: Inter, 'Segoe UI', system-ui, sans-serif;
    color: #111827; line-height: 1.6; margin: 0; padding: 32px; background: #fff;
  }
  h1 { font-size: 22pt; margin: 0 0 4px; letter-spacing: -0.01em; }
  h2 {
    font-size: 12pt; text-transform: uppercase; letter-spacing: 0.08em;
    color: #2f3742; margin: 26px 0 8px; padding-bottom: 6px;
    border-bottom: 1px solid #cbd1d9;
  }
  p { margin: 0 0 10px; }
  .muted { color: #5c6572; font-size: 10pt; margin-bottom: 18px; }
  .hint { color: #5c6572; font-size: 9.5pt; font-style: italic; margin-top: 2px; }
  ol, ul { margin: 0 0 10px; padding-left: 22px; }
  li { margin-bottom: 7px; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 10pt; }
  th, td { border: 1px solid #cbd1d9; padding: 7px 9px; text-align: left; vertical-align: top; }
  th { background: #eef0f3; font-weight: 600; }
  .footer { margin-top: 30px; padding-top: 10px; border-top: 1px solid #cbd1d9; color: #8a929c; font-size: 8.5pt; }
`

/** Word opens HTML saved with this mime type and keeps the styling. */
const WORD_MIME = 'application/msword'

export function saveDocument(doc, format = 'docx') {
  if (!doc?.html) return
  const html = documentHtml(doc)

  if (format === 'pdf') {
    openPrintWindow(doc, html)
    return
  }

  const blob = new Blob([html], { type: `${WORD_MIME};charset=utf-8` })
  const url = URL.createObjectURL(blob)
  const anchor = window.document.createElement('a')
  anchor.href = url
  anchor.download = (doc.filename || 'document').replace(/\.doc$/, '.doc')
  window.document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

function documentHtml(doc) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${escapeHtml(doc.title || 'Document')}</title>
<style>${PRINT_CSS}</style>
</head>
<body>
${doc.html}
<p class="footer">Prepared with TeacherCopilot. AI-generated &mdash; please review before use.</p>
</body>
</html>`
}

function openPrintWindow(doc, html) {
  const win = window.open('', '_blank', 'width=900,height=1000')
  if (!win) {
    // Pop-up blocked: fall back to a download the user can print themselves.
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = window.document.createElement('a')
    anchor.href = url
    anchor.download = `${(doc.filename || 'document').replace(/\.doc$/, '')}.html`
    window.document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    setTimeout(() => URL.revokeObjectURL(url), 2000)
    return
  }
  win.document.write(html)
  win.document.close()
  win.focus()
  // Give the browser a moment to lay the document out before printing.
  win.setTimeout(() => win.print(), 350)
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}
