import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
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

export const MAX_HISTORY = 30
const NODE_DATA_DEBOUNCE_MS = 500

function cloneSnapshot(nodes: Node[], edges: Edge[]): HistorySnapshot {
  return structuredClone({ nodes, edges })
}

interface HistorySnapshot {
  nodes: Node[]
  edges: Edge[]
}

export interface CrewSettings {
  onErrorCrew: string
  onErrorAction: string
}

interface NavStackEntry {
  nodes: Node[]
  edges: Edge[]
  crewName: string
}

interface StudioState {
  nodes: Node[]
  edges: Edge[]
  crewName: string
  selectedNodeId: string | null
  dirty: boolean
  history: HistorySnapshot[]
  historyIndex: number
  canUndo: boolean
  canRedo: boolean
  crewSettings: CrewSettings
  navStack: NavStackEntry[]

  onNodesChange: (changes: NodeChange[]) => void
  onEdgesChange: (changes: EdgeChange[]) => void
  onConnect: (connection: Connection) => void
  addNode: (node: Node) => void
  removeNode: (id: string) => void
  updateNodeData: (id: string, data: Record<string, unknown>) => void
  setSelectedNode: (id: string | null) => void
  setCrewName: (name: string) => void
  setNodes: (nodes: Node[]) => void
  setEdges: (edges: Edge[]) => void
  setCrewSettings: (settings: CrewSettings) => void
  markClean: () => void
  undo: () => void
  redo: () => void
  pushNav: (crewName: string, nodes: Node[], edges: Edge[]) => void
  popNav: () => NavStackEntry | null
}

export const useStudioStore = create<StudioState>()(
  persist(
    (set, get) => {
      let lastHistoryPush = 0
      // True while the live canvas has diverged from every history snapshot.
      // Only then does undo need to capture the live state as a redo target;
      // stepping back from a restored snapshot (post-redo) must not append.
      let liveDirty = false

      function pushHistory() {
        const { nodes, edges, history, historyIndex } = get()
        const newHistory = history.slice(0, historyIndex + 1)
        newHistory.push(cloneSnapshot(nodes, edges))
        if (newHistory.length > MAX_HISTORY) newHistory.shift()
        const newIndex = newHistory.length - 1
        set({
          history: newHistory,
          historyIndex: newIndex,
          canUndo: true,
          canRedo: false,
        })
      }

      return {
        nodes: [],
        edges: [],
        crewName: 'my-crew',
        selectedNodeId: null,
        dirty: false,
        history: [],
        historyIndex: -1,
        canUndo: false,
        canRedo: false,
        crewSettings: { onErrorCrew: '', onErrorAction: '' },
        navStack: [],

        onNodesChange: (changes) => {
          const hasStructuralChange = changes.some(
            (c) =>
              c.type === 'remove' ||
              c.type === 'add' ||
              c.type === 'replace' ||
              (c.type === 'position' && c.dragging === false),
          )
          if (hasStructuralChange) pushHistory()
          liveDirty = true
          set((state) => ({
            nodes: applyNodeChanges(changes, state.nodes),
            dirty: hasStructuralChange,
          }))
        },

        onEdgesChange: (changes) => {
          const hasStructuralChange = changes.some(
            (c) => c.type === 'remove' || c.type === 'add' || c.type === 'replace',
          )
          if (hasStructuralChange) pushHistory()
          liveDirty = true
          set((state) => ({
            edges: applyEdgeChanges(changes, state.edges),
            dirty: hasStructuralChange,
          }))
        },

        onConnect: (connection) => {
          pushHistory()
          liveDirty = true
          set((state) => ({ edges: addEdge(connection, state.edges), dirty: true }))
        },

        addNode: (node) => {
          pushHistory()
          liveDirty = true
          set((state) => ({ nodes: [...state.nodes, node], dirty: true }))
        },

        removeNode: (id) => {
          pushHistory()
          liveDirty = true
          set((state) => {
            const nodes = state.nodes.filter((n) => n.id !== id)
            const filteredEdges = state.edges.filter((e) => e.source !== id && e.target !== id)
            return {
              nodes,
              edges: filteredEdges.length === state.edges.length ? state.edges : filteredEdges,
              selectedNodeId: state.selectedNodeId === id ? null : state.selectedNodeId,
              dirty: true,
            }
          })
        },

        updateNodeData: (id, data) => {
          const now = Date.now()
          if (now - lastHistoryPush > NODE_DATA_DEBOUNCE_MS) {
            pushHistory()
            lastHistoryPush = now
          }
          liveDirty = true
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
        setCrewName: (name) => set({ crewName: name }),
        setNodes: (nodes) => {
          liveDirty = true
          set({ nodes })
        },
        setEdges: (edges) => {
          liveDirty = true
          set({ edges })
        },
        setCrewSettings: (settings) => set({ crewSettings: settings, dirty: true }),
        markClean: () => set({ dirty: false }),

        pushNav: (crewName, nodes, edges) => {
          const state = get()
          liveDirty = false
          set({
            navStack: [
              ...state.navStack,
              { nodes: state.nodes, edges: state.edges, crewName: state.crewName },
            ],
            nodes,
            edges,
            crewName,
            selectedNodeId: null,
            dirty: false,
            history: [],
            historyIndex: -1,
            canUndo: false,
            canRedo: false,
          })
        },

        popNav: () => {
          const state = get()
          if (state.navStack.length === 0) return null
          const stack = [...state.navStack]
          const entry = stack.pop()!
          liveDirty = false
          set({
            navStack: stack,
            nodes: entry.nodes,
            edges: entry.edges,
            crewName: entry.crewName,
            selectedNodeId: null,
            dirty: false,
            history: [],
            historyIndex: -1,
            canUndo: false,
            canRedo: false,
          })
          return entry
        },

        undo: () => {
          const state = get()
          const { history, historyIndex } = state
          if (historyIndex < 0 || history.length === 0) return
          const atTip = historyIndex === history.length - 1
          let currentHistory = history
          let restoreIndex = historyIndex - 1
          if (atTip && liveDirty) {
            // The live state is not yet captured; record it as the redo
            // target and step back to the last pushed snapshot.
            currentHistory = [...history, cloneSnapshot(state.nodes, state.edges)]
            if (currentHistory.length > MAX_HISTORY) currentHistory.shift()
            restoreIndex = currentHistory.length - 2
          } else if (restoreIndex < 0) {
            return
          }
          const prev = currentHistory[restoreIndex]
          if (!prev) return
          liveDirty = false
          set({
            history: currentHistory,
            nodes: prev.nodes,
            edges: prev.edges,
            historyIndex: restoreIndex,
            dirty: true,
            canUndo: restoreIndex >= 1,
            canRedo: currentHistory[restoreIndex + 1] !== undefined,
          })
        },

        redo: () => {
          const { history, historyIndex } = get()
          const next = history[historyIndex + 1]
          if (!next) return
          const newIndex = historyIndex + 1
          liveDirty = false
          set({
            nodes: next.nodes,
            edges: next.edges,
            historyIndex: newIndex,
            dirty: true,
            canUndo: true,
            canRedo: history[newIndex + 1] !== undefined,
          })
        },
      }
    },
    {
      name: 'blackbeard_studio_state',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        nodes: state.nodes,
        edges: state.edges,
        crewName: state.crewName,
        crewSettings: state.crewSettings,
      }),
    },
  ),
)
