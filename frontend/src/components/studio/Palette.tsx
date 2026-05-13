import type { DragEvent } from 'react'
import { User, ListChecks, Wrench } from 'lucide-react'
import { useStudioStore } from '@/stores/studioStore'
import { getDefaultNodeData } from '@/lib/utils'

interface PaletteItem {
  type: string
  label: string
  icon: React.ElementType
  headerBg: string
  iconBg: string
  textColor: string
  borderColor: string
}

const ITEMS: PaletteItem[] = [
  {
    type: 'agent',
    label: 'Agent',
    icon: User,
    headerBg: 'bg-gradient-to-r from-violet-600 to-violet-500',
    iconBg: 'bg-white/20',
    textColor: 'text-violet-700',
    borderColor: 'border-violet-200 hover:border-violet-400',
  },
  {
    type: 'task',
    label: 'Task',
    icon: ListChecks,
    headerBg: 'bg-gradient-to-r from-blue-600 to-blue-500',
    iconBg: 'bg-white/20',
    textColor: 'text-blue-700',
    borderColor: 'border-blue-200 hover:border-blue-400',
  },
  {
    type: 'tool',
    label: 'Tool',
    icon: Wrench,
    headerBg: 'bg-gradient-to-r from-emerald-600 to-emerald-500',
    iconBg: 'bg-white/20',
    textColor: 'text-emerald-700',
    borderColor: 'border-emerald-200 hover:border-emerald-400',
  },
]

function PaletteCard({ item }: { item: PaletteItem }) {
  const Icon = item.icon

  function onDragStart(event: DragEvent<HTMLDivElement>) {
    event.dataTransfer.setData('application/reactflow', item.type)
    event.dataTransfer.effectAllowed = 'move'
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      const { addNode } = useStudioStore.getState()
      addNode({
        id: `${item.type}-${Date.now()}`,
        type: item.type,
        // Stagger position slightly so multiple keyboard-added nodes don't stack exactly
        position: { x: 220 + Math.random() * 120, y: 120 + Math.random() * 120 },
        data: getDefaultNodeData(item.type),
      })
    }
  }

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onKeyDown={onKeyDown}
      tabIndex={0}
      role="button"
      aria-label={`Add ${item.label} node to canvas`}
      className={`cursor-grab select-none overflow-hidden rounded-lg border bg-card shadow-sm transition-all duration-150 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing ${item.borderColor}`}
    >
      {/* Mini header matching the node style */}
      <div className={`flex items-center justify-center gap-1.5 py-2 ${item.headerBg}`}>
        <div className={`flex h-5 w-5 items-center justify-center rounded-md ${item.iconBg}`}>
          <Icon className="h-3 w-3 text-white" />
        </div>
      </div>
      {/* Label */}
      <div className="py-2 text-center">
        <span className={`text-xs font-semibold ${item.textColor}`}>{item.label}</span>
      </div>
    </div>
  )
}

export default function Palette() {
  return (
    <aside
      aria-label="Node palette"
      data-tour="palette"
      className="flex w-[108px] shrink-0 flex-col border-r bg-card"
    >
      <div className="border-b px-3 pb-2 pt-3">
        <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
          Palette
        </p>
      </div>
      <div className="flex flex-col gap-2 p-2 pt-3">
        {ITEMS.map((item) => (
          <PaletteCard key={item.type} item={item} />
        ))}
      </div>
      <div className="p-2 pt-0">
        <p className="text-center text-[10px] leading-tight text-muted-foreground">
          Drag onto canvas or press Enter to add
        </p>
      </div>
    </aside>
  )
}
