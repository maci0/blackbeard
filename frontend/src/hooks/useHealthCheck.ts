import { useState, useCallback, useEffect, useRef } from 'react'
import { api } from '@/api/client'

type HealthStatus = 'connected' | 'degraded' | 'disconnected'

interface HealthCheckResult {
  status: HealthStatus
  lastChecked: Date | null
}

interface HealthResponse {
  status: string
  service: string
  version: string
}

const POLL_INTERVAL_MS = 30_000

export function useHealthCheck(): HealthCheckResult {
  const [status, setStatus] = useState<HealthStatus>('disconnected')
  const [lastChecked, setLastChecked] = useState<Date | null>(null)
  const activeRef = useRef(true)

  const check = useCallback(async () => {
    // Only commit state on an actual status transition — an unconditional
    // setLastChecked(new Date()) re-rendered Layout (and the whole routed
    // page under <Outlet />) every 30s even when nothing changed.
    const commit = (next: HealthStatus) => {
      setStatus((prev) => {
        if (prev !== next) setLastChecked(new Date())
        return next
      })
    }
    try {
      const data = await api.get<HealthResponse>('/api/v1/health')
      if (!activeRef.current) return
      commit(data.status === 'ok' ? 'connected' : 'degraded')
    } catch (err) {
      if (!activeRef.current) return
      console.warn('[health] check failed:', err)
      commit('disconnected')
    }
  }, [])

  useEffect(() => {
    activeRef.current = true
    void check()
    const id = setInterval(() => void check(), POLL_INTERVAL_MS)
    return () => {
      activeRef.current = false
      clearInterval(id)
    }
  }, [check])

  return { status, lastChecked }
}
