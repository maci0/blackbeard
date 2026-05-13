import { useState, useEffect } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { LayoutDashboard, Database, Play, Cpu, Wrench } from 'lucide-react'
import { useDarkMode } from '@/lib/hooks'
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
  useDarkMode()

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
    void navigate('/studio')
    // Small delay to let the page render before spotlighting elements
    setTimeout(() => {
      setTourKey((k) => k + 1)
      setShowTour(true)
    }, 600)
  }

  const handleSkipWelcome = () => {
    setShowWelcome(false)
    void navigate('/studio')
  }

  /* ── Tour handlers ── */

  const handleTourComplete = () => {
    setShowTour(false)
  }

  const handleRestartTour = () => {
    localStorage.removeItem('blackbeard_tour_completed')
    void navigate('/studio')
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
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
      >
        Skip to main content
      </a>

      {/* ── Sidebar ── */}
      <aside aria-label="Main navigation" className="flex w-60 flex-col border-r bg-card">
        <div className="border-b p-4">
          <span className="text-xl font-bold tracking-tight">Blackbeard</span>
          <p className="text-xs text-muted-foreground">Agent Management Platform</p>
        </div>

        <nav aria-label="Primary" data-tour="sidebar-nav" className="flex-1 space-y-1 p-2">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors duration-150 ${
                  isActive
                    ? 'border-l-2 border-indigo-500 bg-accent text-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={`h-4 w-4 ${isActive ? 'text-indigo-500' : ''}`} />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Sidebar footer: Help menu + version */}
        <div className="flex items-center justify-between border-t p-4">
          <HelpMenu onRestartTour={handleRestartTour} />
          <span className="text-xs text-muted-foreground">v0.1.0</span>
        </div>
      </aside>

      {/* ── Main content ── */}
      <main id="main-content" className="flex flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>

      {/* ── Onboarding ── */}
      <WelcomeDialog open={showWelcome} onStartTour={handleStartTour} onSkip={handleSkipWelcome} />
      <GuidedTour key={tourKey} active={showTour} onComplete={handleTourComplete} />
    </div>
  )
}
