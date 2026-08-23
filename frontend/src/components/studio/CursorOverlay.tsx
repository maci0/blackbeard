/**
 * Renders colored cursor indicators for remote collaborators on the Studio canvas.
 *
 * Each cursor appears as an arrow SVG with a name label. Positions animate
 * smoothly using CSS transitions for a fluid experience. The overlay is
 * pointer-events-none so it never interferes with canvas interaction.
 */

import type { RemoteCursor } from '@/hooks/useCollaboration'

export function CursorOverlay({ cursors }: { cursors: RemoteCursor[] }) {
  if (cursors.length === 0) return null

  return (
    <div className="pointer-events-none absolute inset-0 z-50 overflow-hidden" aria-hidden="true">
      {cursors.map((cursor) => (
        <div
          key={cursor.userId}
          className="absolute transition-all duration-100 ease-out"
          style={{
            left: cursor.x,
            top: cursor.y,
            willChange: 'transform',
          }}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 16 16"
            fill={cursor.color}
            className="drop-shadow-sm"
          >
            <path d="M0 0 L0 14 L4 10 L8 16 L10 15 L6 9 L12 9 Z" />
          </svg>
          <span
            className="-mt-1 ml-4 inline-block max-w-[120px] truncate whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-medium leading-tight text-white shadow-sm"
            style={{ backgroundColor: cursor.color }}
          >
            {cursor.name}
          </span>
        </div>
      ))}
    </div>
  )
}
