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

const MAX_HISTORY = 30
const HISTORY_DEBOUNCE_MS = 100
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
}

export const useStudioStore = create<StudioState>()(
  persist(
    (set, get) => {
      let lastHistoryPush = 0

      function pushHistory() {
        const now = Date.now()
        if (now - lastHistoryPush < HISTORY_DEBOUNCE_MS) return
        lastHistoryPush = now

        const { nodes, edges, history, historyIndex } = get()
        const newHistory = history.slice(0, historyIndex + 1)
        newHistory.push(cloneSnapshot(nodes, edges))
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
        crewName: 'my-crew',
        selectedNodeId: null,
        dirty: false,
        history: [],
        historyIndex: -1,
        canUndo: false,
        canRedo: false,
        crewSettings: { onErrorCrew: '', onErrorAction: '' },

        onNodesChange: (changes) => {
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
        setNodes: (nodes) => set({ nodes }),
        setEdges: (edges) => set({ edges }),
        setCrewSettings: (settings) => set({ crewSettings: settings, dirty: true }),
        markClean: () => set({ dirty: false }),

        undo: () => {
          const state = get()
          const { history, historyIndex } = state
          if (historyIndex < 0) return
          let currentHistory = history
          if (historyIndex === history.length - 1) {
            currentHistory = [...history, cloneSnapshot(state.nodes, state.edges)]
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
