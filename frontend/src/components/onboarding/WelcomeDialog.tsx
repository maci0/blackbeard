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
      <div className={`p-2 rounded-lg ${color}`}>
        <Icon className="h-4 w-4" />
      </div>
      <p className="text-sm font-semibold text-foreground leading-snug">{title}</p>
      <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
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
        <Dialog.Overlay className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50" />

        <Dialog.Content
          className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[560px] max-w-[92vw] bg-card border border-border rounded-2xl shadow-2xl overflow-hidden focus:outline-none"
          // Prevent closing by clicking outside — user must choose a button
          onInteractOutside={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => e.preventDefault()}
          aria-describedby="welcome-description"
        >
          {/* ── Hero header ── */}
          <div className="relative px-8 pt-10 pb-8 overflow-hidden bg-gradient-to-br from-slate-900 via-slate-800 to-slate-950">
            {/* Decorative blurred orbs */}
            <div className="pointer-events-none absolute -top-10 -right-10 w-40 h-40 rounded-full bg-violet-500/25 blur-3xl" />
            <div className="pointer-events-none absolute -bottom-6 -left-6 w-32 h-32 rounded-full bg-blue-500/20 blur-3xl" />
            <div className="pointer-events-none absolute top-4 left-1/2 w-20 h-20 rounded-full bg-emerald-500/15 blur-2xl" />

            <div className="relative">
              {/* Logo mark */}
              <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-white/10 border border-white/20 mb-5">
                <Anchor className="h-6 w-6 text-white" />
              </div>

              <Dialog.Title className="text-2xl font-bold text-white tracking-tight">
                Blackbeard
              </Dialog.Title>
              <p className="text-sm text-white/60 mt-0.5 font-medium tracking-wide uppercase">
                Agent Management Platform
              </p>
              <p id="welcome-description" className="text-[15px] text-white/75 mt-3 leading-relaxed max-w-sm">
                Build, run, and manage AI agent crews — visually.
              </p>
            </div>
          </div>

          {/* ── Body ── */}
          <div className="px-8 py-6">
            {/* Feature cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
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
                // eslint-disable-next-line jsx-a11y/no-autofocus
                autoFocus
                onClick={handleStartTour}
                className="flex-1 py-2.5 px-4 text-sm font-semibold bg-primary text-primary-foreground rounded-lg hover:opacity-90 transition-opacity focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none shadow-sm"
              >
                Get Started →
              </button>
              <button
                onClick={handleSkip}
                className="py-2.5 px-4 text-sm font-medium text-muted-foreground border border-border rounded-lg hover:bg-muted transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                Skip
              </button>
            </div>

            <p className="text-[11px] text-muted-foreground/60 text-center mt-3">
              You can restart the tour anytime from the Help menu
            </p>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
