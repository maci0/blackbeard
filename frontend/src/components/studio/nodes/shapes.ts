/** Shared clip-path / class shapes for studio nodes and palette cards. */

export const CLIP_PATHS = {
  diamondTop: 'polygon(12px 0%, calc(100% - 12px) 0%, 100% 12px, 100% 100%, 0% 100%, 0% 12px)',
  diamondTopSm: 'polygon(6px 0%, calc(100% - 6px) 0%, 100% 6px, 100% 100%, 0% 100%, 0% 6px)',
  hexagonal: 'polygon(8% 0%, 92% 0%, 100% 50%, 92% 100%, 8% 100%, 0% 50%)',
  shield: 'polygon(0% 0%, 100% 0%, 100% 75%, 50% 100%, 0% 75%)',
  shieldSm: 'polygon(0% 0%, 100% 0%, 100% 80%, 50% 100%, 0% 80%)',
} as const

export type NodeShape =
  | 'rectangle'
  | 'chamfered'
  | 'diamond-top'
  | 'hexagonal'
  | 'pill'
  | 'shield'
  | 'loop'

export const SHAPE_CLASSES: Record<NodeShape, string> = {
  rectangle: 'rounded-lg',
  chamfered: 'rounded-[0px_14px_14px_0px]',
  'diamond-top': '',
  hexagonal: '',
  pill: 'rounded-3xl',
  shield: '',
  loop: 'rounded-2xl',
}

export const SHAPE_CLIP_PATHS: Partial<Record<NodeShape, string>> = {
  'diamond-top': CLIP_PATHS.diamondTop,
  hexagonal: CLIP_PATHS.hexagonal,
  shield: CLIP_PATHS.shield,
}

export const SHAPE_BODY_CLASSES: Partial<Record<NodeShape, string>> = {
  hexagonal: 'px-4',
  shield: 'pb-6',
}
