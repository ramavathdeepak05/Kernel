import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { BookOpen, LogOut, RefreshCw } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

interface Course {
  id: string
  code: string
  name: string
  department: string
  semester: string
}

export default function CourseSelectorPage() {
  const navigate = useNavigate()
  const { token, tenantId, user, logout } = useAuthStore()

  const [courses, setCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const headers = {
    Authorization: `Bearer ${token}`,
    'X-Tenant-ID': tenantId ?? '',
  }

  const fetchCourses = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API_BASE}/api/v1/academics/courses?faculty=me`, { headers })
      if (!res.ok) throw new Error('Failed to load courses')
      const data = await res.json()
      setCourses(Array.isArray(data) ? data : data.courses ?? [])
    } catch {
      setError('Could not load courses. Check your connection.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchCourses() }, [])

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh' }}>
      {/* Header */}
      <div style={{
        padding: '14px 20px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>
            {user?.full_name ?? 'Faculty'}
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>Select a course to start attendance</div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={fetchCourses}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', padding: 6 }}
            title="Refresh"
          >
            <RefreshCw size={14} />
          </button>
          <button
            onClick={handleLogout}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', padding: 6 }}
            title="Sign out"
          >
            <LogOut size={14} />
          </button>
        </div>
      </div>

      {/* Course list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {loading && (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)', fontSize: 12 }}>
            Loading courses…
          </div>
        )}
        {!loading && error && (
          <div style={{ color: 'var(--red)', fontSize: 12, textAlign: 'center', padding: 20 }}>{error}</div>
        )}
        {!loading && !error && courses.length === 0 && (
          <div style={{ color: 'var(--text-muted)', fontSize: 12, textAlign: 'center', padding: 40 }}>
            No courses assigned this semester.
          </div>
        )}
        {courses.map((course) => (
          <button
            key={course.id}
            onClick={() => navigate(`/session/${course.id}`, { state: { course } })}
            style={{
              display: 'flex', alignItems: 'center', gap: 14, padding: '14px 16px',
              borderRadius: 10, background: 'var(--bg-card)', border: '1px solid var(--border)',
              textAlign: 'left', transition: 'border-color 0.12s, background 0.12s',
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(29,158,117,0.3)'
              ;(e.currentTarget as HTMLButtonElement).style.background = 'rgba(29,158,117,0.04)'
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border)'
              ;(e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-card)'
            }}
          >
            <div style={{
              width: 38, height: 38, borderRadius: 10,
              background: 'var(--green-bg)', border: '1px solid rgba(29,158,117,0.2)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              <BookOpen size={16} color="var(--green)" />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>
                {course.code} — {course.name}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                {course.department} · {course.semester}
              </div>
            </div>
            <div style={{ fontSize: 10, color: 'var(--green)', fontWeight: 600, flexShrink: 0 }}>
              Start →
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
