import { Suspense, lazy } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
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
        </Route>
      </Routes>
    </Suspense>
  )
}

export default App
