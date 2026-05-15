import { useState, useEffect, useCallback, useRef } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { LayoutDashboard, Database, Play, Cpu, Wrench, Menu, X } from 'lucide-react'
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
  const location = useLocation()
  useDarkMode()

  const [showWelcome, setShowWelcome] = useState(false)
  const [showTour, setShowTour] = useState(false)
  // Increment to force GuidedTour remount (fresh step=0) on restart
  const [tourKey, setTourKey] = useState(0)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const sidebarRef = useRef<HTMLElement>(null)

  // Close mobile sidebar on route change
  useEffect(() => {
    setSidebarOpen(false)
  }, [location.pathname])

  // Move focus into sidebar when it opens; restore to menu button when it closes
  const prevSidebarOpen = useRef(false)
  useEffect(() => {
    if (sidebarOpen && !prevSidebarOpen.current) {
      // Focus the first nav link inside the sidebar
      requestAnimationFrame(() => {
        const firstLink = sidebarRef.current?.querySelector<HTMLElement>('a[href]')
        firstLink?.focus()
      })
    } else if (!sidebarOpen && prevSidebarOpen.current) {
      menuButtonRef.current?.focus()
    }
    prevSidebarOpen.current = sidebarOpen
  }, [sidebarOpen])

  // Close mobile sidebar on Escape key
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') setSidebarOpen(false)
  }, [])

  useEffect(() => {
    if (sidebarOpen) {
      document.addEventListener('keydown', handleKeyDown)
      return () => document.removeEventListener('keydown', handleKeyDown)
    }
  }, [sidebarOpen, handleKeyDown])

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
    <div className="flex h-screen" inert={showTour || undefined}>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
      >
        Skip to main content
      </a>

      {/* ── Mobile header ── */}
      <div className="fixed left-0 right-0 top-0 z-40 flex h-12 items-center gap-3 border-b bg-card px-3 md:hidden">
        <button
          ref={menuButtonRef}
          onClick={() => setSidebarOpen((v) => !v)}
          aria-label={sidebarOpen ? 'Close navigation menu' : 'Open navigation menu'}
          aria-expanded={sidebarOpen}
          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
        <span className="text-sm font-bold tracking-tight">Blackbeard</span>
      </div>

      {/* ── Mobile backdrop ── */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 md:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* ── Sidebar ── */}
      <aside
        ref={sidebarRef}
        aria-label="Main navigation"
        className={`fixed inset-y-0 left-0 z-50 flex w-60 flex-col border-r bg-card transition-transform duration-200 ease-in-out md:static md:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
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
                `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                  isActive
                    ? 'bg-accent text-foreground ring-2 ring-inset ring-primary/20'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={`h-4 w-4 ${isActive ? 'text-primary' : ''}`} />
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
      {/* inert prevents focus from reaching obscured content while mobile sidebar is open */}
      <main
        id="main-content"
        className="flex flex-1 flex-col overflow-hidden pt-12 md:pt-0"
        inert={sidebarOpen || undefined}
      >
        <Outlet />
      </main>

      {/* ── Onboarding ── */}
      <WelcomeDialog open={showWelcome} onStartTour={handleStartTour} onSkip={handleSkipWelcome} />
      <GuidedTour key={tourKey} active={showTour} onComplete={handleTourComplete} />
    </div>
  )
}
