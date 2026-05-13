import { Suspense, lazy } from 'react'
import { Routes, Route, Navigate, Link } from 'react-router-dom'
import Layout from './components/Layout'
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
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-screen">
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
              <div className="flex-1 flex items-center justify-center">
                <div className="text-center">
                  <p className="text-6xl font-bold text-muted-foreground/20 mb-2" aria-hidden="true">404</p>
                  <h1 className="text-lg font-semibold mb-1">Page not found</h1>
                  <p className="text-sm text-muted-foreground mb-4">
                    The page you're looking for doesn't exist or may have been moved.
                  </p>
                  <div className="flex items-center gap-3 justify-center">
                    <Link
                      to="/studio"
                      className="inline-flex px-4 py-2 text-sm bg-primary text-primary-foreground rounded-md hover:opacity-90 transition-opacity"
                    >
                      Go to Studio
                    </Link>
                    <Link
                      to="/resources"
                      className="inline-flex px-4 py-2 text-sm border rounded-md hover:bg-accent transition-colors"
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
  )
}

export default App
