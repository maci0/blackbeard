/* ------------------------------------------------------------------ */
/* TourOverlay — spotlight cutout using the box-shadow technique       */
/* A transparent div positioned over the target element, with a huge  */
/* box-shadow that fills the rest of the screen with a dark overlay.  */
/* ------------------------------------------------------------------ */

interface TourOverlayProps {
  targetRect: DOMRect | null
  /** Called when the user clicks anywhere on the dark backdrop */
  onBackdropClick?: () => void
}

export function TourOverlay({ targetRect, onBackdropClick }: TourOverlayProps) {
  const padding = 6
  const reducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  return (
    <>
      {/* Full-screen transparent click-capture layer (z below spotlight) */}
      {/* Clicking backdrop advances the tour step */}
      <div
        aria-hidden="true"
        onClick={onBackdropClick}
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 9997,
          cursor: 'pointer',
          // No background — the spotlight's box-shadow creates the dark overlay
        }}
      />

      {/* Spotlight — transparent box positioned over the target.           */}
      {/* The giant box-shadow creates the semi-opaque overlay around it.   */}
      {/* pointer-events: none so the target element remains interactive.   */}
      {targetRect && (
        <div
          aria-hidden="true"
          style={{
            position: 'fixed',
            top: targetRect.top - padding,
            left: targetRect.left - padding,
            width: targetRect.width + padding * 2,
            height: targetRect.height + padding * 2,
            boxShadow: '0 0 0 9999px rgba(0, 0, 0, 0.55)',
            borderRadius: 10,
            zIndex: 9998,
            pointerEvents: 'none',
            transition: reducedMotion
              ? undefined
              : 'top 0.22s cubic-bezier(0.4, 0, 0.2, 1), left 0.22s cubic-bezier(0.4, 0, 0.2, 1), width 0.22s cubic-bezier(0.4, 0, 0.2, 1), height 0.22s cubic-bezier(0.4, 0, 0.2, 1)',
          }}
        />
      )}

      {/* When there's no targetRect, show a plain dark full-screen overlay */}
      {!targetRect && (
        <div
          aria-hidden="true"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.55)',
            zIndex: 9998,
            pointerEvents: 'none',
          }}
        />
      )}
    </>
  )
}
