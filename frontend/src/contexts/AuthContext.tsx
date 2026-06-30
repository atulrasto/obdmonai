import { createContext, useContext, useState, type ReactNode } from 'react'

interface JwtPayload {
  sub: string
  client_id: string
  role: string
  exp: number
}

function parseToken(token: string): JwtPayload | null {
  try {
    const payload = token.split('.')[1]
    return JSON.parse(atob(payload)) as JwtPayload
  } catch {
    return null
  }
}

interface AuthState {
  token: string | null
  clientId: string | null
  role: string | null
  setToken: (token: string | null) => void
  logout: () => void
}

const AuthContext = createContext<AuthState | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(
    () => localStorage.getItem('token'),
  )

  const parsed = token ? parseToken(token) : null

  function setToken(t: string | null) {
    if (t) {
      localStorage.setItem('token', t)
    } else {
      localStorage.removeItem('token')
    }
    setTokenState(t)
  }

  function logout() {
    setToken(null)
  }

  return (
    <AuthContext.Provider
      value={{
        token,
        clientId: parsed?.client_id ?? null,
        role: parsed?.role ?? null,
        setToken,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
