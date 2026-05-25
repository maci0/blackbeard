import type { DragEvent } from 'react'
import {
  User,
  ListChecks,
  Wrench,
  Workflow,
  ShieldCheck,
  GitBranch,
  Route,
  Columns3,
  StickyNote,
} from 'lucide-react'
import { useStudioStore } from '@/stores/studioStore'
import { getDefaultNodeData } from './defaults'

interface PaletteItem {
  type: string
  label: string
  icon: React.ElementType
  headerBg: string
  iconBg: string
  textColor: string
  borderColor: string
}

function addNodeFromPalette(type: string) {
  const { addNode, nodes } = useStudioStore.getState()
  const offset = nodes.length * 30
  addNode({
    id: `${type}-${crypto.randomUUID()}`,
    type,
    position: { x: 250 + offset, y: 150 + offset },
    data: getDefaultNodeData(type),
  })
}

const ITEMS: PaletteItem[] = [
  {
    type: 'agent',
    label: 'Agent',
    icon: User,
    headerBg: 'bg-gradient-to-r from-violet-600 to-violet-500',
    iconBg: 'bg-white/20',
    textColor: 'text-violet-700 dark:text-violet-300',
    borderColor:
      'border-violet-200 hover:border-violet-400 dark:border-violet-800 dark:hover:border-violet-600',
  },
  {
    type: 'task',
    label: 'Task',
    icon: ListChecks,
    headerBg: 'bg-gradient-to-r from-blue-600 to-blue-500',
    iconBg: 'bg-white/20',
    textColor: 'text-blue-700 dark:text-blue-300',
    borderColor:
      'border-blue-200 hover:border-blue-400 dark:border-blue-800 dark:hover:border-blue-600',
  },
  {
    type: 'tool',
    label: 'Tool',
    icon: Wrench,
    headerBg: 'bg-gradient-to-r from-emerald-600 to-emerald-500',
    iconBg: 'bg-white/20',
    textColor: 'text-emerald-700 dark:text-emerald-300',
    borderColor:
      'border-emerald-200 hover:border-emerald-400 dark:border-emerald-800 dark:hover:border-emerald-600',
  },
  {
    type: 'flowStep',
    label: 'Flow Step',
    icon: Workflow,
    headerBg: 'bg-gradient-to-r from-amber-600 to-amber-500',
    iconBg: 'bg-white/20',
    textColor: 'text-amber-700 dark:text-amber-300',
    borderColor:
      'border-amber-200 hover:border-amber-400 dark:border-amber-800 dark:hover:border-amber-600',
  },
  {
    type: 'pii',
    label: 'PII Filter',
    icon: ShieldCheck,
    headerBg: 'bg-gradient-to-r from-rose-600 to-red-500',
    iconBg: 'bg-white/20',
    textColor: 'text-rose-700 dark:text-rose-300',
    borderColor:
      'border-rose-200 hover:border-rose-400 dark:border-rose-800 dark:hover:border-rose-600',
  },
  {
    type: 'condition',
    label: 'Condition',
    icon: GitBranch,
    headerBg: 'bg-gradient-to-r from-amber-600 to-yellow-500',
    iconBg: 'bg-white/20',
    textColor: 'text-amber-700 dark:text-amber-300',
    borderColor:
      'border-amber-200 hover:border-amber-400 dark:border-amber-800 dark:hover:border-amber-600',
  },
  {
    type: 'router',
    label: 'Router',
    icon: Route,
    headerBg: 'bg-gradient-to-r from-cyan-600 to-cyan-500',
    iconBg: 'bg-white/20',
    textColor: 'text-cyan-700 dark:text-cyan-300',
    borderColor:
      'border-cyan-200 hover:border-cyan-400 dark:border-cyan-800 dark:hover:border-cyan-600',
  },
  {
    type: 'parallel',
    label: 'Parallel',
    icon: Columns3,
    headerBg: 'bg-gradient-to-r from-purple-600 to-purple-500',
    iconBg: 'bg-white/20',
    textColor: 'text-purple-700 dark:text-purple-300',
    borderColor:
      'border-purple-200 hover:border-purple-400 dark:border-purple-800 dark:hover:border-purple-600',
  },
  {
    type: 'stickyNote',
    label: 'Note',
    icon: StickyNote,
    headerBg: 'bg-gradient-to-r from-amber-400 to-yellow-300',
    iconBg: 'bg-white/20',
    textColor: 'text-amber-700 dark:text-amber-300',
    borderColor:
      'border-amber-200 hover:border-amber-400 dark:border-amber-800 dark:hover:border-amber-600',
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
      addNodeFromPalette(item.type)
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
      className="hidden w-[108px] shrink-0 flex-col border-r bg-card sm:flex"
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
          Drag onto canvas or press Enter/Space to add
        </p>
      </div>
    </aside>
  )
}

export function MobilePalette() {
  return (
    <div
      role="toolbar"
      aria-label="Add nodes"
      className="flex shrink-0 items-center justify-center gap-2 border-t bg-card px-3 py-2 sm:hidden"
    >
      {ITEMS.map((item) => {
        const Icon = item.icon
        return (
          <button
            key={item.type}
            onClick={() => addNodeFromPalette(item.type)}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2.5 text-xs font-semibold text-white shadow-sm transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${item.headerBg}`}
            aria-label={`Add ${item.label} node`}
          >
            <Icon className="h-3.5 w-3.5" />
            {item.label}
          </button>
        )
      })}
    </div>
  )
}
