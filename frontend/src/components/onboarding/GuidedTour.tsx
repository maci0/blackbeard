import { useState, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { STORAGE_KEYS } from '@/lib/utils'
import { TourOverlay } from './TourOverlay'
import { TourTooltip } from './TourTooltip'

/* ------------------------------------------------------------------ */
/* Tour step definitions                                               */
/* ------------------------------------------------------------------ */

const TOUR_STEPS = [
  {
    target: '[data-tour="palette"]',
    title: 'Palette',
    description:
      'Drag agents, tasks, and tools from here onto the canvas to build your crew. You can also press Enter or Space on a card to add it directly.',
  },
  {
    target: '[data-tour="canvas"]',
    title: 'Canvas',
    description:
      "This is your workspace. Connect nodes with arrows to define your crew's workflow. Drag from a node's handle to create connections.",
  },
  {
    target: '[data-tour="crew-name"]',
    title: 'Name Your Crew',
    description:
      'Give your crew a name: it becomes the resource identifier used by the API and CLI. Use lowercase letters and hyphens.',
  },
  {
    target: '[data-tour="save-button"]',
    title: 'Save',
    description:
      'Save your crew and all its resources to the server. Changes are auto-saved before running, so you never lose work.',
  },
  {
    target: '[data-tour="run-button"]',
    title: 'Run',
    description:
      'Execute your crew and watch results in real-time. Head to the Executions page to see token usage, cost, and task outputs.',
  },
  {
    target: '[data-tour="sidebar-nav"]',
    title: 'Navigation',
    description:
      'Use the sidebar to manage Resources, view Executions, configure LLM Connections, and browse registered Tools.',
  },
] as const

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

interface GuidedTourProps {
  active: boolean
  onComplete: () => void
}

export default function GuidedTour({ active, onComplete }: GuidedTourProps) {
  const [step, setStep] = useState(0)
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null)
  const prevActiveRef = useRef(false)
  const returnFocusRef = useRef<HTMLElement | null>(null)

  // Reset to step 0 each time the tour becomes active
  useEffect(() => {
    if (active && !prevActiveRef.current) {
      setStep(0)
      returnFocusRef.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null
    }
    prevActiveRef.current = active
  }, [active])

  // Query the target element whenever step or active state changes
  useEffect(() => {
    if (!active) return

    const stepDef = TOUR_STEPS[step]
    if (!stepDef) return

    const update = () => {
      const el = document.querySelector(stepDef.target)
      if (el) {
        // Scroll the element into view if needed
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
        setTargetRect(el.getBoundingClientRect())
      } else {
        setTargetRect(null) // graceful fallback: tooltip shows centered
      }
    }

    // Small delay so DOM has settled after navigation / re-render
    const timer = setTimeout(update, 80)

    window.addEventListener('resize', update)
    // Re-measure on any scroll (handles nested scrollable containers)
    window.addEventListener('scroll', update, { capture: true, passive: true })

    return () => {
      clearTimeout(timer)
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [active, step])

  /* ── Navigation handlers ── */

  const handleComplete = () => {
    localStorage.setItem(STORAGE_KEYS.TOUR_COMPLETED, 'true')
    onComplete()
    returnFocusRef.current?.focus()
  }

  const handleNext = () => {
    if (step < TOUR_STEPS.length - 1) {
      setStep((s) => s + 1)
    } else {
      handleComplete()
    }
  }

  const handleBack = () => {
    if (step > 0) setStep((s) => s - 1)
  }

  if (!active) return null

  const currentStep = TOUR_STEPS[step]!

  return createPortal(
    <>
      <TourOverlay targetRect={targetRect} onBackdropClick={handleNext} />
      <TourTooltip
        title={currentStep.title}
        description={currentStep.description}
        step={step}
        totalSteps={TOUR_STEPS.length}
        onNext={handleNext}
        onBack={handleBack}
        onSkip={handleComplete}
        targetRect={targetRect}
      />
    </>,
    document.body,
  )
}
