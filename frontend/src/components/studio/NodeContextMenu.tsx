import { useCallback, useEffect, useRef } from 'react'
import { Pencil, Copy, Trash2, ClipboardCopy, FlaskConical } from 'lucide-react'
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

const TESTABLE_TYPES = new Set(['agent', 'task'])

function nodeTypeLabel(nodeType: string): string {
  switch (nodeType) {
    case 'agent':
      return 'Agent'
    case 'task':
      return 'Task'
    case 'tool':
      return 'Tool'
    case 'flowStep':
      return 'Flow Step'
    case 'pii':
      return 'PII Guard'
    case 'condition':
      return 'Condition'
    case 'router':
      return 'Router'
    case 'parallel':
      return 'Parallel'
    case 'crewGroup':
      return 'Crew Group'
    case 'stickyNote':
      return 'Sticky Note'
    case 'ifElse':
      return 'IF/ELSE'
    case 'switch':
      return 'Switch'
    case 'merge':
      return 'Merge'
    case 'filter':
      return 'Filter'
    case 'gate':
      return 'Gate'
    case 'crewComponent':
      return 'Crew'
    case 'loop':
      return 'Loop'
    default:
      return 'Node'
  }
}

export function NodeContextMenu({ menu, onClose }: NodeContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null)
  const { setSelectedNode, removeNode, addNode, nodes } = useStudioStore((s) => ({
    setSelectedNode: s.setSelectedNode,
    removeNode: s.removeNode,
    addNode: s.addNode,
    nodes: s.nodes,
  }))
  const toasts = useToastStore()

  // close on click outside or Escape
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

  // adjust position so the menu stays within viewport
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

  const handleEdit = useCallback(() => {
    setSelectedNode(menu.nodeId)
    onClose()
  }, [setSelectedNode, menu.nodeId, onClose])

  const handleDuplicate = useCallback(() => {
    const source = nodes.find((n) => n.id === menu.nodeId)
    if (!source) {
      onClose()
      return
    }
    const newNode = {
      id: `${source.type ?? 'node'}-${crypto.randomUUID()}`,
      type: source.type,
      position: { x: source.position.x + 40, y: source.position.y + 40 },
      data: {
        ...getDefaultNodeData(source.type ?? ''),
        ...structuredClone(source.data),
      },
    }
    addNode(newNode)
    toasts.success(`Duplicated ${nodeTypeLabel(menu.nodeType)}`)
    onClose()
  }, [nodes, menu.nodeId, menu.nodeType, addNode, toasts, onClose])

  const handleDelete = useCallback(() => {
    removeNode(menu.nodeId)
    onClose()
  }, [removeNode, menu.nodeId, onClose])

  const handleCopyId = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(menu.nodeId)
      toasts.success('Node ID copied')
    } catch {
      toasts.error('Failed to copy node ID')
    }
    onClose()
  }, [menu.nodeId, toasts, onClose])

  const handleTest = useCallback(() => {
    // select the node first so the property panel opens, then let the user
    // click Test Agent/Test Task in the property panel
    setSelectedNode(menu.nodeId)
    onClose()
  }, [setSelectedNode, menu.nodeId, onClose])

  const isTestable = TESTABLE_TYPES.has(menu.nodeType)
  const testLabel = menu.nodeType === 'agent' ? 'Test Agent' : 'Test Task'

  return (
    <div
      ref={menuRef}
      role="menu"
      aria-label={`${nodeTypeLabel(menu.nodeType)} actions`}
      className="fixed z-50 min-w-[180px] rounded-lg border border-border bg-card py-1 shadow-lg animate-in fade-in-0 zoom-in-95"
      style={{ left: menu.x, top: menu.y }}
    >
      <button
        role="menuitem"
        className="mx-1 flex w-[calc(100%-8px)] cursor-pointer items-center gap-2 rounded-sm px-3 py-2 text-left text-xs font-medium text-foreground transition-colors hover:bg-muted focus:bg-muted focus:outline-none"
        onClick={handleEdit}
      >
        <Pencil className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
        Edit
      </button>
      <button
        role="menuitem"
        className="mx-1 flex w-[calc(100%-8px)] cursor-pointer items-center gap-2 rounded-sm px-3 py-2 text-left text-xs font-medium text-foreground transition-colors hover:bg-muted focus:bg-muted focus:outline-none"
        onClick={handleDuplicate}
      >
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
        className="mx-1 flex w-[calc(100%-8px)] cursor-pointer items-center gap-2 rounded-sm px-3 py-2 text-left text-xs font-medium text-foreground transition-colors hover:bg-muted focus:bg-muted focus:outline-none"
        onClick={() => void handleCopyId()}
      >
        <ClipboardCopy className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
        Copy ID
      </button>

      {isTestable && (
        <button
          role="menuitem"
          className="mx-1 flex w-[calc(100%-8px)] cursor-pointer items-center gap-2 rounded-sm px-3 py-2 text-left text-xs font-medium text-foreground transition-colors hover:bg-muted focus:bg-muted focus:outline-none"
          onClick={handleTest}
        >
          <FlaskConical className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          {testLabel}
        </button>
      )}
    </div>
  )
}
