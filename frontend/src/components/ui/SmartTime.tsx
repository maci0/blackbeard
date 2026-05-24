import { useState, useEffect } from 'react'
import { timeAgo, formatDate } from '@/lib/formatters'

export function SmartTime({ date }: { date: string | null | undefined }) {
  const [, setTick] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 60_000)
    return () => clearInterval(id)
  }, [])

  if (!date) return <span>—</span>

  return (
    <time dateTime={date} title={formatDate(date)}>
      {timeAgo(date)}
    </time>
  )
}
