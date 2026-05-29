import { Suspense, lazy, useEffect } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { Routes, Route, Navigate, Link, useLocation } from 'react-router-dom'
import Layout from '@/components/Layout'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'
import { OnboardingWizard } from '@/components/onboarding/OnboardingWizard'
import { useDocumentTitle, useOnboarding } from '@/hooks'
import { Spinner } from '@/components/ui/Spinner'
import { ToastContainer } from '@/components/ui/Toast'
import { useAuthStore } from '@/stores/authStore'
import { api } from '@/api/client'

const Dashboard = lazy(() => import('@/pages/Dashboard'))
const Studio = lazy(() => import('@/pages/Studio'))
const Resources = lazy(() => import('@/pages/Resources'))
const ResourceDetail = lazy(() => import('@/pages/ResourceDetail'))
const Executions = lazy(() => import('@/pages/Executions'))
const ExecutionDetail = lazy(() => import('@/pages/ExecutionDetail'))
const ExecutionCompare = lazy(() => import('@/pages/ExecutionCompare'))
const Models = lazy(() => import('@/pages/Models'))
const Chat = lazy(() => import('@/pages/Chat'))
const Tools = lazy(() => import('@/pages/Tools'))
const KnowledgeSources = lazy(() => import('@/pages/KnowledgeSources'))
const Login = lazy(() => import('@/pages/Login'))
const Register = lazy(() => import('@/pages/Register'))
const Users = lazy(() => import('@/pages/Users'))
const Roles = lazy(() => import('@/pages/Roles'))
const Marketplace = lazy(() => import('@/pages/Marketplace'))
const Automations = lazy(() => import('@/pages/Automations'))
const Webhooks = lazy(() => import('@/pages/Webhooks'))
const AuditLogs = lazy(() => import('@/pages/AuditLogs'))
const Settings = lazy(() => import('@/pages/Settings'))
const GuardrailPlayground = lazy(() => import('@/pages/GuardrailPlayground'))
const Credentials = lazy(() => import('@/pages/Credentials'))

const PUBLIC_PATHS = new Set(['/login', '/register'])

function AuthGuard({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  const location = useLocation()

  if (!token && !PUBLIC_PATHS.has(location.pathname)) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }

  return <>{children}</>
}

function NotFound() {
  useDocumentTitle('Page not found')
  return (
    <div className="flex flex-1 items-center justify-center">
      <div className="text-center">
        <p className="mb-2 text-6xl font-bold text-muted-foreground/20" aria-hidden="true">
          404
        </p>
        <h1 className="mb-1 text-lg font-semibold">Page not found</h1>
        <p className="mb-4 text-sm text-muted-foreground">
          The page you're looking for doesn't exist or may have been moved.
        </p>
        <div className="flex items-center justify-center gap-3">
          <Link
            to="/studio"
            className="inline-flex rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            Go to Studio
          </Link>
          <Link
            to="/resources"
            className="inline-flex rounded-md border px-4 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            Browse Resources
          </Link>
        </div>
      </div>
    </div>
  )
}

function App() {
  const { hydrate, token, fetchMe, setSessionExpired } = useAuthStore(
    useShallow((s) => ({
      hydrate: s.hydrate,
      token: s.token,
      fetchMe: s.fetchMe,
      setSessionExpired: s.setSessionExpired,
    })),
  )
  const { showOnboarding, dismissOnboarding } = useOnboarding()

  useEffect(() => {
    hydrate()
    api.onUnauthorized(() => {
      setSessionExpired(true)
    })
  }, [hydrate, setSessionExpired])

  useEffect(() => {
    if (token) {
      void fetchMe()
    }
  }, [token, fetchMe])

  return (
    <>
      {token && showOnboarding && <OnboardingWizard onDismiss={dismissOnboarding} />}
      <ErrorBoundary>
        <Suspense
          fallback={
            <div className="flex h-screen items-center justify-center">
              <Spinner size="lg" label="Loading page" />
            </div>
          }
        >
          <AuthGuard>
            <Routes>
              {/* Public routes (no Layout) */}
              <Route path="login" element={<Login />} />
              <Route path="register" element={<Register />} />

              {/* Authenticated routes (with Layout) */}
              <Route path="/" element={<Layout />}>
                <Route index element={<Navigate to="/dashboard" replace />} />
                <Route path="dashboard" element={<Dashboard />} />
                <Route path="studio" element={<Studio />} />
                <Route path="resources" element={<Resources />} />
                <Route path="resources/:kindPlural/:name" element={<ResourceDetail />} />
                <Route path="executions" element={<Executions />} />
                <Route path="executions/compare" element={<ExecutionCompare />} />
                <Route path="executions/:id" element={<ExecutionDetail />} />
                <Route path="models" element={<Models />} />
                <Route path="chat" element={<Chat />} />
                <Route path="tools" element={<Tools />} />
                <Route path="knowledge" element={<KnowledgeSources />} />
                <Route path="users" element={<Users />} />
                <Route path="roles" element={<Roles />} />
                <Route path="marketplace" element={<Marketplace />} />
                <Route path="automations" element={<Automations />} />
                <Route path="webhooks" element={<Webhooks />} />
                <Route path="audit-logs" element={<AuditLogs />} />
                <Route path="credentials" element={<Credentials />} />
                <Route path="guardrails/playground" element={<GuardrailPlayground />} />
                <Route path="settings" element={<Settings />} />
                <Route path="*" element={<NotFound />} />
              </Route>
            </Routes>
          </AuthGuard>
        </Suspense>
      </ErrorBoundary>
      <ToastContainer />
    </>
  )
}

export default App
