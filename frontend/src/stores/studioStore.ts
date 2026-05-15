import { create } from 'zustand'
import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from '@xyflow/react'

const MAX_HISTORY = 30

interface HistorySnapshot {
  nodes: Node[]
  edges: Edge[]
}

interface StudioState {
  nodes: Node[]
  edges: Edge[]
  selectedNodeId: string | null
  dirty: boolean
  history: HistorySnapshot[]
  historyIndex: number
  canUndo: boolean
  canRedo: boolean

  onNodesChange: (changes: NodeChange[]) => void
  onEdgesChange: (changes: EdgeChange[]) => void
  onConnect: (connection: Connection) => void
  addNode: (node: Node) => void
  removeNode: (id: string) => void
  updateNodeData: (id: string, data: Record<string, unknown>) => void
  setSelectedNode: (id: string | null) => void
  setNodes: (nodes: Node[]) => void
  setEdges: (edges: Edge[]) => void
  markClean: () => void
  undo: () => void
  redo: () => void
}

export const useStudioStore = create<StudioState>()((set, get) => {
  let lastHistoryPush = 0

  function pushHistory() {
    const now = Date.now()
    if (now - lastHistoryPush < 100) return
    lastHistoryPush = now

    const { nodes, edges, history, historyIndex } = get()
    const newHistory = history.slice(0, historyIndex + 1)
    newHistory.push({ nodes: structuredClone(nodes), edges: structuredClone(edges) })
    if (newHistory.length > MAX_HISTORY) newHistory.shift()
    const newIndex = newHistory.length - 1
    set({
      history: newHistory,
      historyIndex: newIndex,
      canUndo: newIndex >= 1,
      canRedo: false,
    })
  }

  return {
    nodes: [],
    edges: [],
    selectedNodeId: null,
    dirty: false,
    history: [],
    historyIndex: -1,
    canUndo: false,
    canRedo: false,

    onNodesChange: (changes) => {
      // Only push history for structural changes or when a drag operation ends,
      // not for every intermediate position update during a drag.
      const hasStructuralChange = changes.some(
        (c) =>
          c.type === 'remove' ||
          c.type === 'add' ||
          c.type === 'replace' ||
          (c.type === 'position' && c.dragging === false),
      )
      if (hasStructuralChange) pushHistory()
      set((state) => ({ nodes: applyNodeChanges(changes, state.nodes), dirty: true }))
    },

    onEdgesChange: (changes) => {
      const hasStructuralChange = changes.some(
        (c) => c.type === 'remove' || c.type === 'add' || c.type === 'replace',
      )
      if (hasStructuralChange) pushHistory()
      set((state) => ({ edges: applyEdgeChanges(changes, state.edges), dirty: true }))
    },

    onConnect: (connection) => {
      pushHistory()
      set((state) => ({ edges: addEdge(connection, state.edges), dirty: true }))
    },

    addNode: (node) => {
      pushHistory()
      set((state) => ({ nodes: [...state.nodes, node], dirty: true }))
    },

    removeNode: (id) => {
      pushHistory()
      set((state) => {
        const nodes = state.nodes.filter((n) => n.id !== id)
        const edges = state.edges.some((e) => e.source === id || e.target === id)
          ? state.edges.filter((e) => e.source !== id && e.target !== id)
          : state.edges
        return {
          nodes,
          edges,
          selectedNodeId: state.selectedNodeId === id ? null : state.selectedNodeId,
          dirty: true,
        }
      })
    },

    updateNodeData: (id, data) => {
      const now = Date.now()
      if (now - lastHistoryPush > 500) {
        pushHistory()
        lastHistoryPush = now
      }
      set((state) => {
        const idx = state.nodes.findIndex((n) => n.id === id)
        if (idx === -1) return state
        const node = state.nodes[idx]!
        const updated = { ...node, data: { ...node.data, ...data } }
        const nodes = state.nodes.slice()
        nodes[idx] = updated
        return { nodes, dirty: true }
      })
    },

    setSelectedNode: (id) => set({ selectedNodeId: id }),
    setNodes: (nodes) => set({ nodes }),
    setEdges: (edges) => set({ edges }),
    markClean: () => set({ dirty: false }),

    undo: () => {
      const state = get()
      const { history, historyIndex } = state
      if (historyIndex < 0) return
      // Save the live canvas state at the tip so redo can restore it
      let currentHistory = history
      if (historyIndex === history.length - 1) {
        currentHistory = [
          ...history,
          { nodes: structuredClone(state.nodes), edges: structuredClone(state.edges) },
        ]
        if (currentHistory.length > MAX_HISTORY + 1) currentHistory.shift()
      }
      const prev = currentHistory[historyIndex]
      if (prev) {
        const newIndex = historyIndex - 1
        set({
          history: currentHistory,
          nodes: prev.nodes,
          edges: prev.edges,
          historyIndex: newIndex,
          dirty: true,
          canUndo: newIndex >= 0,
          canRedo: currentHistory[newIndex + 1] !== undefined,
        })
      }
    },

    redo: () => {
      const { history, historyIndex } = get()
      const next = history[historyIndex + 1]
      if (next) {
        const newIndex = historyIndex + 1
        set({
          nodes: next.nodes,
          edges: next.edges,
          historyIndex: newIndex,
          dirty: true,
          canUndo: newIndex >= 0,
          canRedo: history[newIndex + 1] !== undefined,
        })
      }
    },
  }
})
