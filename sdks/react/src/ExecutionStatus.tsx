import { useState, useEffect, useRef } from 'react'
import { useBlackbeard } from './BlackbeardProvider'
import { apiFetch } from './fetch'
import type { Execution } from './types'
import { TERMINAL_STATUSES } from './types'

export interface ExecutionStatusProps {
  /** UUID of the execution to display. */
  executionId: string
}

const STATUS_COLORS: Record<string, string> = {
  queued: '#f59e0b',
  running: '#3b82f6',
  completed: '#22c55e',
  failed: '#ef4444',
  cancelled: '#6b7280',
}

const POLL_INTERVAL_MS = 3000

function formatDuration(start: string | null, end: string | null): string {
  if (!start) return '--'
  const s = new Date(start).getTime()
  const e = end ? new Date(end).getTime() : Date.now()
  const seconds = Math.round((e - s) / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return `${minutes}m ${remainder}s`
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

/**
 * Displays execution status, token count, and duration for a given
 * execution ID. Polls the API until the execution reaches a terminal
 * state.
 */
export function ExecutionStatus({ executionId }: ExecutionStatusProps) {
  const config = useBlackbeard()
  const [execution, setExecution] = useState<Execution | null>(null)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    let active = true

    async function poll() {
      try {
        const data = await apiFetch<Execution>(
          config,
          `/api/v1/executions/${executionId}`,
        )
        if (!active) return
        setExecution(data)
        setError(null)

        if (TERMINAL_STATUSES.has(data.status) && intervalRef.current) {
          clearInterval(intervalRef.current)
          intervalRef.current = null
        }
      } catch (err) {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Failed to fetch execution')
      }
    }

    void poll()
    intervalRef.current = setInterval(() => void poll(), POLL_INTERVAL_MS)

    return () => {
      active = false
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [config, executionId])

  if (error) {
    return (
      <div style={containerStyle}>
        <span style={{ color: '#ef4444', fontSize: 13 }}>{error}</span>
      </div>
    )
  }

  if (!execution) {
    return (
      <div style={containerStyle}>
        <span style={{ color: '#6b7280', fontSize: 13 }}>Loading...</span>
      </div>
    )
  }

  const statusColor = STATUS_COLORS[execution.status] ?? '#6b7280'

  return (
    <div style={containerStyle}>
      {/* Status badge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span
          style={{
            display: 'inline-block',
            width: 8,
            height: 8,
            borderRadius: '50%',
            backgroundColor: statusColor,
          }}
          aria-hidden="true"
        />
        <span
          style={{ fontWeight: 600, fontSize: 14, textTransform: 'capitalize', color: statusColor }}
        >
          {execution.status}
        </span>
      </div>

      {/* Details */}
      <div style={{ display: 'flex', gap: 16, fontSize: 12, color: '#6b7280' }}>
        <span title="Total tokens">
          {formatTokens(execution.total_tokens)} tokens
        </span>
        <span title="Duration">
          {formatDuration(execution.started_at, execution.completed_at)}
        </span>
        {execution.cost_usd != null && Number(execution.cost_usd) > 0 && (
          <span title="Cost">
            ${Number(execution.cost_usd).toFixed(4)}
          </span>
        )}
      </div>

      {/* Error message */}
      {execution.status === 'failed' && execution.error && (
        <div
          style={{
            marginTop: 8,
            padding: '6px 10px',
            borderRadius: 4,
            backgroundColor: '#fef2f2',
            color: '#991b1b',
            fontSize: 12,
            lineHeight: 1.4,
          }}
        >
          {execution.error}
        </div>
      )}
    </div>
  )
}

const containerStyle: React.CSSProperties = {
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  padding: 12,
  borderRadius: 8,
  border: '1px solid #e5e7eb',
  backgroundColor: '#fff',
}
