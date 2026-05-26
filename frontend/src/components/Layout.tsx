import { useState, useEffect, useCallback, useRef } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  PenTool,
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
  Search,
  Settings as SettingsIcon,
  MessageSquare,
  ScrollText,
  Webhook,
  Bell,
  Check,
  BookOpen,
  ChevronDown,
  FolderOpen,
  Plus,
  Loader2,
  AlertTriangle,
  Keyboard,
} from 'lucide-react'
import { useDarkMode, useHealthCheck } from '@/hooks'
import { Spinner } from '@/components/ui/Spinner'
import { cn, STORAGE_KEYS, STORAGE_KEYS_NAV } from '@/lib/utils'
import { useNotificationStore } from '@/stores/notificationStore'
import { useNamespaceStore } from '@/stores/namespaceStore'
import { isMac, modKey } from '@/lib/platform'
import { useAuthStore } from '@/stores/authStore'
import { useToastStore } from '@/stores/toastStore'
import { CommandPalette } from './ui/CommandPalette'
import { KeyboardShortcutsDialog } from './ui/KeyboardShortcutsDialog'
import WelcomeDialog from './onboarding/WelcomeDialog'
import GuidedTour from './onboarding/GuidedTour'
import HelpMenu from './onboarding/HelpMenu'

type NavItem = { to: string; label: string; icon: React.ComponentType<{ className?: string }> }

const navSections: Array<{ key: string; label: string; items: NavItem[] }> = [
  {
    key: 'main',
    label: 'Main',
    items: [
      { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
      { to: '/studio', label: 'Studio', icon: PenTool },
    ],
  },
  {
    key: 'resources',
    label: 'Resources',
    items: [
      { to: '/resources', label: 'Resources', icon: Database },
      { to: '/models', label: 'Models', icon: Cpu },
      { to: '/tools', label: 'Tools', icon: Wrench },
      { to: '/knowledge', label: 'Knowledge', icon: BookOpen },
    ],
  },
  {
    key: 'operations',
    label: 'Operations',
    items: [
      { to: '/executions', label: 'Executions', icon: Play },
      { to: '/chat', label: 'Chat', icon: MessageSquare },
      { to: '/automations', label: 'Automations', icon: Timer },
    ],
  },
  {
    key: 'admin',
    label: 'Admin',
    items: [
      { to: '/users', label: 'Users', icon: Users },
      { to: '/roles', label: 'Roles', icon: Shield },
      { to: '/audit-logs', label: 'Audit Logs', icon: ScrollText },
      { to: '/webhooks', label: 'Webhooks', icon: Webhook },
    ],
  },
  {
    key: 'other',
    label: 'Other',
    items: [
      { to: '/marketplace', label: 'Marketplace', icon: Store },
      { to: '/settings', label: 'Settings', icon: SettingsIcon },
    ],
  },
]

function loadCollapsedSections(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS_NAV.COLLAPSED_SECTIONS)
    if (raw) return JSON.parse(raw) as Record<string, boolean>
  } catch (err) {
    console.debug('[nav] failed to parse collapsed sections from localStorage:', err)
  }
  return {}
}

