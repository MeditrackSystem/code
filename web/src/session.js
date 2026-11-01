const SESSION_KEY = 'meditrack_user'

export function getSession() {
  try { return JSON.parse(localStorage.getItem(SESSION_KEY)) } catch { return null }
}
export function setSession(u) { localStorage.setItem(SESSION_KEY, JSON.stringify(u)) }
export function clearSession() { localStorage.removeItem(SESSION_KEY) }
