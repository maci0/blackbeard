import { useState, useEffect, useCallback, useRef } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Database,
  Play,
  Cpu,
  Wrench,
  Users,
  Shield,
  Store,
  Menu,
  X,
  Anchor,
  Timer,
  PanelLeftClose,
  PanelLeftOpen,
  Sun,
  Moon,
  Monitor,
  LogOut,
} from 'lucide-react'
import { useDarkMode } from '@/hooks'
import { useAuthStore } from '@/stores/authStore'
import WelcomeDialog from './onboarding/WelcomeDialog'
import GuidedTour from './onboarding/GuidedTour'
import HelpMenu from './onboarding/HelpMenu'

const navItems = [
  { to: '/studio', label: 'Studio', icon: LayoutDashboard },
  { to: '/resources', label: 'Resources', icon: Database },
  { to: '/executions', label: 'Executions', icon: Play },
  { to: '/models', label: 'Models', icon: Cpu },
  { to: '/tools', label: 'Tools', icon: Wrench },
  { to: '/users', label: 'Users', icon: Users },
  { to: '/roles', label: 'Roles', icon: Shield },
  { to: '/marketplace', label: 'Marketplace', icon: Store },
  { to: '/automations', label: 'Automations', icon: Timer },
]

function BlackbeardLogo({ size = 28 }: { size?: number }) {
  return (
    <div
      className="flex shrink-0 items-center justify-center rounded-md bg-slate-900"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <Anchor className="text-indigo-400" style={{ width: size * 0.6, height: size * 0.6 }} />
    </div>
  )
}

