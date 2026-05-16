import * as Dialog from '@radix-ui/react-dialog'
import { LayoutDashboard, Play, Database, Anchor } from 'lucide-react'

/* ------------------------------------------------------------------ */
/* Feature card                                                        */
/* ------------------------------------------------------------------ */

function FeatureCard({
  icon: Icon,
  title,
  description,
  color,
}: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  description: string
  color: string
}) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-xl border border-border bg-muted/30 p-4">
      <div className={`rounded-lg p-2 ${color}`}>
        <Icon className="h-4 w-4" />
      </div>
      <p className="text-sm font-semibold leading-snug text-foreground">{title}</p>
      <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

interface WelcomeDialogProps {
  open: boolean
  onStartTour: () => void
  onSkip: () => void
}

export default function WelcomeDialog({ open, onStartTour, onSkip }: WelcomeDialogProps) {
  const handleStartTour = () => {
    localStorage.setItem('blackbeard_onboarding_completed', 'true')
    onStartTour()
  }

  const handleSkip = () => {
    localStorage.setItem('blackbeard_onboarding_completed', 'true')
    onSkip()
  }

  return (
    <Dialog.Root open={open} modal>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />

        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 w-[560px] max-w-[92vw] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-2xl border border-border bg-card shadow-2xl focus:outline-none"
          // Prevent closing by clicking outside — user must choose a button
          onInteractOutside={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => e.preventDefault()}
          aria-describedby="welcome-description"
        >
          {/* ── Hero header ── */}
          <div className="relative overflow-hidden bg-gradient-to-br from-slate-900 via-slate-800 to-slate-950 px-8 pb-8 pt-10">
            {/* Decorative blurred orbs */}
            <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-violet-500/25 blur-3xl" />
            <div className="pointer-events-none absolute -bottom-6 -left-6 h-32 w-32 rounded-full bg-blue-500/20 blur-3xl" />
            <div className="pointer-events-none absolute left-1/2 top-4 h-20 w-20 rounded-full bg-emerald-500/15 blur-2xl" />

            <div className="relative">
              {/* Logo mark */}
              <div className="mb-5 inline-flex h-12 w-12 items-center justify-center rounded-xl border border-white/20 bg-white/10">
                <Anchor className="h-6 w-6 text-white" />
              </div>

              <Dialog.Title className="text-2xl font-bold tracking-tight text-white">
                Blackbeard
              </Dialog.Title>
              <p className="mt-0.5 text-sm font-medium uppercase tracking-wide text-white/60">
                Agent Management Platform
              </p>
              <p
                id="welcome-description"
                className="mt-3 max-w-sm text-[15px] leading-relaxed text-white/75"
              >
                Build, run, and manage AI agent crews — visually.
              </p>
            </div>
          </div>

          {/* ── Body ── */}
          <div className="px-8 py-6">
            {/* Feature cards */}
            <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
              <FeatureCard
                icon={LayoutDashboard}
                title="Visual Studio"
                description="Drag-and-drop agents, tasks, and tools on a canvas"
                color="bg-violet-100 text-violet-600"
              />
              <FeatureCard
                icon={Play}
                title="One-Click Run"
                description="Execute crews and watch results in real-time"
                color="bg-emerald-100 text-emerald-600"
              />
              <FeatureCard
                icon={Database}
                title="Full Lifecycle"
                description="Manage resources, monitor executions, track costs"
                color="bg-blue-100 text-blue-600"
              />
            </div>

            {/* CTA buttons */}
            <div className="flex items-center gap-3">
              <button
                autoFocus
                onClick={handleStartTour}
                className="flex-1 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground shadow-sm transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Get Started →
              </button>
              <button
                onClick={handleSkip}
                className="rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Skip
              </button>
            </div>

            <p className="text-2xs mt-3 text-center text-muted-foreground">
              You can restart the tour anytime from the Help menu
            </p>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
