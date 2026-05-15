import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  MarkerType,
  useReactFlow,
  type Node,
  type NodeTypes,
  type EdgeTypes,
  type Connection,
  type Edge,
} from '@xyflow/react'
import { User, ListChecks, Wrench, Sparkles } from 'lucide-react'
import { useStudioStore } from '@/stores/studioStore'
import { getDefaultNodeData } from './defaults'
import AgentNode from './nodes/AgentNode'
import TaskNode from './nodes/TaskNode'
import ToolNode from './nodes/ToolNode'
import DataFlowEdge from './edges/DataFlowEdge'
import ToolAssignEdge from './edges/ToolAssignEdge'

/* ------------------------------------------------------------------ */
/* Node / Edge type registries — must be stable references             */
/* ------------------------------------------------------------------ */

const NODE_TYPES: NodeTypes = {
  agent: AgentNode,
  task: TaskNode,
  tool: ToolNode,
}

const EDGE_TYPES: EdgeTypes = {
  dataflow: DataFlowEdge,
  toolassign: ToolAssignEdge,
}

const FIT_VIEW_OPTIONS = { padding: 0.2 } as const
const SNAP_GRID: [number, number] = [20, 20]
const PRO_OPTIONS = { hideAttribution: true } as const
const DELETE_KEY_CODE = ['Delete', 'Backspace']

function pickEdgeType(nodeMap: Map<string, Node>, connection: Connection): string {
  const sourceNode = connection.source ? nodeMap.get(connection.source) : undefined
  if (sourceNode?.type === 'tool') return 'toolassign'
  return 'dataflow'
}

function minimapNodeColor(node: Node): string {
  switch (node.type) {
    case 'agent':
      return '#8b5cf6'
    case 'task':
      return '#3b82f6'
    case 'tool':
      return '#10b981'
    default:
      return '#94a3b8'
  }
}

function CanvasInner() {
  const { screenToFlowPosition } = useReactFlow()
  const [isDark, setIsDark] = useState(() => document.documentElement.classList.contains('dark'))
  useEffect(() => {
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.classList.contains('dark'))
    })
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    })
    return () => observer.disconnect()
  }, [])
  const nodes = useStudioStore((s) => s.nodes)
  const edges = useStudioStore((s) => s.edges)
  const onNodesChange = useStudioStore((s) => s.onNodesChange)
  const onEdgesChange = useStudioStore((s) => s.onEdgesChange)
  const onConnect = useStudioStore((s) => s.onConnect)
  const addNode = useStudioStore((s) => s.addNode)
  const setSelectedNode = useStudioStore((s) => s.setSelectedNode)
  const nodeMapRef = useRef(new Map<string, Node>())
  nodeMapRef.current = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault()
        useStudioStore.getState().undo()
      }
      if ((e.metaKey || e.ctrlKey) && ((e.key === 'z' && e.shiftKey) || e.key === 'y')) {
        e.preventDefault()
        useStudioStore.getState().redo()
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault()
        document.querySelector<HTMLButtonElement>('[data-tour="save-button"]')?.click()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const handleConnect = useCallback(
    (connection: Connection) => {
      const edgeType = pickEdgeType(nodeMapRef.current, connection)
      const enriched: Edge = {
        ...connection,
        id: `${connection.source}-${connection.target}-${Date.now()}`,
        type: edgeType,
        markerEnd:
          edgeType === 'dataflow'
            ? { type: MarkerType.ArrowClosed, width: 12, height: 12, color: '#94a3b8' }
            : undefined,
      }
      onConnect(enriched as Connection)
    },
    [onConnect],
  )

  const onDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault()
      const type = event.dataTransfer.getData('application/reactflow')
      if (!type || !['agent', 'task', 'tool'].includes(type)) return

      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })

      const newNode: Node = {
        id: `${type}-${Date.now()}`,
        type,
        position,
        data: getDefaultNodeData(type),
      }

      addNode(newNode)
    },
    [screenToFlowPosition, addNode],
  )

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      setSelectedNode(node.id)
    },
    [setSelectedNode],
  )

  const onPaneClick = useCallback(() => {
    setSelectedNode(null)
  }, [setSelectedNode])

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={handleConnect}
      nodeTypes={NODE_TYPES}
      edgeTypes={EDGE_TYPES}
      onNodeClick={onNodeClick}
      onPaneClick={onPaneClick}
      onDrop={onDrop}
      onDragOver={onDragOver}
      fitView
      fitViewOptions={FIT_VIEW_OPTIONS}
      snapToGrid
      snapGrid={SNAP_GRID}
      deleteKeyCode={DELETE_KEY_CODE}
      proOptions={PRO_OPTIONS}
      className="studio-canvas"
    >
      <Background
        variant={BackgroundVariant.Dots}
        gap={20}
        size={1}
        color={isDark ? '#334155' : '#e2e8f0'}
      />
      <Controls
        className="!overflow-hidden !rounded-lg !border !border-border !shadow-md"
        showInteractive={false}
      />
      <MiniMap
        nodeColor={minimapNodeColor}
        className="!rounded-lg !border !border-border !shadow-md"
        maskColor={isDark ? 'rgba(15, 23, 42, 0.7)' : 'rgba(248, 250, 252, 0.7)'}
        pannable
        zoomable
      />
    </ReactFlow>
  )
}

function EmptyCanvasOverlay({ onLoadExample }: { onLoadExample?: () => void }) {
  return (
    <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
      <div className="pointer-events-auto select-none text-center">
        <div aria-hidden="true" className="mb-5 flex items-center justify-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-100 dark:bg-violet-900">
            <User className="h-5 w-5 text-violet-500 dark:text-violet-400" />
          </div>
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-100 dark:bg-blue-900">
            <ListChecks className="h-5 w-5 text-blue-500 dark:text-blue-400" />
          </div>
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-100 dark:bg-emerald-900">
            <Wrench className="h-5 w-5 text-emerald-500 dark:text-emerald-400" />
          </div>
        </div>

        <p className="mb-1 text-sm font-medium text-foreground">Canvas is empty</p>
        <p className="mb-5 max-w-[260px] text-xs leading-relaxed text-muted-foreground">
          Drag agents and tasks from the palette, then connect them
        </p>

        {onLoadExample && (
          <button
            onClick={onLoadExample}
            className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-xs font-semibold text-foreground shadow-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Sparkles className="h-3.5 w-3.5 text-amber-500" aria-hidden="true" />
            Load example crew
          </button>
        )}
      </div>
    </div>
  )
}

export default function Canvas({ onLoadExample }: { onLoadExample?: () => void }) {
  const isEmpty = useStudioStore((state) => state.nodes.length === 0)

  return (
    <div
      data-tour="canvas"
      className="relative flex-1 overflow-hidden bg-slate-50 dark:bg-slate-900"
    >
      <CanvasInner />
      {isEmpty && <EmptyCanvasOverlay onLoadExample={onLoadExample} />}
    </div>
  )
}
