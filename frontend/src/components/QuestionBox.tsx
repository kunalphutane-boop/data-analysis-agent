// REAL: question textarea + Ask button + voice input (Web Speech API) + starter
// suggestion chips. Disabled until a dataset is loaded. See spec/ui.md.
'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

interface Props {
  value: string
  onChange: (v: string) => void
  onAsk: () => void
  loading: boolean
  disabled: boolean
  // Starter questions for the loaded dataset; clicking one asks it immediately.
  suggestions?: string[]
  onPickSuggestion?: (q: string) => void
}

// Web Speech API is unprefixed on some browsers, webkit-prefixed on others, and
// its types aren't in the standard DOM lib — so we treat the recognizer as `any`.
/* eslint-disable @typescript-eslint/no-explicit-any */
function getSpeechRecognition(): (new () => any) | null {
  if (typeof window === 'undefined') return null
  const w = window as any
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

function useVoiceInput(value: string, onChange: (v: string) => void) {
  const [listening, setListening] = useState(false)
  const [supported, setSupported] = useState(false)
  const recRef = useRef<any>(null)
  const baseRef = useRef('')

  useEffect(() => {
    setSupported(getSpeechRecognition() !== null)
    return () => recRef.current?.abort?.()
  }, [])

  const toggle = useCallback(() => {
    const SR = getSpeechRecognition()
    if (!SR) return
    if (listening) {
      recRef.current?.stop()
      return
    }
    const rec = new SR()
    rec.lang = 'en-US'
    rec.interimResults = true
    rec.continuous = false
    baseRef.current = value.trim()
    rec.onresult = (e: any) => {
      let finalText = ''
      let interim = ''
      for (let i = 0; i < e.results.length; i++) {
        const t = e.results[i][0].transcript
        if (e.results[i].isFinal) finalText += t
        else interim += t
      }
      const spoken = (finalText + interim).trim()
      onChange([baseRef.current, spoken].filter(Boolean).join(' '))
    }
    rec.onend = () => setListening(false)
    rec.onerror = () => setListening(false)
    recRef.current = rec
    setListening(true)
    rec.start()
  }, [listening, value, onChange])

  return { listening, supported, toggle }
}
/* eslint-enable @typescript-eslint/no-explicit-any */

export function QuestionBox({
  value,
  onChange,
  onAsk,
  loading,
  disabled,
  suggestions = [],
  onPickSuggestion,
}: Props) {
  const canAsk = !disabled && !loading && value.trim().length > 0
  const { listening, supported, toggle } = useVoiceInput(value, onChange)

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold text-gray-700">Ask a question</h2>

      {/* Starter suggestions — shown before the first question. */}
      {!disabled && suggestions.length > 0 && value.trim().length === 0 && (
        <div data-testid="suggestions" className="mb-3">
          <p className="mb-1.5 text-xs text-gray-400">Try one of these:</p>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((q, i) => (
              <button
                key={i}
                type="button"
                data-testid="suggestion-chip"
                onClick={() => (onPickSuggestion ? onPickSuggestion(q) : onChange(q))}
                disabled={loading}
                className="inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50/60 px-3 py-1.5 text-xs font-medium text-blue-700 transition hover:border-blue-400 hover:bg-blue-100 disabled:opacity-50"
              >
                <span aria-hidden className="text-blue-400">✦</span>
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="relative">
        <textarea
          data-testid="question-input"
          className="w-full rounded-lg border border-gray-300 p-3 pr-12 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50"
          rows={3}
          placeholder={
            disabled
              ? 'Upload a CSV first, then ask a question…'
              : listening
                ? 'Listening… speak your question'
                : 'e.g. What is the total revenue by region?'
          }
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && canAsk) onAsk()
          }}
          disabled={disabled || loading}
        />

        {/* Voice input — only when the browser supports the Web Speech API. */}
        {supported && (
          <button
            type="button"
            data-testid="voice-button"
            onClick={toggle}
            disabled={disabled || loading}
            aria-pressed={listening}
            aria-label={listening ? 'Stop voice input' : 'Ask with voice'}
            title={listening ? 'Stop listening' : 'Ask with voice'}
            className={`absolute right-2 top-2 inline-flex h-9 w-9 items-center justify-center rounded-lg border text-base transition disabled:opacity-40 ${
              listening
                ? 'animate-pulse border-red-300 bg-red-50 text-red-600'
                : 'border-gray-200 bg-white text-gray-500 hover:border-blue-300 hover:text-blue-600'
            }`}
          >
            {listening ? '■' : '🎤'}
          </button>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between">
        <button
          type="button"
          data-testid="ask-button"
          onClick={onAsk}
          disabled={!canAsk}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading && (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
          )}
          {loading ? 'Analyzing…' : 'Ask'}
        </button>

        {listening && (
          <span data-testid="voice-status" className="text-xs font-medium text-red-600">
            ● Listening…
          </span>
        )}
      </div>
    </section>
  )
}
