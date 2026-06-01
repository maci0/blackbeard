import { type DragEvent, useState, useEffect } from 'react'
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
  Search,
  ToggleLeft,
  Combine,
  Filter,
  Lock,
  Repeat,
  Users,
} from 'lucide-react'
import { useStudioStore } from '@/stores/studioStore'
import { useResourceStore } from '@/stores/resourceStore'
import type { Resource } from '@/lib/types'
import { getDefaultNodeData } from './defaults'

interface PaletteItem {
  type: string
  label: string
  icon: React.ElementType
  headerBg: string
  iconBg: string
  textColor: string
  borderColor: string
  cardShape?: {
    className?: string
    style?: React.CSSProperties
  }
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
    cardShape: {
      style: { clipPath: 'polygon(0% 0%, 100% 0%, 100% 80%, 50% 100%, 0% 80%)' },
    },
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
    cardShape: {
      style: {
        clipPath: 'polygon(6px 0%, calc(100% - 6px) 0%, 100% 6px, 100% 100%, 0% 100%, 0% 6px)',
      },
    },
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
    cardShape: { className: 'rounded-[12px]' },
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
    cardShape: { className: 'rounded-2xl' },
  },
  {
    type: 'ifElse',
    label: 'IF/ELSE',
    icon: GitBranch,
    headerBg: 'bg-gradient-to-r from-amber-500 to-yellow-400',
    iconBg: 'bg-white/20',
    textColor: 'text-amber-700 dark:text-amber-300',
    borderColor:
      'border-amber-200 hover:border-amber-400 dark:border-amber-800 dark:hover:border-amber-600',
    cardShape: {
      style: {
        clipPath: 'polygon(6px 0%, calc(100% - 6px) 0%, 100% 6px, 100% 100%, 0% 100%, 0% 6px)',
      },
    },
  },
  {
    type: 'switch',
    label: 'Switch',
    icon: ToggleLeft,
    headerBg: 'bg-gradient-to-r from-cyan-600 to-cyan-400',
    iconBg: 'bg-white/20',
    textColor: 'text-cyan-700 dark:text-cyan-300',
    borderColor:
      'border-cyan-200 hover:border-cyan-400 dark:border-cyan-800 dark:hover:border-cyan-600',
    cardShape: { className: 'rounded-[12px]' },
  },
  {
    type: 'merge',
    label: 'Merge',
    icon: Combine,
    headerBg: 'bg-gradient-to-r from-indigo-600 to-indigo-400',
    iconBg: 'bg-white/20',
    textColor: 'text-indigo-700 dark:text-indigo-300',
    borderColor:
      'border-indigo-200 hover:border-indigo-400 dark:border-indigo-800 dark:hover:border-indigo-600',
    cardShape: { className: 'rounded-2xl' },
  },
  {
    type: 'filter',
    label: 'Filter',
    icon: Filter,
    headerBg: 'bg-gradient-to-r from-orange-500 to-orange-400',
    iconBg: 'bg-white/20',
    textColor: 'text-orange-700 dark:text-orange-300',
    borderColor:
      'border-orange-200 hover:border-orange-400 dark:border-orange-800 dark:hover:border-orange-600',
    cardShape: {
      style: {
        clipPath: 'polygon(6px 0%, calc(100% - 6px) 0%, 100% 6px, 100% 100%, 0% 100%, 0% 6px)',
      },
    },
  },
  {
    type: 'gate',
    label: 'Gate',
    icon: Lock,
    headerBg: 'bg-gradient-to-r from-teal-600 to-teal-400',
    iconBg: 'bg-white/20',
    textColor: 'text-teal-700 dark:text-teal-300',
    borderColor:
      'border-teal-200 hover:border-teal-400 dark:border-teal-800 dark:hover:border-teal-600',
    cardShape: { className: 'rounded-2xl' },
  },
  {
    type: 'loop',
    label: 'Loop',
    icon: Repeat,
    headerBg: 'bg-gradient-to-r from-pink-500 to-pink-400',
    iconBg: 'bg-white/20',
    textColor: 'text-pink-700 dark:text-pink-300',
    borderColor:
      'border-pink-200 hover:border-pink-400 dark:border-pink-800 dark:hover:border-pink-600',
    cardShape: { className: 'rounded-xl' },
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
      title={item.label}
      aria-label={`Add ${item.label} node to canvas`}
      className={`cursor-grab select-none overflow-hidden ${item.cardShape?.className ?? 'rounded-lg'} border bg-card shadow-sm transition-all duration-150 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing ${item.borderColor}`}
      style={item.cardShape?.style}
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

function CrewComponentCard({ crew }: { crew: Resource }) {
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- spec fields are runtime-typed
  const agentCount = ((crew.spec.agents as unknown[]) ?? []).length
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- spec fields are runtime-typed
  const taskCount = ((crew.spec.tasks as unknown[]) ?? []).length
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- spec fields are runtime-typed
  const inputs = (crew.spec.inputs as Array<{ name: string }>) ?? []

  function onDragStart(event: DragEvent<HTMLDivElement>) {
    event.dataTransfer.setData('application/reactflow', 'crewComponent')
    event.dataTransfer.setData(
      'application/crewdata',
      JSON.stringify({
        crew_name: crew.metadata.name,
        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- runtime data
        description: (crew.spec.description as string) ?? '',
        agent_count: agentCount,
        task_count: taskCount,
        inputs,
      }),
    )
    event.dataTransfer.effectAllowed = 'move'
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      const { addNode, nodes } = useStudioStore.getState()
      const offset = nodes.length * 30
      addNode({
        id: `crewComponent-${crypto.randomUUID()}`,
        type: 'crewComponent',
        position: { x: 250 + offset, y: 150 + offset },
        data: {
          crew_name: crew.metadata.name,
          description: crew.spec.description ?? '',
          agent_count: agentCount,
          task_count: taskCount,
          inputs,
        },
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
      title={crew.metadata.name}
      aria-label={`Add crew ${crew.metadata.name} as component`}
      className="cursor-grab select-none overflow-hidden rounded-lg border-2 border-primary/20 bg-card shadow-sm transition-all duration-150 hover:border-primary/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing"
    >
      <div className="flex items-center gap-1 bg-gradient-to-r from-primary to-primary/80 px-1.5 py-1.5">
        <Users className="h-3 w-3 text-white/90" />
        <span className="truncate text-[9px] font-bold text-white">{crew.metadata.name}</span>
      </div>
      <div className="flex items-center gap-1 px-1.5 py-1">
        <span className="text-[10px] text-muted-foreground" aria-label={`${agentCount} agents`}>
          {agentCount}A
        </span>
        <span className="text-[10px] text-muted-foreground" aria-label={`${taskCount} tasks`}>
          {taskCount}T
        </span>
      </div>
    </div>
  )
}

export default function Palette() {
  const [filter, setFilter] = useState('')
  const crews = useResourceStore((s) => s.resources['crews']) ?? []
  const hasCrew = useResourceStore((s) => 'crews' in s.resources)
  const fetchResources = useResourceStore((s) => s.fetchResources)

  useEffect(() => {
    if (!hasCrew) void fetchResources('crews')
  }, [hasCrew, fetchResources])

  const filtered = filter
    ? ITEMS.filter((item) => item.label.toLowerCase().includes(filter.toLowerCase()))
    : ITEMS

  const filteredCrews = filter
    ? crews.filter((c) => c.metadata.name.toLowerCase().includes(filter.toLowerCase()))
    : crews

  return (
    <aside
      aria-label="Node palette"
      data-tour="palette"
      className="hidden w-[108px] shrink-0 flex-col border-r bg-card sm:flex"
    >
      <div className="border-b px-2 pb-2 pt-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-1.5 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter…"
            aria-label="Filter palette nodes"
            className="w-full rounded-md border bg-background py-1 pl-6 pr-1 text-[10px] text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </div>
      </div>
      <div className="flex flex-col gap-2 overflow-y-auto p-2 pt-2">
        {filtered.length > 0
          ? filtered.map((item) => <PaletteCard key={item.type} item={item} />)
          : !filteredCrews.length && (
              <p className="py-4 text-center text-[10px] text-muted-foreground">No matches</p>
            )}

        {/* My Components section */}
        {filteredCrews.length > 0 && (
          <>
            <div className="mt-1 border-t pt-2" role="group" aria-label="My Crews">
              <p
                className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70"
                aria-hidden="true"
              >
                My Crews
              </p>
            </div>
            {filteredCrews.map((crew) => (
              <CrewComponentCard key={crew.metadata.name} crew={crew} />
            ))}
          </>
        )}
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
