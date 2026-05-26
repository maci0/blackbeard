import { cn } from '@/lib/utils'

interface PresenceUser {
  id: string
  name: string
}

const COLORS = [
  'bg-rose-500',
  'bg-blue-500',
  'bg-emerald-500',
  'bg-amber-500',
  'bg-violet-500',
  'bg-pink-500',
  'bg-cyan-500',
  'bg-orange-500',
]

function hashColor(id: string): string {
  let hash = 0
  for (let i = 0; i < id.length; i++) {
    hash = ((hash << 5) - hash + id.charCodeAt(i)) | 0
  }
  return COLORS[Math.abs(hash) % COLORS.length] ?? COLORS[0]!
}

function getInitial(name: string): string {
  return (name.charAt(0) || '?').toUpperCase()
}

const MAX_VISIBLE = 5

export function PresenceAvatars({
  users,
  className,
}: {
  users: PresenceUser[]
  className?: string
}) {
  if (users.length === 0) return null

  const visible = users.slice(0, MAX_VISIBLE)
  const overflow = users.length - MAX_VISIBLE

  return (
    <div
      className={cn('flex items-center -space-x-1.5', className)}
      aria-label={`${users.length} user${users.length !== 1 ? 's' : ''} viewing`}
    >
      {visible.map((user) => (
        <div
          key={user.id}
          className={cn(
            'flex h-7 w-7 items-center justify-center rounded-full border-2 border-background text-[10px] font-bold text-white',
            hashColor(user.id),
          )}
          title={user.name}
          aria-label={user.name}
        >
          {getInitial(user.name)}
        </div>
      ))}
      {overflow > 0 && (
        <div
          className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-background bg-muted text-[10px] font-bold text-muted-foreground"
          title={`${overflow} more user${overflow !== 1 ? 's' : ''}`}
          aria-label={`${overflow} more users`}
        >
          +{overflow}
        </div>
      )}
    </div>
  )
}
