import { useState, useEffect, memo } from 'react'
import { timeAgo, formatDate } from '@/lib/formatters'

const listeners = new Set<() => void>()
let tickInterval: ReturnType<typeof setInterval> | null = null

function subscribe(cb: () => void) {
  listeners.add(cb)
  if (listeners.size === 1) {
    tickInterval = setInterval(() => {
      for (const fn of listeners) fn()
    }, 60_000)
  }
  return () => {
    listeners.delete(cb)
    if (listeners.size === 0 && tickInterval) {
      clearInterval(tickInterval)
      tickInterval = null
    }
  }
}

export const SmartTime = memo(function SmartTime({ date }: { date: string | null | undefined }) {
  const [, setTick] = useState(0)

  useEffect(() => subscribe(() => setTick((t) => t + 1)), [])

  if (!date) return <span>—</span>

  return (
    <time dateTime={date} title={formatDate(date)}>
      {timeAgo(date)}
    </time>
  )
})
