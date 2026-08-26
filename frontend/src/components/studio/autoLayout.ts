import type { ELK, ElkNode, ElkExtendedEdge } from 'elkjs/lib/elk.bundled.js'
import type { Node, Edge } from '@xyflow/react'

let elk: ELK | null = null

async function getElk(): Promise<ELK> {
  if (elk) return elk
  const { default: ELK } = await import('elkjs/lib/elk.bundled.js')
  elk = new ELK()
  return elk
}

const NODE_WIDTH = 160
const NODE_HEIGHT = 120
const GROUP_PADDING = { top: 40, right: 20, bottom: 20, left: 20 }

export async function autoLayout(
  nodes: Node[],
  edges: Edge[],
): Promise<{ nodes: Node[]; edges: Edge[] }> {
  if (nodes.length === 0) return { nodes, edges }

  // Lay out only leaf nodes via ELK (flat), then rebuild group bounds manually
  const groupNodes = nodes.filter((n) => n.type === 'crewGroup')
  const leafNodes = nodes.filter((n) => n.type !== 'crewGroup')

  if (leafNodes.length === 0) return { nodes, edges }

  // For leaf nodes that have a parentId, we need to temporarily treat them
  // as top-level for ELK layout, then re-parent them afterwards
  const elkNodes: ElkNode[] = leafNodes.map((n) => ({
    id: n.id,
    width: (n.measured?.width ?? n.width) || NODE_WIDTH,
    height: (n.measured?.height ?? n.height) || NODE_HEIGHT,
  }))

  // Only include edges where both source and target are leaf nodes
  const leafIds = new Set(leafNodes.map((n) => n.id))
  const elkEdges: ElkExtendedEdge[] = edges
    .filter((e) => leafIds.has(e.source) && leafIds.has(e.target))
    .map((e) => ({
      id: e.id,
      sources: [e.source],
      targets: [e.target],
    }))

  const elkInstance = await getElk()
  const graph = await elkInstance.layout({
    id: 'root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': 'RIGHT',
      'elk.spacing.nodeNode': '80',
      'elk.layered.spacing.nodeNodeBetweenLayers': '120',
      'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
      'elk.edgeRouting': 'SPLINES',
    },
    children: elkNodes,
    edges: elkEdges,
  })

  const positionMap = new Map<string, { x: number; y: number }>()
  for (const child of graph.children ?? []) {
    positionMap.set(child.id, { x: child.x ?? 0, y: child.y ?? 0 })
  }

  // Apply positions to leaf nodes (stripping parentId for now: we rebuild below)
  const layoutedLeaves = leafNodes.map((n) => {
    const pos = positionMap.get(n.id)
    // eslint-disable-next-line @typescript-eslint/no-unused-vars -- omit-only destructure: parentId/extent are stripped, not consumed
    const { parentId: _p, extent: _e, ...rest } = n
    return pos ? { ...rest, position: pos } : { ...rest }
  })

  if (groupNodes.length === 0) {
    return { nodes: layoutedLeaves, edges }
  }

  // Rebuild group node bounds and re-parent children
  const result: Node[] = []

  for (const group of groupNodes) {
    const childIds = new Set(nodes.filter((n) => n.parentId === group.id).map((n) => n.id))
    const childLeaves = layoutedLeaves.filter((n) => childIds.has(n.id))

    if (childLeaves.length === 0) {
      // Group with no children: keep as-is
      result.push(group)
      continue
    }

    // Calculate bounding box of children
    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity

    for (const n of childLeaves) {
      minX = Math.min(minX, n.position.x)
      minY = Math.min(minY, n.position.y)
      maxX = Math.max(maxX, n.position.x + NODE_WIDTH)
      maxY = Math.max(maxY, n.position.y + NODE_HEIGHT)
    }

    const groupX = minX - GROUP_PADDING.left
    const groupY = minY - GROUP_PADDING.top

    const updatedGroup: Node = {
      ...group,
      position: { x: groupX, y: groupY },
      style: {
        width: maxX - minX + GROUP_PADDING.left + GROUP_PADDING.right,
        height: maxY - minY + GROUP_PADDING.top + GROUP_PADDING.bottom,
      },
      zIndex: -1,
    }
    result.push(updatedGroup)

    // Re-parent child nodes with positions relative to the group
    for (const child of childLeaves) {
      result.push({
        ...child,
        parentId: group.id,
        extent: 'parent' as const,
        position: {
          x: child.position.x - groupX,
          y: child.position.y - groupY,
        },
      })
    }
  }

  // Add any leaf nodes not in a group
  const parentedIds = new Set(result.map((n) => n.id))
  for (const leaf of layoutedLeaves) {
    if (!parentedIds.has(leaf.id)) {
      result.push(leaf)
    }
  }

  return { nodes: result, edges }
}
