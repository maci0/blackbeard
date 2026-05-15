import { Suspense, lazy } from 'react'
import { Routes, Route, Navigate, Link } from 'react-router-dom'
import Layout from './components/Layout'
import { ErrorBoundary } from './components/ui/ErrorBoundary'
import { Spinner } from './components/ui/Spinner'

const Studio = lazy(() => import('./pages/Studio'))
const Resources = lazy(() => import('./pages/Resources'))
const ResourceDetail = lazy(() => import('./pages/ResourceDetail'))
const Executions = lazy(() => import('./pages/Executions'))
const ExecutionDetail = lazy(() => import('./pages/ExecutionDetail'))
const Models = lazy(() => import('./pages/Models'))
const Tools = lazy(() => import('./pages/Tools'))

function App() {
  return (
    <ErrorBoundary>
      <Suspense
        fallback={
          <div className="flex h-screen items-center justify-center">
            <Spinner size="lg" />
          </div>
        }
      >
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/studio" replace />} />
            <Route path="studio" element={<Studio />} />
            <Route path="resources" element={<Resources />} />
            <Route path="resources/:kindPlural/:name" element={<ResourceDetail />} />
            <Route path="executions" element={<Executions />} />
            <Route path="executions/:id" element={<ExecutionDetail />} />
            <Route path="models" element={<Models />} />
            <Route path="tools" element={<Tools />} />
            <Route
              path="*"
              element={
                <div className="flex flex-1 items-center justify-center">
                  <div className="text-center">
                    <p
                      className="mb-2 text-6xl font-bold text-muted-foreground/20"
                      aria-hidden="true"
                    >
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
              }
            />
          </Route>
        </Routes>
      </Suspense>
    </ErrorBoundary>
  )
}

export default App
