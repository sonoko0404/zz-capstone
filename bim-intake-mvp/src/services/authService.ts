import type { UserSession } from '../types/intake'

const SESSION_KEY = 'bim-intake-session'

function normalizeSession(value: UserSession, fallbackRole: UserSession['role'] = 'user'): UserSession {
  return {
    email: value.email,
    displayName: value.displayName || value.email.split('@')[0],
    loginAt: value.loginAt || new Date().toISOString(),
    role: value.role || fallbackRole,
  }
}

export function getSession(): UserSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY)
    return raw ? normalizeSession(JSON.parse(raw) as UserSession) : null
  } catch {
    return null
  }
}

export function saveSession(session: UserSession) {
  window.localStorage.setItem(SESSION_KEY, JSON.stringify(normalizeSession(session)))
}

export function clearSession() {
  window.localStorage.removeItem(SESSION_KEY)
}

export async function loginWithEmail(
  email: string,
  role: UserSession['role'] = 'user',
): Promise<UserSession> {
  const normalizedEmail = email.trim().toLowerCase()
  const apiUrl = import.meta.env.VITE_AUTH_API_URL?.trim()

  if (apiUrl) {
    const response = await fetch(apiUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: normalizedEmail, role }),
    })

    if (!response.ok) {
      throw new Error(`Auth API failed with ${response.status}`)
    }

    const session = normalizeSession((await response.json()) as UserSession, role)
    saveSession(session)
    return session
  }

  await new Promise((resolve) => window.setTimeout(resolve, 420))

  const session = normalizeSession({
    email: normalizedEmail,
    displayName: normalizedEmail.split('@')[0],
    loginAt: new Date().toISOString(),
    role,
  })
  saveSession(session)
  return session
}
