const SESSION_KEY = 'meditrack_user'

export function getSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    if (!raw || raw === 'undefined' || raw === 'null') return null
    const user = JSON.parse(raw)
    return user && typeof user === 'object' ? user : null
  } catch {
    return null
  }
}

export function setSession(u) {
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify(u))
  } catch {
    // Storage may be unavailable (private mode / embedded webview); the
    // in-memory user state still keeps the current session working.
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(SESSION_KEY)
  } catch {
    // ignore
  }
}
