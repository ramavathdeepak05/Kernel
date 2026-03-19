import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { useAuthStore, type AuthState } from './store/authStore'
import LoginPage from './pages/LoginPage'
import CourseSelectorPage from './pages/CourseSelectorPage'
import SessionPage from './pages/SessionPage'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s: AuthState) => s.token)
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <CourseSelectorPage />
            </RequireAuth>
          }
        />
        <Route
          path="/session/:courseId"
          element={
            <RequireAuth>
              <SessionPage />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
