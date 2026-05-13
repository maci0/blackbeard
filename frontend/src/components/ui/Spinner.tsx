import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

export function Spinner({ className, size = 'md', label = 'Loading' }: { className?: string; size?: 'sm' | 'md' | 'lg'; label?: string }) {
  const sizeClasses = { sm: 'h-3.5 w-3.5', md: 'h-5 w-5', lg: 'h-8 w-8' }
  return (
    <span role="status">
      <Loader2 className={cn('animate-spin motion-reduce:animate-none', sizeClasses[size], className)} aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </span>
  )
}
