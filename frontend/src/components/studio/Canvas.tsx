import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react'
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  ControlButton,
  MiniMap,
  useReactFlow,
  type Node,
  type NodeTypes,
  type EdgeTypes,
  type Connection,
  type Edge,
  type IsValidConnection,
} from '@xyflow/react'
import {
  User,
  ListChecks,
  Wrench,
  Workflow,
  ShieldCheck,
  GitBranch,
  Route,
  Columns3,
  Sparkles,
  Maximize2,
} from 'lucide-react'
import { useShallow } from 'zustand/react/shallow'
import { useStudioStore } from '@/stores/studioStore'
import { DATAFLOW_MARKER_END, getDefaultNodeData } from './defaults'
import AgentNode from './nodes/AgentNode'
import TaskNode from './nodes/TaskNode'
import ToolNode from './nodes/ToolNode'
import FlowStepNode from './nodes/FlowStepNode'
import PIINode from './nodes/PIINode'
import ConditionNode from './nodes/ConditionNode'
import RouterNode from './nodes/RouterNode'
import ParallelNode from './nodes/ParallelNode'
import CrewGroupNode from './nodes/CrewGroupNode'
import StickyNoteNode from './nodes/StickyNoteNode'
import DataFlowEdge from './edges/DataFlowEdge'
import ToolAssignEdge from './edges/ToolAssignEdge'

/* ------------------------------------------------------------------ */
/* Node / Edge type registries — must be stable references             */
/* ------------------------------------------------------------------ */

const NODE_TYPES: NodeTypes = {
  agent: AgentNode,
  task: TaskNode,
  tool: ToolNode,
  flowStep: FlowStepNode,
  pii: PIINode,
  condition: ConditionNode,
  router: RouterNode,
  parallel: ParallelNode,
  crewGroup: CrewGroupNode,
  stickyNote: StickyNoteNode,
}

const DROPPABLE_TYPES = new Set([
  'agent',
  'task',
  'tool',
  'flowStep',
  'pii',
  'condition',
  'router',
  'parallel',
  'stickyNote',
])

const EDGE_TYPES: EdgeTypes = {
  dataflow: DataFlowEdge,
  toolassign: ToolAssignEdge,
}

const FIT_VIEW_OPTIONS = { padding: 0.5, maxZoom: 1 } as const
const SNAP_GRID: [number, number] = [20, 20]
const PRO_OPTIONS = { hideAttribution: true } as const
const DELETE_KEY_CODE = ['Delete', 'Backspace']
const MINIMAP_STYLE = { width: 140, height: 90 } as const
const CONNECTION_LINE_STYLE = { stroke: '#6366f1', strokeWidth: 2 } as const

const VALID_CONNECTIONS = new Set([
  'agent->task',
  'task->task',
  'task->agent',
  'tool->agent',
  'tool->task',
  'flowStep->flowStep',
])

const UNIVERSAL_TARGETS = new Set(['condition', 'router', 'parallel'])

function pickEdgeType(nodes: Node[], connection: Connection): string {
  const sourceNode = connection.source ? nodes.find((n) => n.id === connection.source) : undefined
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
    case 'flowStep':
      return '#f59e0b'
    case 'pii':
      return '#f43f5e'
    case 'condition':
      return '#f59e0b'
    case 'router':
      return '#06b6d4'
    case 'parallel':
      return '#a855f7'
    case 'crewGroup':
      return '#94a3b8'
    case 'stickyNote':
      return '#fbbf24'
    default:
      return '#94a3b8'
  }
}