function UserInitials({ name, size = 'md' }: { name: string; size?: 'sm' | 'md' }) {
  const initial = name.length > 0 ? name.charAt(0).toUpperCase() : '?'
  const sizeClass = size === 'sm' ? 'h-7 w-7 text-xs' : 'h-8 w-8 text-sm'
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full bg-primary font-semibold text-primary-foreground ${sizeClass}`}
      aria-hidden="true"
    >
      {initial}
    </span>
  )
}

export default function Layout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { preference, cycle } = useDarkMode()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)

  const [showWelcome, setShowWelcome] = useState(false)
  const [showTour, setShowTour] = useState(false)
  const [tourKey, setTourKey] = useState(0)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem('blackbeard_sidebar_collapsed') === 'true',
  )
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const sidebarRef = useRef<HTMLElement>(null)

  useEffect(() => {
    localStorage.setItem('blackbeard_sidebar_collapsed', String(collapsed))
  }, [collapsed])

  useEffect(() => {
    setSidebarOpen(false)
  }, [location.pathname])

  const prevSidebarOpen = useRef(false)
  useEffect(() => {
    if (sidebarOpen && !prevSidebarOpen.current) {
      requestAnimationFrame(() => {
        const firstLink = sidebarRef.current?.querySelector<HTMLElement>('a[href]')
        firstLink?.focus()
      })
    } else if (!sidebarOpen && prevSidebarOpen.current) {
      menuButtonRef.current?.focus()
    }
    prevSidebarOpen.current = sidebarOpen
  }, [sidebarOpen])

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') setSidebarOpen(false)
  }, [])

  useEffect(() => {
    if (sidebarOpen) {
      document.addEventListener('keydown', handleKeyDown)
      return () => document.removeEventListener('keydown', handleKeyDown)
    }
  }, [sidebarOpen, handleKeyDown])

  useEffect(() => {
    if (!localStorage.getItem('blackbeard_onboarding_completed')) {
      setShowWelcome(true)
    }
  }, [])

  const handleStartTour = () => {
    setShowWelcome(false)
    void navigate('/studio')
    setTimeout(() => {
      setTourKey((k) => k + 1)
      setShowTour(true)
    }, 600)
  }

  const handleSkipWelcome = () => {
    setShowWelcome(false)
    void navigate('/studio')
  }

  const handleTourComplete = () => {
    setShowTour(false)
  }

  const handleRestartTour = () => {
    localStorage.removeItem('blackbeard_tour_completed')
    void navigate('/studio')
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
      <header className="fixed left-0 right-0 top-0 z-40 flex h-12 items-center gap-3 border-b bg-card px-3 md:hidden">
        <button
          ref={menuButtonRef}
          onClick={() => setSidebarOpen((v) => !v)}
          aria-label={sidebarOpen ? 'Close navigation menu' : 'Open navigation menu'}
          aria-expanded={sidebarOpen}
          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
        <BlackbeardLogo size={22} />
        <span className="text-sm font-bold tracking-tight">Blackbeard</span>
      </header>

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
        className={`fixed inset-y-0 left-0 z-50 flex flex-col border-r bg-card transition-all duration-200 ease-in-out md:static md:translate-x-0 ${
          collapsed ? 'md:w-14' : 'md:w-60'
        } w-60 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}
      >
        {/* Branding */}
        <button
          onClick={() => void navigate('/studio')}
          className={`flex items-center gap-3 border-b p-4 text-left transition-all hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring ${
            collapsed ? 'md:justify-center md:px-2' : ''
          }`}
          aria-label="Go to Studio"
        >
          <BlackbeardLogo size={collapsed ? 24 : 28} />
          <div className={collapsed ? 'md:hidden' : ''}>
            <span className="text-xl font-bold tracking-tight">Blackbeard</span>
            <p className="text-xs text-muted-foreground">Agent Management Platform</p>
          </div>
        </button>

        <nav
          aria-label="Primary"
          data-tour="sidebar-nav"
          className={`flex-1 space-y-1 p-2 ${collapsed ? 'md:px-1' : ''}`}
        >
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              title={collapsed ? label : undefined}
              aria-label={label}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                  collapsed ? 'md:justify-center md:px-0' : ''
                } ${
                  isActive
                    ? 'bg-accent text-foreground ring-2 ring-inset ring-primary/20'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={`h-4 w-4 shrink-0 ${isActive ? 'text-primary' : ''}`} />
                  <span className={collapsed ? 'md:sr-only' : ''}>{label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* User section */}
        {user && (
          <div
            className={`border-t p-2 ${collapsed ? 'md:flex md:flex-col md:items-center md:gap-1 md:px-1' : 'px-3 py-3'}`}
          >
            {collapsed ? (
              <button
                onClick={() => {
                  logout()
                  void navigate('/login')
                }}
                title={`Sign out (${user.display_name || user.email})`}
                aria-label={`Sign out as ${user.display_name || user.email}`}
                className="hidden rounded-md p-1 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:inline-flex"
              >
                <UserInitials name={user.display_name || user.email} size="sm" />
              </button>
            ) : null}
            <div className={collapsed ? 'md:hidden' : ''}>
              <div className="flex items-center gap-2.5">
                <UserInitials name={user.display_name || user.email} />
                <div className="min-w-0 flex-1">
                  <p
                    className="truncate text-sm font-medium"
                    title={user.display_name || user.email}
                  >
                    {user.display_name || user.email}
                  </p>
                  {user.display_name && (
                    <p className="truncate text-xs text-muted-foreground" title={user.email}>
                      {user.email}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => {
                    logout()
                    void navigate('/login')
                  }}
                  aria-label="Sign out"
                  title="Sign out"
                  className="shrink-0 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Sidebar footer */}
        <div
          className={`flex items-center border-t p-2 ${
            collapsed ? 'md:flex-col md:justify-center md:gap-2' : 'justify-between px-4 py-4'
          }`}
        >
          <div className={collapsed ? 'md:hidden' : ''}>
            <HelpMenu onRestartTour={handleRestartTour} />
          </div>
          <div className={`flex items-center gap-2 ${collapsed ? '' : ''}`}>
            <span className={`text-xs text-muted-foreground ${collapsed ? 'md:hidden' : ''}`}>
              v0.1.0
            </span>
            <button
              onClick={cycle}
              aria-label={`Theme: ${preference}. Click to cycle theme.`}
              title={`Theme: ${preference}`}
              className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {preference === 'dark' ? (
                <Moon className="h-4 w-4" />
              ) : preference === 'light' ? (
                <Sun className="h-4 w-4" />
              ) : (
                <Monitor className="h-4 w-4" />
              )}
            </button>
            <button
              onClick={() => setCollapsed((v) => !v)}
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              className="hidden rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:inline-flex"
            >
              {collapsed ? (
                <PanelLeftOpen className="h-4 w-4" />
              ) : (
                <PanelLeftClose className="h-4 w-4" />
              )}
            </button>
          </div>
        </div>
      </aside>

      {/* ── Main content ── */}
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
