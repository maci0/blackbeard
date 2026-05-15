import { useEffect, useRef, type CSSProperties } from 'react'
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
  const tooltipRef = useRef<HTMLDivElement>(null)

  // Move focus into the tooltip whenever step changes
  useEffect(() => {
    // Small delay to let the DOM settle after position computation
    const timer = setTimeout(() => {
      tooltipRef.current?.focus()
    }, 100)
    return () => clearTimeout(timer)
  }, [step])

  // Trap focus within the tooltip while the tour is active
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return
      const container = tooltipRef.current
      if (!container) return

      const focusable = container.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      )
      if (focusable.length === 0) return

      const first = focusable[0]!
      const last = focusable[focusable.length - 1]!

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault()
          last.focus()
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  return (
    <div
      ref={tooltipRef}
      role="dialog"
      aria-label={`Tour step ${step + 1} of ${totalSteps}: ${title}`}
      aria-modal="true"
      tabIndex={-1}
      style={style}
      // Stop clicks from bubbling to the backdrop click-capture layer
      onClick={(e) => e.stopPropagation()}
      className="focus:outline-none"
    >
      {/* Announce step changes to screen readers */}
      <span className="sr-only" aria-live="polite" aria-atomic="true">
        Step {step + 1} of {totalSteps}: {title}. {description}
      </span>
      {/* Up-arrow when tooltip is below its target */}
      {placement === 'below' && targetRect && (
        <div
          aria-hidden="true"
          className="absolute -top-1.5 h-3 w-3 rotate-45 border-l border-t border-border bg-card"
          style={{ left: 24 }}
        />
      )}

      <div className="overflow-hidden rounded-xl border border-border bg-card shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-2 px-4 pb-2 pt-4">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              {step + 1} of {totalSteps}
            </p>
            <h3 className="mt-0.5 text-sm font-bold leading-snug text-foreground">{title}</h3>
          </div>
          <button
            onClick={onSkip}
            aria-label="Skip tour"
            className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Progress bar */}
        <div className="mb-3 px-4">
          <div className="h-0.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all duration-300 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Description */}
        <p className="px-4 pb-4 text-[13px] leading-relaxed text-muted-foreground">{description}</p>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border bg-muted/20 px-4 py-3">
          <button
            onClick={onSkip}
            className="text-2xs rounded text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Skip tour
          </button>

          <div className="flex items-center gap-2">
            {!isFirst && (
              <button
                onClick={onBack}
                className="flex items-center gap-1 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                Back
              </button>
            )}
            <button
              onClick={onNext}
              className="flex items-center gap-1 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {isLast ? 'Finish' : 'Next'}
              {!isLast && <ChevronRight className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Down-arrow when tooltip is above its target */}
      {placement === 'above' && targetRect && (
        <div
          aria-hidden="true"
          className="absolute -bottom-1.5 h-3 w-3 rotate-45 border-b border-r border-border bg-card"
          style={{ left: 24 }}
        />
      )}
    </div>
  )
}
