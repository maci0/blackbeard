import { memo, useCallback, useRef, useEffect } from 'react'
import { type NodeProps } from '@xyflow/react'
import { StickyNote } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useStudioStore } from '@/stores/studioStore'

const COLOR_STYLES: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  yellow: {
    bg: 'bg-amber-50 dark:bg-amber-950/60',
    border: 'border-amber-200 dark:border-amber-800',
    text: 'text-amber-900 dark:text-amber-100',
    icon: 'text-amber-400 dark:text-amber-600',
  },
  blue: {
    bg: 'bg-sky-50 dark:bg-sky-950/60',
    border: 'border-sky-200 dark:border-sky-800',
    text: 'text-sky-900 dark:text-sky-100',
    icon: 'text-sky-400 dark:text-sky-600',
  },
  green: {
    bg: 'bg-emerald-50 dark:bg-emerald-950/60',
    border: 'border-emerald-200 dark:border-emerald-800',
    text: 'text-emerald-900 dark:text-emerald-100',
    icon: 'text-emerald-400 dark:text-emerald-600',
  },
  pink: {
    bg: 'bg-pink-50 dark:bg-pink-950/60',
    border: 'border-pink-200 dark:border-pink-800',
    text: 'text-pink-900 dark:text-pink-100',
    icon: 'text-pink-400 dark:text-pink-600',
  },
}

export default memo(function StickyNoteNode({ id, data, selected }: NodeProps) {
  const text = (data['text'] as string | undefined) ?? ''
  const color = (data['color'] as string | undefined) ?? 'yellow'
  const style = COLOR_STYLES[color] ?? COLOR_STYLES['yellow']!
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const updateNodeData = useStudioStore((s) => s.updateNodeData)

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      updateNodeData(id, { text: e.target.value })
    },
    [id, updateNodeData],
  )

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.max(el.scrollHeight, 48)}px`
  }, [text])

  return (
    <div
      aria-label={`Sticky note: ${text.slice(0, 40) || 'empty'}`}
      className={cn(
        'w-[180px] rounded-lg border shadow-sm transition-all duration-150',
        style.bg,
        style.border,
        selected && 'shadow-md ring-2 ring-amber-300 ring-offset-1 dark:ring-offset-slate-900',
      )}
    >
      <div className="flex items-center gap-1 px-2 py-1">
        <StickyNote className={cn('h-3 w-3 shrink-0', style.icon)} />
        <span className={cn('text-[10px] font-bold uppercase tracking-wider', style.icon)}>
          Note
        </span>
      </div>
      <div className="px-2 pb-2">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleChange}
          placeholder="Type a note..."
          rows={2}
          className={cn(
            'w-full resize-none bg-transparent text-xs leading-relaxed placeholder:opacity-40 focus-visible:outline-none',
            style.text,
          )}
        />
      </div>
    </div>
  )
})
