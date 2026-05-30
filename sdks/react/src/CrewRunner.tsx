import { useState, useCallback, useRef, useEffect } from 'react'
import { useBlackbeard } from './BlackbeardProvider'
import { apiFetch } from './fetch'
import { ExecutionStatus } from './ExecutionStatus'
import type { Execution } from './types'
import { BlackbeardApiError, TERMINAL_STATUSES } from './types'

export interface CrewRunnerProps {
  /** Name of the crew to run. */
  crewName: string
  /** Project containing the crew (defaults to "default"). */
  project?: string
  /** @deprecated Use `project` instead. */
  namespace?: string
  /** Callback fired when the execution reaches a terminal state. */
  onComplete?: (execution: Execution) => void
}

/**
 * Crew runner widget. Displays an input form based on the crew spec,
 * triggers a kickoff, and shows execution status while running.
 */
export function CrewRunner({ crewName, project, namespace, onComplete }: CrewRunnerProps) {
  const config = useBlackbeard()
  const [inputsJson, setInputsJson] = useState('{}')
  const [executionId, setExecutionId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const activeRef = useRef(true)
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete

  useEffect(() => {
    activeRef.current = true
    return () => {
      activeRef.current = false
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current)
        pollTimerRef.current = null
      }
    }
  }, [])

  const handleRun = useCallback(async () => {
    setError(null)
    setExecutionId(null)
    setSubmitting(true)

    try {
      let parsedInputs: Record<string, unknown> = {}
      try {
        parsedInputs = JSON.parse(inputsJson) as Record<string, unknown>
      } catch {
        setError('Invalid JSON in inputs field')
        setSubmitting(false)
        return
      }

      const ns = project ?? namespace ?? 'default'
      const result = await apiFetch<{ id: string }>(
        config,
        `/api/v1/crews/${encodeURIComponent(crewName)}/kickoff?project=${encodeURIComponent(ns)}`,
        { method: 'POST', body: { inputs: parsedInputs } },
      )
      setExecutionId(result.id)

      if (onCompleteRef.current) {
        const poll = async () => {
          if (!activeRef.current) return
          try {
            const exec = await apiFetch<Execution>(
              config,
              `/api/v1/executions/${encodeURIComponent(result.id)}`,
            )
            if (!activeRef.current) return
            if (TERMINAL_STATUSES.has(exec.status)) {
              onCompleteRef.current?.(exec)
            } else {
              pollTimerRef.current = setTimeout(() => void poll(), 3000)
            }
          } catch {
            if (activeRef.current) {
              pollTimerRef.current = setTimeout(() => void poll(), 3000)
            }
          }
        }
        pollTimerRef.current = setTimeout(() => void poll(), 3000)
      }
    } catch (err) {
      setError(err instanceof BlackbeardApiError ? err.detail : err instanceof Error ? err.message : 'Failed to start execution')
    } finally {
      setSubmitting(false)
    }
  }, [config, crewName, project, namespace, inputsJson])

  // Read-only resource fetch not needed — we accept raw JSON input to
  // keep this widget dependency-free and simple.

  return (
    <div style={containerStyle}>
      {/* Header */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontWeight: 600, fontSize: 14, color: '#111827', marginBottom: 2 }}>
          Run: {crewName}
        </div>
        <div style={{ fontSize: 12, color: '#6b7280' }}>
          Provide inputs as JSON and click Run.
        </div>
      </div>

      {/* Input form */}
      {!executionId && (
        <div>
          <label
            htmlFor={`bb-inputs-${crewName}`}
            style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#374151', marginBottom: 4 }}
          >
            Inputs (JSON)
          </label>
          <textarea
            id={`bb-inputs-${crewName}`}
            value={inputsJson}
            onChange={(e) => setInputsJson(e.target.value)}
            rows={4}
            style={textareaStyle}
            spellCheck={false}
          />

          {error && (
            <div style={{ marginTop: 8, color: '#ef4444', fontSize: 12 }}>{error}</div>
          )}

          <button
            onClick={() => void handleRun()}
            disabled={submitting}
            style={{
              ...buttonStyle,
              opacity: submitting ? 0.6 : 1,
              cursor: submitting ? 'not-allowed' : 'pointer',
            }}
          >
            {submitting ? 'Starting...' : 'Run'}
          </button>
        </div>
      )}

      {/* Execution status */}
      {executionId && (
        <div style={{ marginTop: 8 }}>
          <ExecutionStatus executionId={executionId} />
          <button
            onClick={() => {
              if (pollTimerRef.current) {
                clearTimeout(pollTimerRef.current)
                pollTimerRef.current = null
              }
              setExecutionId(null)
              setError(null)
            }}
            style={{
              ...buttonStyle,
              backgroundColor: '#f3f4f6',
              color: '#374151',
              marginTop: 8,
            }}
          >
            Run another
          </button>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Styles                                                              */
/* ------------------------------------------------------------------ */

const containerStyle: React.CSSProperties = {
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  padding: 16,
  borderRadius: 8,
  border: '1px solid #e5e7eb',
  backgroundColor: '#fff',
}

const textareaStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  borderRadius: 6,
  border: '1px solid #d1d5db',
  fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
  fontSize: 13,
  lineHeight: 1.5,
  resize: 'vertical',
  boxSizing: 'border-box',
}

const buttonStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  marginTop: 12,
  padding: '8px 20px',
  borderRadius: 6,
  border: 'none',
  backgroundColor: '#3b82f6',
  color: '#fff',
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
}
