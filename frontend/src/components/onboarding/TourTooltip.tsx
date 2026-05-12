import type { CSSProperties } from 'react'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'

/* ------------------------------------------------------------------ */
/* Positioning logic                                                   */
/* ------------------------------------------------------------------ */

const TOOLTIP_WIDTH = 320
const TOOLTIP_GAP = 14
const APPROX_HEIGHT = 210 // estimated tooltip height in px

type Placement = 'below' | 'above' | 'center'

interface PositionResult {
  style: CSSProperties
  placement: Placement
}

function computePosition(targetRect: DOMRect | null): PositionResult {
  if (!targetRect) {
    return {
      style: {
        position: 'fixed',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        width: TOOLTIP_WIDTH,
        zIndex: 9999,
      },
      placement: 'center',
    }
  }

  const vw = window.innerWidth
  const vh = window.innerHeight

  // Horizontal: center on target, clamped within viewport margins
  let left = targetRect.left + targetRect.width / 2 - TOOLTIP_WIDTH / 2
  left = Math.max(12, Math.min(left, vw - TOOLTIP_WIDTH - 12))

  // Vertical: prefer below; fall back to above if not enough room
  let top: number
  let placement: Placement

  if (targetRect.bottom + TOOLTIP_GAP + APPROX_HEIGHT <= vh) {
    top = targetRect.bottom + TOOLTIP_GAP
    placement = 'below'
  } else {
    top = targetRect.top - TOOLTIP_GAP - APPROX_HEIGHT
    placement = 'above'
  }

  // Clamp top to stay inside viewport
  top = Math.max(8, Math.min(top, vh - APPROX_HEIGHT - 8))

  return {
    style: {
      position: 'fixed',
      top,
      left,
      width: TOOLTIP_WIDTH,
      zIndex: 9999,
    },
    placement,
  }
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export interface TourTooltipProps {
  title: string
  description: string
  step: number
  totalSteps: number
  onNext: () => void
  onBack: () => void
  onSkip: () => void
  targetRect: DOMRect | null
}

export function TourTooltip({
  title,
  description,
  step,
  totalSteps,
  onNext,
  onBack,
  onSkip,
  targetRect,
}: TourTooltipProps) {
  const isFirst = step === 0
  const isLast = step === totalSteps - 1
  const progress = ((step + 1) / totalSteps) * 100

  const { style, placement } = computePosition(targetRect)

  return (
    <div
      style={style}
      // Stop clicks from bubbling to the backdrop click-capture layer
      onClick={(e) => e.stopPropagation()}
    >
      {/* Announce step changes to screen readers */}
      <span className="sr-only" aria-live="polite" aria-atomic="true">
        Step {step + 1} of {totalSteps}: {title}. {description}
      </span>
      {/* Up-arrow when tooltip is below its target */}
      {placement === 'below' && targetRect && (
        <div
          aria-hidden="true"
          className="absolute -top-1.5 w-3 h-3 bg-card border-l border-t border-border rotate-45"
          style={{ left: 24 }}
        />
      )}

      <div className="bg-card border border-border rounded-xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-start justify-between gap-2 px-4 pt-4 pb-2">
          <div className="min-w-0">
            <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
              {step + 1} of {totalSteps}
            </p>
            <h3 className="text-sm font-bold text-foreground mt-0.5 leading-snug">{title}</h3>
          </div>
          <button
            onClick={onSkip}
            aria-label="Skip tour"
            className="shrink-0 p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Progress bar */}
        <div className="px-4 mb-3">
          <div className="h-0.5 w-full bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-300 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Description */}
        <p className="px-4 pb-4 text-[13px] text-muted-foreground leading-relaxed">
          {description}
        </p>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-border bg-muted/20">
          <button
            onClick={onSkip}
            className="text-[11px] text-muted-foreground hover:text-foreground transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none rounded"
          >
            Skip tour
          </button>

          <div className="flex items-center gap-2">
            {!isFirst && (
              <button
                onClick={onBack}
                className="flex items-center gap-1 px-3 py-1.5 text-[12px] font-medium border border-border rounded-lg text-foreground bg-background hover:bg-muted transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
                Back
              </button>
            )}
            <button
              onClick={onNext}
              className="flex items-center gap-1 px-3 py-1.5 text-[12px] font-semibold bg-primary text-primary-foreground rounded-lg hover:opacity-90 transition-opacity focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              {isLast ? 'Finish' : 'Next'}
              {!isLast && <ChevronRight className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Down-arrow when tooltip is above its target */}
      {placement === 'above' && targetRect && (
        <div
          aria-hidden="true"
          className="absolute -bottom-1.5 w-3 h-3 bg-card border-r border-b border-border rotate-45"
          style={{ left: 24 }}
        />
      )}
    </div>
  )
}
