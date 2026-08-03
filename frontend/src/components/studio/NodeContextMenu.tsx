import { useCallback, useEffect, useRef } from 'react'
import { Pencil, Copy, Trash2, ClipboardCopy } from 'lucide-react'
import { useStudioStore } from '@/stores/studioStore'
import { useToastStore } from '@/stores/toastStore'
import { getDefaultNodeData } from './defaults'

export interface NodeContextMenuState {
  x: number
  y: number
  nodeId: string
  nodeType: string
}

interface NodeContextMenuProps {
  menu: NodeContextMenuState
  onClose: () => void
}

const NODE_LABELS: Record<string, string> = {
  agent: 'Agent',
  task: 'Task',
  tool: 'Tool',
  flowStep: 'Flow Step',
  pii: 'PII Guard',
  condition: 'Condition',
  router: 'Router',
  parallel: 'Parallel',
  crewGroup: 'Crew Group',
  stickyNote: 'Sticky Note',
  ifElse: 'IF/ELSE',
  switch: 'Switch',
  merge: 'Merge',
  filter: 'Filter',
  gate: 'Gate',
  crewComponent: 'Crew',
  loop: 'Loop',
}

function nodeTypeLabel(nodeType: string): string {
  return NODE_LABELS[nodeType] ?? 'Node'
}

const menuItemClass =
  'mx-1 flex w-[calc(100%-8px)] cursor-pointer items-center gap-2 rounded-sm px-3 py-2 text-left text-xs font-medium text-foreground transition-colors hover:bg-muted focus:bg-muted focus:outline-none'

export function NodeContextMenu({ menu, onClose }: NodeContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null)
  const { setSelectedNode, removeNode, addNode, nodes } = useStudioStore((s) => ({
    setSelectedNode: s.setSelectedNode,
    removeNode: s.removeNode,
    addNode: s.addNode,
    nodes: s.nodes,
  }))
  const toasts = useToastStore()

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as HTMLElement)) {
        onClose()
      }
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [onClose])

  useEffect(() => {
    if (!menuRef.current) return
    const el = menuRef.current
    const rect = el.getBoundingClientRect()
    if (rect.right > window.innerWidth) {
      el.style.left = `${menu.x - rect.width}px`
    }
    if (rect.bottom > window.innerHeight) {
      el.style.top = `${menu.y - rect.height}px`
    }
  }, [menu.x, menu.y])

  const handleEdit = () => {
    setSelectedNode(menu.nodeId)
    onClose()
  }

  const handleDuplicate = () => {
    const source = nodes.find((n) => n.id === menu.nodeId)
    if (!source) {
      onClose()
      return
    }
    addNode({
      id: `${source.type ?? 'node'}-${crypto.randomUUID()}`,
      type: source.type,
      position: { x: source.position.x + 40, y: source.position.y + 40 },
      data: {
        ...getDefaultNodeData(source.type ?? ''),
        ...structuredClone(source.data),
      },
    })
    toasts.success(`Duplicated ${nodeTypeLabel(menu.nodeType)}`)
    onClose()
  }

  const handleDelete = () => {
    removeNode(menu.nodeId)
    onClose()
  }

  const handleCopyId = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(menu.nodeId)
      toasts.success('Node ID copied')
    } catch {
      toasts.error('Failed to copy node ID')
    }
    onClose()
  }, [menu.nodeId, toasts, onClose])

  return (
    <div
      ref={menuRef}
      role="menu"
      aria-label={`${nodeTypeLabel(menu.nodeType)} actions`}
      className="fixed z-50 min-w-[180px] rounded-lg border border-border bg-card py-1 shadow-lg animate-in fade-in-0 zoom-in-95"
      style={{ left: menu.x, top: menu.y }}
    >
      <button role="menuitem" className={menuItemClass} onClick={handleEdit}>
        <Pencil className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
        Edit
      </button>
      <button role="menuitem" className={menuItemClass} onClick={handleDuplicate}>
        <Copy className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
        Duplicate
      </button>
      <button
        role="menuitem"
        className="mx-1 flex w-[calc(100%-8px)] cursor-pointer items-center gap-2 rounded-sm px-3 py-2 text-left text-xs font-medium text-destructive transition-colors hover:bg-destructive/10 focus:bg-destructive/10 focus:outline-none"
        onClick={handleDelete}
      >
        <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
        Delete
      </button>

      <div className="mx-2 my-1 h-px bg-border" role="separator" />

      <button
        role="menuitem"
        className={menuItemClass}
        onClick={() => void handleCopyId()}
      >
        <ClipboardCopy className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
        Copy ID
      </button>
    </div>
  )
}
