import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import * as Dialog from '@radix-ui/react-dialog'
import {
  Search,
  LayoutDashboard,
  PenTool,
  Database,
  Play,
  Cpu,
  Wrench,
  Users,
  Shield,
  Store,
  Timer,
  Settings,
  MessageSquare,
  ScrollText,
  Plus,
  ArrowDownToLine,
  CornerDownLeft,
} from 'lucide-react'
import { useResourceStore } from '@/stores/resourceStore'
import { PLURAL_TO_KIND } from '@/lib/kinds'
import { cn } from '@/lib/utils'
import { KindBadge } from './KindBadge'

interface CommandItem {
  id: string
  label: string
  category: 'Pages' | 'Resources' | 'Actions'
  path: string
  icon?: React.ReactNode
  badge?: string
}

const PAGE_ITEMS: CommandItem[] = [
  {
    id: 'page-dashboard',
    label: 'Dashboard',
    category: 'Pages',
    path: '/dashboard',
    icon: <LayoutDashboard className="h-4 w-4" />,
  },
  {
    id: 'page-studio',
    label: 'Studio',
    category: 'Pages',
    path: '/studio',
    icon: <PenTool className="h-4 w-4" />,
  },
  {
    id: 'page-resources',
    label: 'Resources',
    category: 'Pages',
    path: '/resources',
    icon: <Database className="h-4 w-4" />,
  },
  {
    id: 'page-executions',
    label: 'Executions',
    category: 'Pages',
    path: '/executions',
    icon: <Play className="h-4 w-4" />,
  },
  {
    id: 'page-models',
    label: 'Models',
    category: 'Pages',
    path: '/models',
    icon: <Cpu className="h-4 w-4" />,
  },
  {
    id: 'page-chat',
    label: 'Chat',
    category: 'Pages',
    path: '/chat',
    icon: <MessageSquare className="h-4 w-4" />,
  },
  {
    id: 'page-tools',
    label: 'Tools',
    category: 'Pages',
    path: '/tools',
    icon: <Wrench className="h-4 w-4" />,
  },
  {
    id: 'page-users',
    label: 'Users',
    category: 'Pages',
    path: '/users',
    icon: <Users className="h-4 w-4" />,
  },
  {
    id: 'page-roles',
    label: 'Roles',
    category: 'Pages',
    path: '/roles',
    icon: <Shield className="h-4 w-4" />,
  },
  {
    id: 'page-audit-logs',
    label: 'Audit Logs',
    category: 'Pages',
    path: '/audit-logs',
    icon: <ScrollText className="h-4 w-4" />,
  },
  {
    id: 'page-marketplace',
    label: 'Marketplace',
    category: 'Pages',
    path: '/marketplace',
    icon: <Store className="h-4 w-4" />,
  },
  {
    id: 'page-automations',
    label: 'Automations',
    category: 'Pages',
    path: '/automations',
    icon: <Timer className="h-4 w-4" />,
  },
  {
    id: 'page-settings',
    label: 'Settings',
    category: 'Pages',
    path: '/settings',
    icon: <Settings className="h-4 w-4" />,
  },
]

const ACTION_ITEMS: CommandItem[] = [
  {
    id: 'action-new-resource',
    label: 'New resource in Studio',
    category: 'Actions',
    path: '/studio',
    icon: <Plus className="h-4 w-4" />,
  },
  {
    id: 'action-import-marketplace',
    label: 'Import from Marketplace',
    category: 'Actions',
    path: '/marketplace',
    icon: <ArrowDownToLine className="h-4 w-4" />,
  },
  {
    id: 'action-add-model',
    label: 'Add Model',
    category: 'Actions',
    path: '/models',
    icon: <Cpu className="h-4 w-4" />,
  },
]

