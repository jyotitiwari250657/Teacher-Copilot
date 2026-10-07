import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { ToastProvider } from './components/Toast'
import Layout from './components/Layout'
import { Spinner } from './components/ui'

import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Classes from './pages/Classes'
import LessonPlanner from './pages/LessonPlanner'
import Grading from './pages/Grading'
import Differentiation from './pages/Differentiation'
import ParentUpdates from './pages/ParentUpdates'
import Workflow from './pages/Workflow'
import Settings from './pages/Settings'

function FullPageLoader() {
  return (
    <div className="grid min-h-screen place-items-center bg-ink-50">
      <div className="flex flex-col items-center gap-3 text-ink-500">
        <Spinner size={26} />
        <p className="text-sm">Loading TeacherCopilot…</p>
      </div>
    </div>
  )
}

function RequireAuth({ children }) {
  const { teacher, loading } = useAuth()
  if (loading) return <FullPageLoader />
  if (!teacher) return <Navigate to="/login" replace />
  return children
}

function Shell() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/classes" element={<Classes />} />
        <Route path="/lessons" element={<LessonPlanner />} />
        <Route path="/grading" element={<Grading />} />
        <Route path="/differentiation" element={<Differentiation />} />
        <Route path="/parent-updates" element={<ParentUpdates />} />
        <Route path="/workflow" element={<Workflow />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <Shell />
      </ToastProvider>
    </AuthProvider>
  )
}