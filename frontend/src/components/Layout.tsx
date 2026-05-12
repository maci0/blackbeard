import { useState, useEffect } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  Database,
  Play,
  Cpu,
  Wrench,
} from 'lucide-react'
import WelcomeDialog from './onboarding/WelcomeDialog'
import GuidedTour from './onboarding/GuidedTour'
import HelpMenu from './onboarding/HelpMenu'

/* ------------------------------------------------------------------ */
/* Nav items                                                           */
/* ------------------------------------------------------------------ */

const navItems = [
  { to: '/studio', label: 'Studio', icon: LayoutDashboard },
  { to: '/resources', label: 'Resources', icon: Database },
  { to: '/executions', label: 'Executions', icon: Play },
  { to: '/models', label: 'Models', icon: Cpu },
  { to: '/tools', label: 'Tools', icon: Wrench },
]

/* ------------------------------------------------------------------ */
/* Layout                                                              */
/* ------------------------------------------------------------------ */

export default function Layout() {
  const navigate = useNavigate()

  const [showWelcome, setShowWelcome] = useState(false)
  const [showTour, setShowTour] = useState(false)
  // Increment to force GuidedTour remount (fresh step=0) on restart
  const [tourKey, setTourKey] = useState(0)

  // Show welcome dialog on first ever visit
  useEffect(() => {
    if (!localStorage.getItem('blackbeard_onboarding_completed')) {
      setShowWelcome(true)
    }
  }, [])

  /* ── Welcome dialog handlers ── */

  const handleStartTour = () => {
    setShowWelcome(false)
    // Navigate to Studio so tour targets are in the DOM
    navigate('/studio')
    // Small delay to let the page render before spotlighting elements
    setTimeout(() => {
      setTourKey((k) => k + 1)
      setShowTour(true)
    }, 600)
  }

  const handleSkipWelcome = () => {
    setShowWelcome(false)
    navigate('/studio')
  }

  /* ── Tour handlers ── */

  const handleTourComplete = () => {
    setShowTour(false)
  }

  const handleRestartTour = () => {
    localStorage.removeItem('blackbeard_tour_completed')
    navigate('/studio')
    // Delay slightly so navigation settles before spotlighting
    setTimeout(() => {
      setTourKey((k) => k + 1)
      setShowTour(true)
    }, 400)
  }

  return (
    <div className="flex h-screen">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-primary focus:text-primary-foreground focus:rounded-lg"
      >
        Skip to main content
      </a>

      {/* ── Sidebar ── */}
      <aside className="w-60 border-r bg-card flex flex-col">
        <div className="p-4 border-b">
          <span className="text-xl font-bold tracking-tight">Blackbeard</span>
          <p className="text-xs text-muted-foreground">Agent Management Platform</p>
        </div>

        <nav data-tour="sidebar-nav" className="flex-1 p-2 space-y-1">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                }`
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Sidebar footer: Help menu + version */}
        <div className="p-4 border-t flex items-center justify-between">
          <HelpMenu onRestartTour={handleRestartTour} />
          <span className="text-xs text-muted-foreground">v0.1.0</span>
        </div>
      </aside>

      {/* ── Main content ── */}
      <main id="main-content" className="flex-1 overflow-hidden flex flex-col">
        <Outlet />
      </main>

      {/* ── Onboarding ── */}
      <WelcomeDialog
        open={showWelcome}
        onStartTour={handleStartTour}
        onSkip={handleSkipWelcome}
      />
      <GuidedTour
        key={tourKey}
        active={showTour}
        onComplete={handleTourComplete}
      />
    </div>
  )
}