const MAX_RESULTS = 20

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const resources = useResourceStore((s) => s.resources)

  const resourceItems = useMemo<CommandItem[]>(() => {
    const items: CommandItem[] = []
    for (const [kindPlural, list] of Object.entries(resources)) {
      const kind = PLURAL_TO_KIND[kindPlural]
      if (!kind || !list) continue
      for (const r of list) {
        items.push({
          id: `resource-${kindPlural}-${r.metadata.name}`,
          label: r.metadata.name,
          category: 'Resources',
          path: `/resources/${kindPlural}/${r.metadata.name}`,
          badge: kind,
        })
      }
    }
    return items
  }, [resources])

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim()
    const all = [...PAGE_ITEMS, ...resourceItems, ...ACTION_ITEMS]
    if (!q) return all.slice(0, MAX_RESULTS)
    return all.filter((item) => item.label.toLowerCase().includes(q)).slice(0, MAX_RESULTS)
  }, [query, resourceItems])

  const grouped = useMemo(() => {
    const groups: { category: string; items: CommandItem[] }[] = []
    const seen = new Set<string>()
    for (const item of filtered) {
      if (!seen.has(item.category)) {
        seen.add(item.category)
        groups.push({ category: item.category, items: [] })
      }
      groups.find((g) => g.category === item.category)!.items.push(item)
    }
    return groups
  }, [filtered])

  useEffect(() => {
    if (open) {
      setQuery('')
      setActiveIndex(0)
    }
  }, [open])

  useEffect(() => {
    setActiveIndex(0)
  }, [query])

  const select = useCallback(
    (item: CommandItem) => {
      onOpenChange(false)
      void navigate(item.path)
    },
    [navigate, onOpenChange],
  )

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setActiveIndex((i) => (i + 1) % filtered.length)
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActiveIndex((i) => (i - 1 + filtered.length) % filtered.length)
      } else if (e.key === 'Enter' && filtered[activeIndex]) {
        e.preventDefault()
        select(filtered[activeIndex])
      }
    },
    [filtered, activeIndex, select],
  )

  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-index="${activeIndex}"]`)
    el?.scrollIntoView({ block: 'nearest' })
  }, [activeIndex])

  let flatIndex = -1

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" />
        <Dialog.Content
          className="fixed left-1/2 top-[20%] z-50 w-full max-w-lg -translate-x-1/2 overflow-hidden rounded-lg border bg-card shadow-2xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
          onKeyDown={handleKeyDown}
          aria-label="Command palette"
        >
          <Dialog.Title className="sr-only">Command palette</Dialog.Title>
          <Dialog.Description className="sr-only">
            Search pages, resources, and actions. Use arrow keys to navigate and Enter to select.
          </Dialog.Description>
          <div className="flex items-center gap-2 border-b px-3">
            <Search className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search pages, resources, actions..."
              className="flex-1 bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground"
              autoFocus
              aria-label="Search"
              aria-activedescendant={
                filtered[activeIndex] ? `cmd-item-${filtered[activeIndex].id}` : undefined
              }
              role="combobox"
              aria-expanded={filtered.length > 0}
              aria-controls="command-palette-list"
              aria-autocomplete="list"
            />
          </div>
          <div
            ref={listRef}
            id="command-palette-list"
            role="listbox"
            className="max-h-72 overflow-y-auto p-1"
          >
            {grouped.length === 0 ? (
              <div className="px-3 py-6 text-center text-sm text-muted-foreground">
                No results found
              </div>
            ) : (
              grouped.map((group) => (
                <div key={group.category} role="group" aria-label={group.category}>
                  <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
                    {group.category}
                  </div>
                  {group.items.map((item) => {
                    flatIndex++
                    const idx = flatIndex
                    return (
                      <div
                        key={item.id}
                        id={`cmd-item-${item.id}`}
                        role="option"
                        aria-selected={activeIndex === idx}
                        data-index={idx}
                        onMouseEnter={() => setActiveIndex(idx)}
                        onClick={() => select(item)}
                        className={cn(
                          'flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors',
                          activeIndex === idx
                            ? 'bg-accent text-foreground'
                            : 'text-muted-foreground hover:bg-accent/50',
                        )}
                      >
                        {item.icon && (
                          <span className="flex h-5 w-5 shrink-0 items-center justify-center">
                            {item.icon}
                          </span>
                        )}
                        <span className="flex-1 truncate">{item.label}</span>
                        {item.badge && <KindBadge kind={item.badge} />}
                        {activeIndex === idx && (
                          <CornerDownLeft
                            className="h-3 w-3 shrink-0 text-muted-foreground"
                            aria-hidden="true"
                          />
                        )}
                      </div>
                    )
                  })}
                </div>
              ))
            )}
          </div>
          <div className="flex items-center justify-between border-t px-3 py-2 text-xs text-muted-foreground">
            <div className="flex items-center gap-3" aria-hidden="true">
              <span className="flex items-center gap-1">
                <kbd className="rounded border bg-muted px-1 py-0.5 font-mono text-[10px]">
                  &uarr;&darr;
                </kbd>
                navigate
              </span>
              <span className="flex items-center gap-1">
                <kbd className="rounded border bg-muted px-1 py-0.5 font-mono text-[10px]">
                  &crarr;
                </kbd>
                select
              </span>
              <span className="flex items-center gap-1">
                <kbd className="rounded border bg-muted px-1 py-0.5 font-mono text-[10px]">esc</kbd>
                close
              </span>
            </div>
            <span aria-live="polite" aria-atomic="true">
              {filtered.length} results
            </span>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
