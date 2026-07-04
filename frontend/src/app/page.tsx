'use client'

import { useState } from 'react'
import {
  ApiError,
  ask,
  createSession,
  getSuggestions,
  uploadDataset,
  type Dataset,
} from '@/lib/api'
import { UploadDropzone } from '@/components/UploadDropzone'
import { ProfilePanel } from '@/components/ProfilePanel'
import { QuestionBox } from '@/components/QuestionBox'
import { ChatTurn, type ChatTurnData } from '@/components/ChatTurn'
import {
  ConversationIntelligence,
  BusinessContextPanel,
} from '@/components/ConversationIntelligence'
import { StubPanel } from '@/components/Stub'

type Tab = 'ask' | 'intelligence'

function TabButton({
  active,
  onClick,
  testId,
  children,
}: {
  active: boolean
  onClick: () => void
  testId: string
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      data-testid={testId}
      onClick={onClick}
      className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium transition ${
        active
          ? 'bg-blue-600 text-white shadow-sm'
          : 'text-slate-600 hover:bg-slate-100'
      }`}
    >
      {children}
    </button>
  )
}

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [dataset, setDataset] = useState<Dataset | null>(null)

  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const [activeTab, setActiveTab] = useState<Tab>('ask')
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [turns, setTurns] = useState<ChatTurnData[]>([])
  const [suggestions, setSuggestions] = useState<string[]>([])

  async function handleFile(file: File) {
    setUploading(true)
    setUploadError(null)
    setSuggestions([])
    try {
      // Create a session first if we don't have one yet.
      let sid = sessionId
      if (!sid) {
        const session = await createSession()
        sid = session.id
        setSessionId(sid)
      }
      const ds = await uploadDataset(file, sid)
      setDataset(ds)
      // A new dataset starts a fresh conversation.
      setTurns([])
      setQuestion('')
      setActiveTab('ask')
      // Fetch starter questions in the background — never blocks the UI.
      getSuggestions(ds.id)
        .then(setSuggestions)
        .catch(() => setSuggestions([]))
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : 'Network error — is the server running at :8001?'
      setUploadError(msg)
    } finally {
      setUploading(false)
    }
  }

  // Ask a question and APPEND it to the transcript (history is retained). Used by
  // the box, suggestion chips, and follow-up chips.
  async function runAsk(q: string) {
    const text = q.trim()
    if (!sessionId || !dataset || !text || asking) return
    const id =
      typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random()}`
    setActiveTab('ask')
    setQuestion('')
    setAsking(true)
    setTurns((prev) => [...prev, { id, question: text, pending: true }])
    try {
      const result = await ask(sessionId, dataset.id, text)
      setTurns((prev) =>
        prev.map((t) => (t.id === id ? { ...t, result, pending: false } : t)),
      )
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : 'Network error — is the server running at :8001?'
      setTurns((prev) =>
        prev.map((t) => (t.id === id ? { ...t, error: msg, pending: false } : t)),
      )
    } finally {
      setAsking(false)
    }
  }

  function handleAsk() {
    void runAsk(question)
  }

  // Newest turn first, so the latest answer sits right under the question box.
  const orderedTurns = [...turns].reverse()

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-50">
      {/* Branded top bar — sticky, spans full width. */}
      <header className="sticky top-0 z-20 border-b border-slate-200/70 bg-white/80 backdrop-blur-md">
        <div className="mx-auto flex w-full max-w-[1600px] items-center gap-3 px-4 py-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 text-sm font-bold text-white shadow-sm">
            DA
          </span>
          <div className="leading-tight">
            <h1 className="text-base font-semibold tracking-tight text-slate-900">
              Data Analytics Agent
            </h1>
            <p className="text-xs text-slate-500">
              Upload a CSV, set your business context, and ask questions answered by real
              pandas execution.
            </p>
          </div>
          {dataset && (
            <span className="ml-auto hidden items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600 sm:inline-flex">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              {dataset.filename}
            </span>
          )}
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1600px] px-4 py-8">
        <div className="grid gap-5 xl:grid-cols-[30%_70%]">
          <aside data-testid="analytics-left-panel" className="space-y-5">
            <UploadDropzone
              onFile={handleFile}
              loading={uploading}
              error={uploadError}
              filename={dataset?.filename ?? null}
            />

            {dataset && <BusinessContextPanel sessionId={dataset.session_id} />}

            <ProfilePanel dataset={dataset} />

            <StubPanel title="Data-quality flags" testId="quality-flags-stub">
              Automatic warnings about outliers, duplicates, and type mismatches.
            </StubPanel>
          </aside>

          <section data-testid="analytics-right-panel" className="space-y-4">
            {/* Tabs — full space for each workspace. */}
            {dataset && (
              <div
                role="tablist"
                className="flex gap-1 rounded-xl border border-slate-200 bg-white p-1 shadow-sm"
              >
                <TabButton
                  active={activeTab === 'ask'}
                  onClick={() => setActiveTab('ask')}
                  testId="tab-ask"
                >
                  Ask Anything
                </TabButton>
                <TabButton
                  active={activeTab === 'intelligence'}
                  onClick={() => setActiveTab('intelligence')}
                  testId="tab-intelligence"
                >
                  Call Intelligence
                </TabButton>
              </div>
            )}

            {/* Call Intelligence — kept mounted (hidden) so its job/results persist
                across tab switches. */}
            {dataset && (
              <div
                data-testid="tab-panel-intelligence"
                className={activeTab === 'intelligence' ? '' : 'hidden'}
              >
                <ConversationIntelligence key={dataset.id} dataset={dataset} />
              </div>
            )}

            {/* Ask Anything — question box + retained chat transcript. */}
            <div
              data-testid="tab-panel-ask"
              className={!dataset || activeTab === 'ask' ? 'space-y-4' : 'hidden'}
            >
              <QuestionBox
                value={question}
                onChange={setQuestion}
                onAsk={handleAsk}
                loading={asking}
                disabled={!dataset}
                suggestions={suggestions}
                onPickSuggestion={runAsk}
              />

              {turns.length > 0 ? (
                <div data-testid="chat-transcript" className="space-y-5">
                  {orderedTurns.map((turn) => (
                    <ChatTurn key={turn.id} turn={turn} onFollowUp={runAsk} />
                  ))}
                </div>
              ) : (
                <p className="pb-4 text-center text-sm text-gray-400">
                  Your answers, the executed code, and the running cost will appear here —
                  and stay as you ask more.
                </p>
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  )
}
