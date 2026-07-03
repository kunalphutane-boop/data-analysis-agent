// REAL: drag/drop or pick a CSV. Handles empty / loading / error states.
'use client'

import { useRef, useState } from 'react'
import { StubButton } from './Stub'

interface Props {
  onFile: (file: File) => void
  loading: boolean
  error: string | null
  filename: string | null
}

export function UploadDropzone({ onFile, loading, error, filename }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    if (loading) return
    const file = e.dataTransfer.files?.[0]
    if (file) onFile(file)
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">Upload dataset</h2>
        <StubButton label="Add file" testId="add-file-stub" />
      </div>

      <div
        data-testid="upload-dropzone"
        onClick={() => !loading && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-10 text-center transition ${
          dragOver
            ? 'border-blue-400 bg-blue-50'
            : 'border-gray-300 bg-gray-50 hover:border-blue-300 hover:bg-blue-50/40'
        } ${loading ? 'pointer-events-none opacity-70' : ''}`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          data-testid="file-input"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) onFile(file)
            e.target.value = ''
          }}
        />

        {loading ? (
          <div data-testid="upload-loading" className="flex items-center gap-2 text-sm text-gray-600">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600" />
            Profiling…
          </div>
        ) : (
          <>
            <svg
              className="mb-2 h-8 w-8 text-gray-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1.5}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5"
              />
            </svg>
            <p className="text-sm font-medium text-gray-700">
              Drag & drop a CSV here, or click to choose
            </p>
            <p className="mt-1 text-xs text-gray-400">Up to ~100 MB · .csv</p>
          </>
        )}
      </div>

      {filename && !loading && !error && (
        <p data-testid="upload-filename" className="mt-2 text-xs text-gray-500">
          Loaded: <span className="font-medium text-gray-700">{filename}</span>
        </p>
      )}

      {error && (
        <div
          data-testid="upload-error"
          className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        >
          {error}
        </div>
      )}
    </section>
  )
}
