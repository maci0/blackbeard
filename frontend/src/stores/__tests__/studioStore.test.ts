/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { useStudioStore, MAX_HISTORY } from '../studioStore'
import type { Node, Edge, Connection } from '@xyflow/react'

function makeNode(id: string, overrides: Partial<Node> = {}): Node {
  return {
    id,
    type: 'default',
    position: { x: 0, y: 0 },
    data: { label: id },
    ...overrides,
  }
}

function makeEdge(id: string, source: string, target: string): Edge {
  return { id, source, target }
}

function resetStore() {
  useStudioStore.setState({
    nodes: [],
    edges: [],
    selectedNodeId: null,
    dirty: false,
    history: [],
    historyIndex: -1,
    canUndo: false,
    canRedo: false,
  })
}

describe('studioStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetStore()
  })

  describe('addNode', () => {
    it('adds a node to the canvas', () => {
      const node = makeNode('node-1')
      useStudioStore.getState().addNode(node)

      const state = useStudioStore.getState()
      expect(state.nodes).toHaveLength(1)
      expect(state.nodes[0]!.id).toBe('node-1')
      expect(state.dirty).toBe(true)
    })

    it('appends multiple nodes', () => {
      useStudioStore.getState().addNode(makeNode('node-1'))
      useStudioStore.getState().addNode(makeNode('node-2'))

      expect(useStudioStore.getState().nodes).toHaveLength(2)
    })
  })

  describe('removeNode', () => {
    it('removes a node by id', () => {
      useStudioStore.getState().addNode(makeNode('node-1'))
      useStudioStore.getState().addNode(makeNode('node-2'))

      useStudioStore.getState().removeNode('node-1')

      const state = useStudioStore.getState()
      expect(state.nodes).toHaveLength(1)
      expect(state.nodes[0]!.id).toBe('node-2')
      expect(state.dirty).toBe(true)
    })

    it('removes edges connected to the removed node', () => {
      useStudioStore.setState({
        nodes: [makeNode('a'), makeNode('b'), makeNode('c')],
        edges: [makeEdge('e1', 'a', 'b'), makeEdge('e2', 'b', 'c'), makeEdge('e3', 'a', 'c')],
      })

      useStudioStore.getState().removeNode('b')

      const state = useStudioStore.getState()
      expect(state.nodes).toHaveLength(2)
      // Only edge e3 (a->c) should remain — e1 and e2 involve node b
      expect(state.edges).toHaveLength(1)
      expect(state.edges[0]!.id).toBe('e3')
    })

    it('clears selectedNodeId if the selected node is removed', () => {
      useStudioStore.setState({
        nodes: [makeNode('a'), makeNode('b')],
        selectedNodeId: 'a',
      })

      useStudioStore.getState().removeNode('a')

      expect(useStudioStore.getState().selectedNodeId).toBeNull()
    })

    it('preserves selectedNodeId if a different node is removed', () => {
      useStudioStore.setState({
        nodes: [makeNode('a'), makeNode('b')],
        selectedNodeId: 'a',
      })

      useStudioStore.getState().removeNode('b')

      expect(useStudioStore.getState().selectedNodeId).toBe('a')
    })
  })

  describe('onConnect', () => {
    it('creates an edge from a connection', () => {
      useStudioStore.setState({
        nodes: [makeNode('a'), makeNode('b')],
        edges: [],
      })

      const connection: Connection = {
        source: 'a',
        target: 'b',
        sourceHandle: null,
        targetHandle: null,
      }
      useStudioStore.getState().onConnect(connection)

      const state = useStudioStore.getState()
      expect(state.edges).toHaveLength(1)
      expect(state.edges[0]!.source).toBe('a')
      expect(state.edges[0]!.target).toBe('b')
      expect(state.dirty).toBe(true)
    })
  })

  describe('undo / redo', () => {
    beforeEach(() => {
      vi.useFakeTimers()
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it('undo restores previous state', () => {
      const node1 = makeNode('node-1')
      useStudioStore.getState().addNode(node1)
      expect(useStudioStore.getState().nodes).toHaveLength(1)

      vi.advanceTimersByTime(200)

      const node2 = makeNode('node-2')
      useStudioStore.getState().addNode(node2)
      expect(useStudioStore.getState().nodes).toHaveLength(2)

      useStudioStore.getState().undo()

      // After undo, should go back to 1-node state
      const state = useStudioStore.getState()
      expect(state.nodes).toHaveLength(1)
      expect(state.nodes[0]!.id).toBe('node-1')
      expect(state.dirty).toBe(true)
    })

    it('redo restores undone state', () => {
      vi.advanceTimersByTime(200)

      useStudioStore.getState().addNode(makeNode('node-1'))
      vi.advanceTimersByTime(200)
      useStudioStore.getState().addNode(makeNode('node-2'))
      vi.advanceTimersByTime(200)

      expect(useStudioStore.getState().nodes).toHaveLength(2)

      // Undo: history records snapshot before each addNode.
      // First undo saves live state as the redo target, then restores the
      // snapshot taken before addNode('node-2').
      useStudioStore.getState().undo()
      expect(useStudioStore.getState().nodes).toHaveLength(1)
      expect(useStudioStore.getState().nodes[0]!.id).toBe('node-1')
      expect(useStudioStore.getState().canRedo).toBe(true)

      // Redo: steps forward through history, restoring the saved live state.
      useStudioStore.getState().redo()
      expect(useStudioStore.getState().nodes).toHaveLength(2)
      const ids = useStudioStore
        .getState()
        .nodes.map((n) => n.id)
        .sort()
      expect(ids).toEqual(['node-1', 'node-2'])
    })

    it('undo is a no-op when there is no history', () => {
      useStudioStore.getState().undo()

      const state = useStudioStore.getState()
      expect(state.nodes).toHaveLength(0)
      expect(state.historyIndex).toBe(-1)
    })

    it('undo after redo steps back instead of re-appending the live state', () => {
      useStudioStore.getState().addNode(makeNode('node-1'))
      vi.advanceTimersByTime(200)
      useStudioStore.getState().addNode(makeNode('node-2'))
      vi.advanceTimersByTime(200)

      useStudioStore.getState().undo()
      useStudioStore.getState().redo()
      expect(useStudioStore.getState().nodes).toHaveLength(2)

      // This undo must go back to 1 node, not sit on the live snapshot.
      useStudioStore.getState().undo()
      expect(useStudioStore.getState().nodes).toHaveLength(1)
      expect(useStudioStore.getState().nodes[0]!.id).toBe('node-1')
    })

    it('redo is a no-op when there is nothing to redo', () => {
      useStudioStore.getState().addNode(makeNode('node-1'))
      vi.advanceTimersByTime(200)

      useStudioStore.getState().redo()

      // Should still have 1 node — redo did nothing
      expect(useStudioStore.getState().nodes).toHaveLength(1)
    })
  })

  describe('setNodes / setEdges', () => {
    it('setNodes updates nodes', () => {
      const nodes = [makeNode('x'), makeNode('y')]
      useStudioStore.getState().setNodes(nodes)

      expect(useStudioStore.getState().nodes).toEqual(nodes)
    })

    it('setEdges updates edges', () => {
      const edges = [makeEdge('e1', 'x', 'y')]
      useStudioStore.getState().setEdges(edges)

      expect(useStudioStore.getState().edges).toEqual(edges)
    })
  })

  describe('markClean', () => {
    it('clears the dirty flag', () => {
      useStudioStore.getState().addNode(makeNode('node-1'))
      expect(useStudioStore.getState().dirty).toBe(true)

      useStudioStore.getState().markClean()
      expect(useStudioStore.getState().dirty).toBe(false)
    })
  })

  describe('history limits', () => {
    it('limits history to MAX_HISTORY entries', () => {
      vi.useFakeTimers()

      // Push more than MAX_HISTORY entries — each addNode pushes one
      for (let i = 0; i < MAX_HISTORY + 5; i++) {
        useStudioStore.getState().addNode(makeNode(`node-${i}`))
        vi.advanceTimersByTime(200)
      }

      const state = useStudioStore.getState()
      expect(state.history.length).toBe(MAX_HISTORY)

      vi.useRealTimers()
    })
  })

  describe('updateNodeData', () => {
    it('updates data for an existing node', () => {
      vi.useFakeTimers()

      useStudioStore.setState({
        nodes: [makeNode('node-1', { data: { label: 'Original' } })],
      })

      vi.advanceTimersByTime(600)
      useStudioStore.getState().updateNodeData('node-1', { label: 'Updated' })

      const state = useStudioStore.getState()
      expect(state.nodes[0]!.data).toEqual({ label: 'Updated' })
      expect(state.dirty).toBe(true)

      vi.useRealTimers()
    })

    it('is a no-op for non-existent node id', () => {
      useStudioStore.setState({
        nodes: [makeNode('node-1')],
      })

      useStudioStore.getState().updateNodeData('non-existent', { label: 'Nothing' })

      expect(useStudioStore.getState().nodes).toHaveLength(1)
      expect(useStudioStore.getState().nodes[0]!.id).toBe('node-1')
    })
  })

  describe('setSelectedNode', () => {
    it('sets the selected node id', () => {
      useStudioStore.getState().setSelectedNode('node-1')
      expect(useStudioStore.getState().selectedNodeId).toBe('node-1')
    })

    it('clears the selected node id', () => {
      useStudioStore.getState().setSelectedNode('node-1')
      useStudioStore.getState().setSelectedNode(null)
      expect(useStudioStore.getState().selectedNodeId).toBeNull()
    })
  })
})