function NavSection({
  section,
  collapsed: sidebarCollapsed,
  sectionCollapsed,
  onToggle,
}: {
  section: (typeof navSections)[number]
  collapsed: boolean
  sectionCollapsed: boolean
  onToggle: () => void
}) {
  return (
    <div>
      {!sidebarCollapsed && (
        <button
          type="button"
          onClick={onToggle}
          className="flex w-full items-center gap-1 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70 transition-colors hover:text-muted-foreground"
        >
          <ChevronDown
            className={cn(
              'h-3 w-3 shrink-0 transition-transform duration-200',
              sectionCollapsed && '-rotate-90',
            )}
          />
          {section.label}
        </button>
      )}
      {(sidebarCollapsed || !sectionCollapsed) && (
        <div className="space-y-0.5">
          {section.items.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              title={sidebarCollapsed ? label : undefined}
              aria-label={label}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-md px-3 py-1.5 text-sm font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  sidebarCollapsed && 'md:justify-center md:px-0',
                  isActive
                    ? 'bg-accent text-foreground ring-2 ring-inset ring-primary/20'
                    : 'text-muted-foreground hover:translate-x-0.5 hover:bg-accent hover:text-foreground',
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={cn('h-4 w-4 shrink-0', isActive && 'text-primary')} />
                  <span className={sidebarCollapsed ? 'md:sr-only' : ''}>{label}</span>
                </>
              )}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  )
}

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

function NamespaceSwitcher({ collapsed }: { collapsed: boolean }) {
  const current = useNamespaceStore((s) => s.current)
  const namespaces = useNamespaceStore((s) => s.namespaces)
  const loading = useNamespaceStore((s) => s.loading)
  const setCurrent = useNamespaceStore((s) => s.setCurrent)
  const fetchNamespaces = useNamespaceStore((s) => s.fetchNamespaces)
  const createNamespace = useNamespaceStore((s) => s.createNamespace)
  const toast = useToastStore()
  const navigate = useNavigate()

  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    void fetchNamespaces()
  }, [fetchNamespaces])

  useEffect(() => {
    if (!open) return
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false)
        setCreating(false)
        setNewName('')
      }
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        setCreating(false)
        setNewName('')
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  const handleCreate = async () => {
    const trimmed = newName
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9-]/g, '')
    if (!trimmed) return
    setSubmitting(true)
    try {
      await createNamespace(trimmed)
      setCurrent(trimmed)
      setNewName('')
      setCreating(false)
      setOpen(false)
      toast.success(`Namespace "${trimmed}" created`)
    } catch {
      toast.error('Failed to create namespace')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div ref={dropdownRef} className={`relative mx-2 mb-1 ${collapsed ? 'md:mx-1' : ''}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title={collapsed ? `Namespace: ${current}` : undefined}
        aria-label={`Current namespace: ${current}`}
        aria-expanded={open}
        className={`flex w-full items-center gap-2 rounded-md border bg-muted/30 px-3 py-1.5 text-left text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
          collapsed ? 'md:justify-center md:px-2' : ''
        }`}
      >
        <FolderOpen className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className={`flex-1 truncate ${collapsed ? 'md:sr-only' : ''}`}>{current}</span>
        <ChevronDown
          className={`h-3 w-3 shrink-0 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''} ${collapsed ? 'md:hidden' : ''}`}
        />
      </button>

      {open && (
        <div className="absolute left-0 right-0 z-50 mt-1 overflow-hidden rounded-lg border bg-card shadow-lg">
          <div className="border-b px-3 py-2">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Namespace
            </p>
          </div>
          <div className="max-h-48 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : (
              namespaces.map((ns) => (
                <button
                  key={ns}
                  type="button"
                  onClick={() => {
                    setCurrent(ns)
                    setOpen(false)
                  }}
                  className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm transition-colors hover:bg-accent ${
                    ns === current ? 'bg-primary/10 font-medium text-primary' : ''
                  }`}
                >
                  <span className="flex-1 truncate">{ns}</span>
                  {ns === current && <Check className="h-3 w-3 shrink-0" />}
                </button>
              ))
            )}
          </div>

          <div className="border-t">
            {creating ? (
              <div className="flex items-center gap-1.5 p-2">
                <label htmlFor="new-namespace-input" className="sr-only">
                  New namespace name
                </label>
                <input
                  id="new-namespace-input"
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void handleCreate()
                    if (e.key === 'Escape') {
                      setCreating(false)
                      setNewName('')
                    }
                  }}
                  placeholder="my-namespace"
                  autoFocus
                  autoComplete="off"
                  spellCheck={false}
                  className="flex-1 rounded border bg-background px-2 py-1 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
                <button
                  type="button"
                  onClick={() => void handleCreate()}
                  disabled={submitting || !newName.trim()}
                  className="rounded bg-primary px-2 py-1 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  {submitting ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Add'}
                </button>
              </div>
            ) : (
              <div className="flex flex-col">
                <button
                  type="button"
                  onClick={() => setCreating(true)}
                  className="flex items-center gap-2 px-3 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                >
                  <Plus className="h-3 w-3" />
                  Create namespace
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setOpen(false)
                    void navigate('/resources?kind=namespaces')
                  }}
                  className="flex items-center gap-2 px-3 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                >
                  <SettingsIcon className="h-3 w-3" />
                  Manage namespaces
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default function Layout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { preference, cycle } = useDarkMode()
  const { status: apiHealth, lastChecked: apiLastChecked } = useHealthCheck()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const unreadCount = useNotificationStore((s) => s.unreadCount)
  const notifications = useNotificationStore((s) => s.notifications)
  const markAllRead = useNotificationStore((s) => s.markAllRead)

  const [cmdPaletteOpen, setCmdPaletteOpen] = useState(false)
  const [shortcutsDialogOpen, setShortcutsDialogOpen] = useState(false)
  const [notifOpen, setNotifOpen] = useState(false)
  const notifRef = useRef<HTMLDivElement>(null)
  const [showWelcome, setShowWelcome] = useState(false)
  const [showTour, setShowTour] = useState(false)
  const [tourKey, setTourKey] = useState(0)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(STORAGE_KEYS.SIDEBAR_COLLAPSED) === 'true',
  )
  const [collapsedSections, setCollapsedSections] =
    useState<Record<string, boolean>>(loadCollapsedSections)

  const toggleSection = useCallback((key: string) => {
    setCollapsedSections((prev) => {
      const next = { ...prev, [key]: !prev[key] }
      localStorage.setItem(STORAGE_KEYS_NAV.COLLAPSED_SECTIONS, JSON.stringify(next))
      return next
    })
  }, [])
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const sidebarRef = useRef<HTMLElement>(null)

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.SIDEBAR_COLLAPSED, String(collapsed))
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
    const onGlobalShortcut = (e: KeyboardEvent) => {
      const mod = isMac ? e.metaKey : e.ctrlKey

      if (e.key === 'k' && mod) {
        e.preventDefault()
        setCmdPaletteOpen((v) => !v)
        return
      }

      if (mod && e.shiftKey) {
        if (e.key === 'S' || e.key === 's') {
          e.preventDefault()
          void navigate('/studio')
          return
        }
        if (e.key === 'E' || e.key === 'e') {
          e.preventDefault()
          void navigate('/executions')
          return
        }
        if (e.key === 'N' || e.key === 'n') {
          e.preventDefault()
          void navigate('/resources')
          return
        }
      }

      if (e.key === '.' && mod) {
        e.preventDefault()
        void navigate('/settings')
        return
      }

      if (e.key === '?') {
        const tag = (e.target as HTMLElement).tagName
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
        if ((e.target as HTMLElement).isContentEditable) return
        e.preventDefault()
        setShortcutsDialogOpen(true)
      }
    }
    document.addEventListener('keydown', onGlobalShortcut)
    return () => document.removeEventListener('keydown', onGlobalShortcut)
  }, [navigate])

  useEffect(() => {
    if (!notifOpen) return
    const handleClickOutside = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setNotifOpen(false)
      }
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setNotifOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [notifOpen])

  useEffect(() => {
    if (!localStorage.getItem(STORAGE_KEYS.ONBOARDING_COMPLETED)) {
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
    localStorage.removeItem(STORAGE_KEYS.TOUR_COMPLETED)
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
          className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
        className={`fixed inset-y-0 left-0 z-50 flex flex-col overflow-x-hidden border-r bg-card transition-all duration-200 ease-in-out md:static md:translate-x-0 ${
          collapsed ? 'md:w-14' : 'md:w-60'
        } w-60 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}
      >
        {/* Branding */}
        <button
          type="button"
          onClick={() => void navigate('/dashboard')}
          className={`flex items-center gap-3 border-b p-4 text-left transition-all hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring ${
            collapsed ? 'md:justify-center md:px-2' : ''
          }`}
          aria-label="Go to Dashboard"
        >
          <BlackbeardLogo size={collapsed ? 24 : 28} />
          <div className={collapsed ? 'md:hidden' : ''}>
            <span className="text-xl font-bold tracking-tight">Blackbeard</span>
            <p className="text-xs text-muted-foreground">Agent Management Platform</p>
          </div>
        </button>

        <button
          type="button"
          onClick={() => setCmdPaletteOpen(true)}
          className={`mx-2 mb-1 flex items-center gap-2 rounded-md border bg-muted/50 px-3 py-1.5 text-left text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
            collapsed ? 'md:justify-center md:px-2' : ''
          }`}
          aria-label={`Search (${modKey}K)`}
        >
          <Search className="h-3.5 w-3.5 shrink-0" />
          <span className={`flex-1 ${collapsed ? 'md:sr-only' : ''}`}>Search...</span>
          <kbd
            className={`rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px] ${collapsed ? 'md:hidden' : ''}`}
          >
            {modKey}K
          </kbd>
        </button>

        <NamespaceSwitcher collapsed={collapsed} />

        <nav
          aria-label="Primary"
          data-tour="sidebar-nav"
          className={cn('flex-1 space-y-1 overflow-y-auto p-2', collapsed && 'md:px-1')}
        >
          {navSections.map((section) => (
            <NavSection
              key={section.key}
              section={section}
              collapsed={collapsed}
              sectionCollapsed={!!collapsedSections[section.key]}
              onToggle={() => toggleSection(section.key)}
            />
          ))}
        </nav>

        {/* User section */}
        {user && (
          <div
            className={`border-t p-2 ${collapsed ? 'md:flex md:flex-col md:items-center md:gap-1 md:px-1' : 'px-3 py-3'}`}
          >
            {collapsed ? (
              <button
                type="button"
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
                  type="button"
                  onClick={() => {
                    logout()
                    void navigate('/login')
                  }}
                  aria-label="Sign out"
                  title="Sign out"
                  className="flex min-h-[44px] min-w-[44px] shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
            <div
              title={
                apiLastChecked
                  ? `API: ${apiHealth} (checked ${apiLastChecked.toLocaleTimeString()})`
                  : `API: ${apiHealth}`
              }
              className="flex items-center gap-1.5"
              role="status"
              aria-label={`API status: ${apiHealth}`}
            >
              <span
                className={cn(
                  'inline-block h-2 w-2 shrink-0 rounded-full',
                  apiHealth === 'connected' && 'bg-emerald-500',
                  apiHealth === 'degraded' && 'bg-amber-500',
                  apiHealth === 'disconnected' && 'bg-red-500',
                )}
              />
              <span className={`text-xs text-muted-foreground ${collapsed ? 'md:hidden' : ''}`}>
                API
              </span>
            </div>
            <span className={`text-xs text-muted-foreground ${collapsed ? 'md:hidden' : ''}`}>
              v0.1.0
            </span>
            <div ref={notifRef} className="relative">
              <button
                type="button"
                onClick={() => setNotifOpen((v) => !v)}
                aria-label={
                  unreadCount > 0
                    ? `${unreadCount} unread notification${unreadCount !== 1 ? 's' : ''}`
                    : 'No unread notifications'
                }
                title="Notifications"
                className="relative flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Bell className="h-4 w-4" />
                {unreadCount > 0 && (
                  <span className="absolute right-1.5 top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
                    {unreadCount > 99 ? '99+' : unreadCount}
                  </span>
                )}
              </button>
              {notifOpen && (
                <div className="absolute bottom-full left-0 z-50 mb-2 w-72 overflow-hidden rounded-lg border bg-card shadow-lg">
                  <div className="flex items-center justify-between border-b px-3 py-2">
                    <span className="text-xs font-semibold">Notifications</span>
                    {unreadCount > 0 && (
                      <button
                        type="button"
                        onClick={() => markAllRead()}
                        className="flex items-center gap-1 text-[10px] text-primary hover:underline"
                      >
                        <Check className="h-3 w-3" />
                        Mark all read
                      </button>
                    )}
                  </div>
                  <div className="max-h-64 overflow-y-auto">
                    {notifications.length === 0 ? (
                      <p className="px-3 py-6 text-center text-xs text-muted-foreground">
                        No notifications yet
                      </p>
                    ) : (
                      notifications.map((n) => (
                        <div
                          key={n.id}
                          className={`border-b px-3 py-2 last:border-b-0 ${!n.read ? 'bg-primary/5' : ''}`}
                        >
                          <p className="text-xs font-medium">{n.title}</p>
                          <p className="mt-0.5 text-[11px] text-muted-foreground">{n.body}</p>
                          <p className="mt-1 text-[10px] text-muted-foreground/60">
                            {n.time.toLocaleTimeString()}
                          </p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={cycle}
              aria-label={`Theme: ${preference}. Click to cycle theme.`}
              title={`Theme: ${preference}`}
              className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
              type="button"
              onClick={() => setShortcutsDialogOpen(true)}
              aria-label="Keyboard shortcuts"
              title="Keyboard shortcuts (?)"
              className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Keyboard className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setCollapsed((v) => !v)}
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              className="hidden min-h-[44px] min-w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:inline-flex"
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
        {apiHealth === 'disconnected' && (
          <div className="flex flex-1 items-center justify-center bg-background/80 backdrop-blur-sm">
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
                <AlertTriangle className="h-6 w-6 text-destructive" />
              </div>
              <h2 className="text-lg font-semibold">API Unavailable</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Cannot connect to the Blackbeard API. Retrying automatically…
              </p>
              <Spinner size="sm" className="mx-auto mt-4 text-muted-foreground" />
            </div>
          </div>
        )}
        {apiHealth !== 'disconnected' && <Outlet />}
      </main>

      <CommandPalette open={cmdPaletteOpen} onOpenChange={setCmdPaletteOpen} />
      <KeyboardShortcutsDialog open={shortcutsDialogOpen} onOpenChange={setShortcutsDialogOpen} />

      {/* ── Onboarding ── */}
      <WelcomeDialog open={showWelcome} onStartTour={handleStartTour} onSkip={handleSkipWelcome} />
      <GuidedTour key={tourKey} active={showTour} onComplete={handleTourComplete} />
    </div>
  )
}
