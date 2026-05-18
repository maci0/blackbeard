import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LayoutGrid,
  Boxes,
  Play,
  Shield,
  Terminal,
  ArrowRight,
  ArrowLeft,
  X,
  Sparkles,
} from 'lucide-react'

interface Step {
  icon: React.ReactNode
  title: string
  description: string
  action?: { label: string; path: string }
}

const STEPS: Step[] = [
  {
    icon: <LayoutGrid className="h-8 w-8 text-primary" />,
    title: 'Visual Studio',
    description:
      'Drag agents, tasks, and tools onto the canvas to design your crew. Connect them visually, configure properties, and save — no YAML required.',
    action: { label: 'Open Studio', path: '/studio' },
  },
  {
    icon: <Boxes className="h-8 w-8 text-primary" />,
    title: 'Resource Library',
    description:
      'All entities — agents, tasks, crews, tools, LLM connections — are stored as resources. Browse, search, and manage them from the Resources page.',
    action: { label: 'Browse Resources', path: '/resources' },
  },
  {
    icon: <Play className="h-8 w-8 text-primary" />,
    title: 'Run Crews',
    description:
      "Execute your crews with one click. Watch progress in real-time via event streaming. Train and test with CrewAI's built-in learning loops.",
    action: { label: 'View Executions', path: '/executions' },
  },
  {
    icon: <Shield className="h-8 w-8 text-primary" />,
    title: 'RBAC & Policies',
    description:
      'Control who can do what with roles and role bindings. Agent policies enforce tool allowlists, budget limits, and sandbox tiers at runtime.',
    action: { label: 'Manage Roles', path: '/roles' },
  },
  {
    icon: <Terminal className="h-8 w-8 text-primary" />,
    title: 'CLI & API',
    description:
      'Everything in the UI is also available via the blackbeard CLI and REST API. Export resources as YAML, script deployments, integrate with CI/CD.',
  },
]

export function OnboardingWizard({ onDismiss }: { onDismiss: () => void }) {
  const [step, setStep] = useState(0)
  const navigate = useNavigate()
  const current = STEPS[step]
  const isLast = step === STEPS.length - 1

  if (!current) return null

  function handleAction() {
    if (current?.action) {
      onDismiss()
      void navigate(current.action.path)
    }
  }

  function handleFinish() {
    onDismiss()
    void navigate('/studio')
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Welcome to Blackbeard"
    >
      <div className="relative mx-4 w-full max-w-lg rounded-xl border bg-card p-8 shadow-2xl">
        {/* Close button */}
        <button
          onClick={onDismiss}
          className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground hover:text-foreground"
          aria-label="Skip onboarding"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Header */}
        {step === 0 && (
          <div className="mb-6 flex items-center gap-2 text-primary">
            <Sparkles className="h-5 w-5" />
            <span className="text-sm font-medium">Welcome to Blackbeard</span>
          </div>
        )}

        {/* Step content */}
        <div className="mb-8">
          <div className="mb-4">{current.icon}</div>
          <h2 className="mb-2 text-xl font-semibold">{current.title}</h2>
          <p className="text-sm leading-relaxed text-muted-foreground">{current.description}</p>
        </div>

        {/* Progress dots */}
        <div className="mb-6 flex justify-center gap-1.5" aria-label="Step progress">
          {STEPS.map((_, i) => (
            <button
              key={i}
              onClick={() => setStep(i)}
              className={`h-1.5 rounded-full transition-all ${
                i === step
                  ? 'w-6 bg-primary'
                  : 'w-1.5 bg-muted-foreground/30 hover:bg-muted-foreground/50'
              }`}
              aria-label={`Go to step ${i + 1}`}
              aria-current={i === step ? 'step' : undefined}
            />
          ))}
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between">
          <div>
            {step > 0 && (
              <button
                onClick={() => setStep(step - 1)}
                className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Back
              </button>
            )}
          </div>

          <div className="flex items-center gap-3">
            {current.action && (
              <button onClick={handleAction} className="text-sm text-primary hover:underline">
                {current.action.label}
              </button>
            )}

            {isLast ? (
              <button
                onClick={handleFinish}
                className="flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
              >
                Get Started
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            ) : (
              <button
                onClick={() => setStep(step + 1)}
                className="flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
              >
                Next
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