function CanvasInner() {
  const { screenToFlowPosition, fitView } = useReactFlow()
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
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, addNode, setSelectedNode } =
    useStudioStore(
      useShallow((s) => ({
        nodes: s.nodes,
        edges: s.edges,
        onNodesChange: s.onNodesChange,
        onEdgesChange: s.onEdgesChange,
        onConnect: s.onConnect,
        addNode: s.addNode,
        setSelectedNode: s.setSelectedNode,
      })),
    )
  const nodesRef = useRef(nodes)
  nodesRef.current = nodes

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      const isEditable =
        tag === 'INPUT' || tag === 'TEXTAREA' || (e.target as HTMLElement).isContentEditable

      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) {
        if (isEditable) return
        e.preventDefault()
        useStudioStore.getState().undo()
      }
      if ((e.metaKey || e.ctrlKey) && ((e.key === 'z' && e.shiftKey) || e.key === 'y')) {
        if (isEditable) return
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
      const edgeType = pickEdgeType(nodesRef.current, connection)
      const enriched: Edge = {
        ...connection,
        id: `${connection.source}-${connection.target}-${crypto.randomUUID()}`,
        type: edgeType,
        markerEnd: edgeType === 'dataflow' ? DATAFLOW_MARKER_END : undefined,
      }
      onConnect(enriched as Connection)
    },
    [onConnect],
  )

  const isValidConnection: IsValidConnection = useCallback((connection) => {
    const sourceNode = nodesRef.current.find((n) => n.id === connection.source)
    const targetNode = nodesRef.current.find((n) => n.id === connection.target)
    if (!sourceNode?.type || !targetNode?.type) return false
    if (sourceNode.type === 'stickyNote' || targetNode.type === 'stickyNote') return false
    if (UNIVERSAL_TARGETS.has(targetNode.type)) return true
    return VALID_CONNECTIONS.has(`${sourceNode.type}->${targetNode.type}`)
  }, [])

  const handleFitView = useCallback(() => {
    void fitView(FIT_VIEW_OPTIONS)
  }, [fitView])

  const onDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault()
      const type = event.dataTransfer.getData('application/reactflow')
      if (!type || !DROPPABLE_TYPES.has(type)) return

      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })

      const newNode: Node = {
        id: `${type}-${crypto.randomUUID()}`,
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
      isValidConnection={isValidConnection}
      connectionLineStyle={CONNECTION_LINE_STYLE}
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
      >
        <ControlButton onClick={handleFitView} title="Fit view" aria-label="Fit view">
          <Maximize2 className="h-3.5 w-3.5" />
        </ControlButton>
      </Controls>
      <MiniMap
        nodeColor={minimapNodeColor}
        nodeStrokeWidth={1}
        className="!rounded-lg !border !border-border opacity-70 !shadow-md transition-opacity duration-200 hover:opacity-100"
        maskColor={isDark ? 'rgba(15, 23, 42, 0.85)' : 'rgba(248, 250, 252, 0.85)'}
        style={MINIMAP_STYLE}
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
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-100 dark:bg-amber-900">
            <Workflow className="h-5 w-5 text-amber-500 dark:text-amber-400" />
          </div>
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-rose-100 dark:bg-rose-900">
            <ShieldCheck className="h-5 w-5 text-rose-500 dark:text-rose-400" />
          </div>
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-100 dark:bg-amber-900">
            <GitBranch className="h-5 w-5 text-amber-500 dark:text-amber-400" />
          </div>
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-100 dark:bg-cyan-900">
            <Route className="h-5 w-5 text-cyan-500 dark:text-cyan-400" />
          </div>
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-100 dark:bg-purple-900">
            <Columns3 className="h-5 w-5 text-purple-500 dark:text-purple-400" />
          </div>
        </div>

        <h2 className="mb-1 text-sm font-medium text-foreground">Canvas is empty</h2>
        <p className="mb-5 max-w-[260px] text-xs leading-relaxed text-muted-foreground">
          <span className="hidden sm:inline">
            Drag agents and tasks from the palette, then connect them
          </span>
          <span className="sm:hidden">
            Tap the buttons below to add agents and tasks, then connect them
          </span>
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
      role="region"
      aria-label="Studio canvas — drag agents, tasks, and tools to build a crew"
      tabIndex={-1}
      className="relative flex-1 overflow-hidden bg-slate-50 focus-visible:outline-none dark:bg-slate-900"
    >
      <CanvasInner />
      {isEmpty && <EmptyCanvasOverlay onLoadExample={onLoadExample} />}
    </div>
  )
}
