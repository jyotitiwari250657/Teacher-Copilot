import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, getToken, setToken } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [teacher, setTeacher] = useState(null)
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)

  const loadConfig = useCallback(async () => {
    try {
      setConfig(await api.config())
    } catch {
      /* settings page will show an empty state; not fatal */
    }
  }, [])

  // Restore an existing session on first mount.
  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      if (!getToken()) {
        setLoading(false)
        return
      }
      try {
        const me = await api.me()
        if (!cancelled) {
          setTeacher(me)
          loadConfig()
        }
      } catch {
        setToken(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    bootstrap()
    return () => {
      cancelled = true
    }
  }, [loadConfig])

  // The API client signals an expired token by dispatching this event.
  useEffect(() => {
    const onUnauthorized = () => {
      setTeacher(null)
      setToken(null)
    }
    window.addEventListener('teachercopilot:unauthorized', onUnauthorized)
    return () => window.removeEventListener('teachercopilot:unauthorized', onUnauthorized)
  }, [])

  const login = useCallback(
    async (email, password, remember = true) => {
      const data = await api.login(email, password, remember)
      setToken(data.access_token, remember)
      setTeacher(data.teacher)
      loadConfig()
      return data.teacher
    },
    [loadConfig],
  )

  const logout = useCallback(() => {
    setToken(null)
    setTeacher(null)
  }, [])

  const value = useMemo(
    () => ({ teacher, config, loading, login, logout, setTeacher, refreshConfig: loadConfig }),
    [teacher, config, loading, login, logout, loadConfig],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}