import { useCallback, useEffect, useMemo, type DragEvent } from 'react'
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
import '@xyflow/react/dist/style.css'
import { User, ListChecks, Wrench, Sparkles } from 'lucide-react'
import { useStudioStore } from '@/stores/studioStore'
import { getDefaultNodeData } from '@/lib/utils'

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

/* ------------------------------------------------------------------ */
/* Edge type selector based on connected node types                    */
/* ------------------------------------------------------------------ */

function pickEdgeType(nodes: Node[], connection: Connection): string {
  const sourceNode = nodes.find((n) => n.id === connection.source)
  if (sourceNode?.type === 'tool') return 'toolassign'
  return 'dataflow'
}

/* ------------------------------------------------------------------ */
/* MiniMap node colors                                                 */
/* ------------------------------------------------------------------ */

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

/* ------------------------------------------------------------------ */
/* Inner canvas that uses useReactFlow (must be child of Provider)     */
/* ------------------------------------------------------------------ */

function CanvasInner() {
  const { screenToFlowPosition } = useReactFlow()
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, addNode, setSelectedNode } =
    useStudioStore()

  /* ── Undo / Redo keyboard shortcuts ── */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault()
        useStudioStore.getState().undo()
      }
      if (
        (e.metaKey || e.ctrlKey) &&
        ((e.key === 'z' && e.shiftKey) || e.key === 'y')
      ) {
        e.preventDefault()
        useStudioStore.getState().redo()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  /** Derive an edge type from the connected nodes and attach arrow marker */
  const handleConnect = useCallback(
    (connection: Connection) => {
      const edgeType = pickEdgeType(nodes, connection)
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
    [nodes, onConnect],
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

  // Keep edge types stable
  const edgeTypes = useMemo(() => EDGE_TYPES, [])
  const nodeTypes = useMemo(() => NODE_TYPES, [])

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={handleConnect}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodeClick={onNodeClick}
      onPaneClick={onPaneClick}
      onDrop={onDrop}
      onDragOver={onDragOver}
      fitView
      fitViewOptions={{ padding: 0.2 }}
      deleteKeyCode={['Delete', 'Backspace']}
      proOptions={{ hideAttribution: true }}
      className="studio-canvas"
    >
      <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e2e8f0" />
      <Controls
        className="!border !border-border !rounded-lg !shadow-md !overflow-hidden"
        showInteractive={false}
      />
      <MiniMap
        nodeColor={minimapNodeColor}
        className="!border !border-border !rounded-lg !shadow-md"
        maskColor="rgba(248, 250, 252, 0.7)"
        pannable
        zoomable
      />
    </ReactFlow>
  )
}

/* ------------------------------------------------------------------ */
/* Empty canvas guidance overlay                                       */
/* ------------------------------------------------------------------ */

function EmptyCanvasOverlay({ onLoadExample }: { onLoadExample?: () => void }) {
  return (
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
      <div className="text-center pointer-events-auto select-none">
        {/* Icon cluster */}
        <div className="flex items-center justify-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-xl bg-violet-100 flex items-center justify-center">
            <User className="w-5 h-5 text-violet-500" />
          </div>
          <div className="w-10 h-10 rounded-xl bg-blue-100 flex items-center justify-center">
            <ListChecks className="w-5 h-5 text-blue-500" />
          </div>
          <div className="w-10 h-10 rounded-xl bg-emerald-100 flex items-center justify-center">
            <Wrench className="w-5 h-5 text-emerald-500" />
          </div>
        </div>

        <p className="text-sm font-medium text-foreground mb-1">Canvas is empty</p>
        <p className="text-[12px] text-muted-foreground mb-5 max-w-[260px] leading-relaxed">
          Drag agents and tasks from the palette, then connect them
        </p>

        {onLoadExample && (
          <button
            onClick={onLoadExample}
            className="inline-flex items-center gap-2 px-4 py-2 text-[12px] font-semibold bg-card border border-border rounded-lg text-foreground hover:bg-muted shadow-sm transition-colors"
          >
            <Sparkles className="w-3.5 h-3.5 text-amber-500" />
            Load example crew
          </button>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Exported Canvas — thin wrapper so CanvasInner is always a child     */
/* ------------------------------------------------------------------ */

export default function Canvas({ onLoadExample }: { onLoadExample?: () => void }) {
  const { nodes } = useStudioStore()

  return (
    <div data-tour="canvas" className="flex-1 relative overflow-hidden bg-slate-50">
      <CanvasInner />
      {nodes.length === 0 && <EmptyCanvasOverlay onLoadExample={onLoadExample} />}
    </div>
  )
}
