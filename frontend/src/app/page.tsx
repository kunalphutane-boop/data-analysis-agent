'use client'

import { useState } from 'react'
import {
  ApiError,
  ask,
  createSession,
  uploadDataset,
  type AskResult,
  type Dataset,
} from '@/lib/api'
import { UploadDropzone } from '@/components/UploadDropzone'
import { ProfilePanel } from '@/components/ProfilePanel'
import { QuestionBox } from '@/components/QuestionBox'
import { AnswerDisplay } from '@/components/AnswerDisplay'
import {
  ConversationIntelligence,
  BusinessContextPanel,
} from '@/components/ConversationIntelligence'
import { StubPanel } from '@/components/Stub'

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [dataset, setDataset] = useState<Dataset | null>(null)

  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [askError, setAskError] = useState<string | null>(null)
  const [answer, setAnswer] = useState<AskResult | null>(null)

  async function handleFile(file: File) {
    setUploading(true)
    setUploadError(null)
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
      // A new dataset invalidates the previous answer.
      setAnswer(null)
      setAskError(null)
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

  async function handleAsk() {
    if (!sessionId || !dataset || !question.trim()) return
    setAsking(true)
    setAskError(null)
    setAnswer(null)
    try {
      const result = await ask(sessionId, dataset.id, question.trim())
      setAnswer(result)
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : 'Network error — is the server running at :8001?'
      setAskError(msg)
    } finally {
      setAsking(false)
    }
  }

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

            {dataset && (
              <BusinessContextPanel sessionId={dataset.session_id} />
            )}

            <ProfilePanel dataset={dataset} />

            <StubPanel title="Data-quality flags" testId="quality-flags-stub">
              Automatic warnings about outliers, duplicates, and type mismatches.
            </StubPanel>
          </aside>

          <section data-testid="analytics-right-panel" className="space-y-5">
            {dataset && (
              <ConversationIntelligence key={dataset.id} dataset={dataset} />
            )}

            <QuestionBox
              value={question}
              onChange={setQuestion}
              onAsk={handleAsk}
              loading={asking}
              disabled={!dataset}
            />

            {askError && (
              <div
                data-testid="ask-error"
                className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"
              >
                {askError}
              </div>
            )}

            <AnswerDisplay result={answer} />

            {!answer && !asking && !askError && (
              <p className="pb-4 text-center text-sm text-gray-400">
                Your answer, the executed code, and its cost will appear here.
              </p>
            )}
          </section>
        </div>
      </main>
    </div>
  )
}
