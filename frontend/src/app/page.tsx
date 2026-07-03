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
import { Sidebar } from '@/components/Sidebar'
import { UploadDropzone } from '@/components/UploadDropzone'
import { ProfilePanel } from '@/components/ProfilePanel'
import { QuestionBox } from '@/components/QuestionBox'
import { AnswerDisplay } from '@/components/AnswerDisplay'
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
    <div className="flex min-h-screen">
      <Sidebar />

      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
        <header className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">
            Data Analytics Agent
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Upload a CSV, read its profile, ask a question — answers are backed by pandas
            actually executed on your full data.
          </p>
        </header>

        <div className="space-y-5">
          <UploadDropzone
            onFile={handleFile}
            loading={uploading}
            error={uploadError}
            filename={dataset?.filename ?? null}
          />

          <ProfilePanel dataset={dataset} />

          {/* Data-quality flags STUB */}
          <StubPanel title="Data-quality flags" testId="quality-flags-stub">
            Automatic warnings about outliers, duplicates, and type mismatches.
          </StubPanel>

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
        </div>
      </main>
    </div>
  )
}
