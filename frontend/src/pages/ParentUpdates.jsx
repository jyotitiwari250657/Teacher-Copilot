import { useCallback, useEffect, useState } from 'react'
import {
  MessageSquare,
  CheckCircle2,
  Send,
  AlertTriangle,
  ShieldCheck,
  Mail,
  Smartphone,
  Pencil,
  Save,
} from 'lucide-react'
import { AiGlyph } from '../components/brand'
import { api } from '../api/client'
import { useToast } from '../components/Toast'
import {
  Card,
  CardHeader,
  Field,
  ErrorBanner,
  AiLabel,
  DraftBadge,
  LoadingPanel,
  EmptyState,
  Spinner,
  Tabs,
  T,
} from '../components/ui'

const STATUS_TONE = {
  draft: 'border-amber-200 bg-amber-50 text-amber-800',
  needs_review: 'border-red-200 bg-red-50 text-red-800',
  approved: 'border-brand-200 bg-brand-50 text-brand-800',
  simulated_sent: 'border-sky-200 bg-sky-50 text-sky-800',
  sent: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  failed: 'border-red-200 bg-red-50 text-red-800',
}

export default function ParentUpdates() {
  const toast = useToast()
  const [classes, setClasses] = useState([])
  const [classId, setClassId] = useState('')
  const [tab, setTab] = useState('drafts')
  const [form, setForm] = useState({
    tone: 'warm',
    channel: 'whatsapp',
    language: 'English',
    topic: '',
    teacher_note: '',
  })
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [sending, setSending] = useState(false)

  useEffect(() => {
    api.classes()
      .then((list) => {
        setClasses(list)
        if (list.length > 0) setClassId(String(list[0].id))
      })
      .catch(() => setClasses([]))
  }, [])

  const loadMessages = useCallback(async () => {
    if (!classId) return setMessages([])
    setLoading(true)
    try {
      setMessages(await api.messages(Number(classId)))
      setError(null)
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [classId])

  useEffect(() => {
    loadMessages()
  }, [loadMessages])

  async function generate(event) {
    event.preventDefault()
    setGenerating(true)
    setError(null)
    try {
      const result = await api.generateMessages({
        class_id: Number(classId),
        tone: form.tone,
        channel: form.channel,
        language: form.language,
        topic: form.topic,
        teacher_note: form.teacher_note,
      })
      toast.success(
        `${result.generated} message${result.generated === 1 ? '' : 's'} drafted. ` +
          'Nothing is sent until you approve it.',
      )
      await loadMessages()
      setTab('drafts')
    } catch (err) {
      setError(err)
    } finally {
      setGenerating(false)
    }
  }

  async function approve(message) {
    try {
      await api.approveMessage(message.id)
      toast.success(`Approved. Ready to send when you are.`)
      await loadMessages()
    } catch (err) {
      toast.error(err.message)
    }
  }

  async function approveAll() {
    try {
      const result = await api.approveAllMessages(Number(classId))
      toast.success(`${result.approved} message${result.approved === 1 ? '' : 's'} approved.`)
      await loadMessages()
    } catch (err) {
      toast.error(err.message)
    }
  }

  async function sendApproved() {
    setSending(true)
    try {
      const result = await api.sendMessages({ send_all: true, message_ids: [] })
      if (result.sent === 0) {
        toast.warning('No approved messages to send. Approve some first.')
      } else {
        toast.success(`${result.sent} message${result.sent === 1 ? '' : 's'} sent (simulated).`)
      }
      await loadMessages()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSending(false)
    }
  }

  async function saveDraft(message) {
    const body = drafts[message.id]
    if (body === undefined) return
    try {
      await api.updateMessage(message.id, { body })
      setDrafts((current) => {
        const next = { ...current }
        delete next[message.id]
        return next
      })
      toast.success('Message updated.')
      await loadMessages()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const grouped = {
    drafts: messages.filter((m) => m.status === 'draft' || m.status === 'needs_review'),
    approved: messages.filter((m) => m.status === 'approved'),
    sent: messages.filter((m) => m.status === 'sent' || m.status === 'simulated_sent'),
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-ink-800">Parent Updates</h1>
          <p className="mt-1 text-sm text-ink-500">
            Short, warm notes about your own student only. Never sent without your approval.
          </p>
        </div>
        <span className="chip border-brand-200 bg-brand-50 text-brand-800">
          <ShieldCheck size={13} />
          Approval required
        </span>
      </div>

      <div className="grid gap-5 lg:grid-cols-4">
        {/* Composer */}
        <Card className="lg:col-span-1">
          <CardHeader title="Write messages" icon={MessageSquare} />
          <form onSubmit={generate} className="card-pad space-y-3.5">
            <Field label="Class">
              <select
                className="input"
                value={classId}
                onChange={(e) => setClassId(e.target.value)}
              >
                {classes.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Channel">
              <select
                className="input"
                value={form.channel}
                onChange={(e) => setForm({ ...form, channel: e.target.value })}
              >
                <option value="whatsapp">WhatsApp (max 120 words)</option>
                <option value="email">Email (subject + body)</option>
              </select>
            </Field>
            <Field label="Language">
              <select
                className="input"
                value={form.language}
                onChange={(e) => setForm({ ...form, language: e.target.value })}
              >
                <option>English</option>
                <option>Hindi</option>
              </select>
            </Field>
            <Field label="Tone">
              <select
                className="input"
                value={form.tone}
                onChange={(e) => setForm({ ...form, tone: e.target.value })}
              >
                <option value="warm">Warm</option>
                <option value="formal">Formal</option>
              </select>
            </Field>
            <Field label="Topic" hint="Optional, shown to the writer.">
              <input
                className="input"
                value={form.topic}
                onChange={(e) => setForm({ ...form, topic: e.target.value })}
                placeholder="Photosynthesis unit test"
              />
            </Field>
            <Field label="Note for this batch" hint="Optional guidance for every message.">
              <textarea
                className="input min-h-[64px] resize-y"
                value={form.teacher_note}
                onChange={(e) => setForm({ ...form, teacher_note: e.target.value })}
                placeholder="Focus on the reading section this week."
              />
            </Field>

            {error && <ErrorBanner error={error} />}

            <button className="btn-primary w-full" disabled={generating || !classId}>
              {generating ? <Spinner size={15} /> : <AiGlyph size={16} />}
              {generating ? 'Writing…' : 'Generate for the class'}
            </button>
            <p className="text-xs text-ink-500">
              Produces one draft per student. Each contains one positive note, one thing to work on,
              and one step for home.
            </p>
          </form>
        </Card>

        {/* Messages */}
        <div className="space-y-4 lg:col-span-3">
          <Tabs
            active={tab}
            onChange={setTab}
            tabs={[
              { key: 'drafts', label: 'Drafts', count: grouped.drafts.length },
              { key: 'approved', label: 'Approved', count: grouped.approved.length },
              { key: 'sent', label: 'Sent', count: grouped.sent.length },
            ]}
          />

          {loading ? (
            <Card>
              <LoadingPanel label="Loading messages…" />
            </Card>
          ) : (
            <>
              {tab !== 'drafts' && grouped.approved.length > 0 && (
                <Card className="border-brand-200 bg-brand-50/60">
                  <div className="card-pad flex flex-wrap items-center justify-between gap-3">
                    <p className="text-sm text-brand-900">
                      <strong>{grouped.approved.length}</strong> message
                      {grouped.approved.length === 1 ? '' : 's'} approved and ready to send.
                    </p>
                    <button className="btn-primary btn-sm" onClick={sendApproved} disabled={sending}>
                      {sending ? <Spinner size={13} /> : <Send size={14} />}
                      Send approved messages
                    </button>
                  </div>
                </Card>
              )}

              {grouped[tab].length === 0 ? (
                <Card>
                  <EmptyState
                    icon={MessageSquare}
                    title={`No ${tab} yet`}
                    description={
                      tab === 'drafts'
                        ? 'Generate messages for the class to see drafts here.'
                        : tab === 'approved'
                          ? 'Approve a draft and it will move here, ready to send.'
                          : 'Sent messages will appear here. Sending is simulated in this demo.'
                    }
                  />
                </Card>
              ) : (
                <>
                  {tab === 'drafts' && grouped.drafts.length > 0 && (
                    <div className="flex justify-end">
                      <button className="btn-secondary btn-sm" onClick={approveAll}>
                        <CheckCircle2 size={14} />
                        Approve all drafts
                      </button>
                    </div>
                  )}

                  {grouped[tab].map((message) => (
                    <MessageCard
                      key={message.id}
                      message={message}
                      draft={drafts[message.id]}
                      onChange={(value) =>
                        setDrafts((current) => ({ ...current, [message.id]: value }))
                      }
                      onSave={() => saveDraft(message)}
                      onApprove={() => approve(message)}
                      showActions={tab === 'drafts'}
                      // Approved-but-unsent messages stay editable so a mistaken
                      // approval can be undone; saving an edit revokes it.
                      editable={tab !== 'sent'}
                    />
                  ))}
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
function MessageCard({ message, draft, onChange, onSave, onApprove, showActions, editable }) {
  const body = draft ?? message.body
  const edited = draft !== undefined
  const isHindi = /[\u0900-\u097F]/.test(body)
  const ChannelIcon = message.channel === 'email' ? Mail : Smartphone

  return (
    <Card
      className={
        message.needs_teacher_review && message.status !== 'sent' && message.status !== 'simulated_sent'
          ? 'border-red-200'
          : ''
      }
    >
      <div className="card-pad">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-2.5">
            <ChannelIcon size={16} className="mt-0.5 shrink-0 text-ink-400" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink-800">
                {message.student_name}
                <span className="ml-2 font-normal text-ink-500">
                  → {message.parent_name || 'Parent'}
                </span>
              </p>
              <p className="text-xs text-ink-500">
                {message.channel} · {message.language} · {message.tone} tone ·{' '}
                {message.word_count} words
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`chip ${STATUS_TONE[message.status] || 'border-ink-200 bg-ink-50'}`}>
              {message.status.replace(/_/g, ' ')}
            </span>
            {showActions && (
              <button className="btn-primary btn-sm" onClick={onApprove}>
                <CheckCircle2 size={13} /> Approve
              </button>
            )}
          </div>
        </div>

        {message.needs_teacher_review && (message.review_reasons || []).length > 0 && (
          <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5">
            <p className="flex items-start gap-2 text-xs font-semibold text-red-900">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              Needs your attention before sending
            </p>
            <ul className="mt-1 space-y-0.5 pl-6">
              {message.review_reasons.map((reason, index) => (
                <li key={index} className="list-disc text-xs text-red-800">
                  {reason}
                </li>
              ))}
            </ul>
          </div>
        )}

        {message.channel === 'email' && message.subject && (
          <p className="mt-3 rounded bg-ink-50 px-3 py-2 text-sm font-medium text-ink-700">
            Subject: {message.subject}
          </p>
        )}

        <textarea
          className={`input mt-3 min-h-[110px] resize-y leading-relaxed ${
            isHindi ? 'devanagari' : ''
          }`}
          value={body}
          onChange={(event) => onChange(event.target.value)}
          readOnly={!editable}
        />

        {showActions && edited && (
          <div className="mt-2 flex justify-end">
            <button className="btn-secondary btn-sm" onClick={onSave}>
              <Save size={13} /> Save edit
            </button>
          </div>
        )}

        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-ink-200/70 pt-3">
          <AiLabel compact />
          {message.sent_at && (
            <span className="text-xs text-ink-500">
              Sent {new Date(message.sent_at).toLocaleString()}
            </span>
          )}
        </div>
      </div>
    </Card>
  )
}