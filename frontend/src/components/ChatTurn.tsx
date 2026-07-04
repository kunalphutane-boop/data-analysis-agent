// One turn in the Ask-Anything chat transcript: the user's question (right-aligned
// bubble) followed by its answer card, a loading state, or an error. History is
// retained across questions — each ask appends a new turn.
'use client'

import { AnswerDisplay } from './AnswerDisplay'
import type { AskResult } from '@/lib/api'

export interface ChatTurnData {
  id: string
  question: string
  result?: AskResult
  error?: string
  pending: boolean
}

export function ChatTurn({
  turn,
  onFollowUp,
}: {
  turn: ChatTurnData
  onFollowUp: (q: string) => void
}) {
  return (
    <div data-testid="chat-turn" className="space-y-3">
      <div className="flex justify-end">
        <div
          data-testid="chat-question"
          className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm"
        >
          {turn.question}
        </div>
      </div>

      {turn.pending ? (
        <div data-testid="chat-pending" className="flex items-center gap-2 text-sm text-gray-500">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600" />
          Analyzing…
        </div>
      ) : turn.error ? (
        <div
          data-testid="chat-error"
          className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"
        >
          {turn.error}
        </div>
      ) : turn.result ? (
        <AnswerDisplay result={turn.result} onFollowUp={onFollowUp} />
      ) : null}
    </div>
  )
}
