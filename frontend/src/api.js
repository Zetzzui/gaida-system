import { BACKEND_URL } from './config'

// Bearer-token fetch wrapper.
//
// - Attaches `Authorization: Bearer <token>` from the active login
//   (student or counselor) to every request, except login/consent/health
//   endpoints that are deliberately public.
// - Forwards 401 responses to the portal by clearing stored auth state so
//   the route guards bounce the user back to login.
//
// Usage:
//   apiFetch('/api/counselor/alerts')                       // token from localStorage
//   apiFetch(`${BACKEND}/virtual-agent/stream`, { ... })    // absolute URL ok
//   apiFetch('/api/research/gad7', {...}, explicitToken)    // caller-supplied token
export function getAuthToken() {
  return localStorage.getItem('session_token') || localStorage.getItem('counselor_token') || null
}

// Purge sensitive data the service worker persisted locally (chat-history
// cache + offline message queue). Called on logout / session end / 401 so
// nothing sensitive outlives the session on disk.
export async function clearSensitiveLocalData() {
  try {
    if ('caches' in window && typeof caches.keys === 'function') {
      const keys = await caches.keys()
      await Promise.all(keys.filter((k) => k.includes('-data')).map((k) => caches.delete(k)))
    }
  } catch { /* non-secure context or unsupported cache API — ignore */ }
  try {
    if ('indexedDB' in window) {
      await new Promise((resolve) => {
        const req = indexedDB.deleteDatabase('gaida-offline-queue')
        req.onsuccess = req.onerror = req.onblocked = () => resolve()
      })
    }
  } catch { /* ignore */ }
  try {
    navigator.serviceWorker?.controller?.postMessage({ type: 'LOGOUT' })
  } catch { /* ignore */ }
}

export function clearAuth() {
  localStorage.removeItem('session_token')
  localStorage.removeItem('counselor_token')
  localStorage.removeItem('counselorData')
  localStorage.removeItem('student_id')
  clearSensitiveLocalData()
}

export async function apiFetch(input, options = {}, tokenOverride = null) {
  const isAbsolute = typeof input === 'string' && /^https?:\/\//.test(input)
  const url = isAbsolute ? input : `${BACKEND_URL}${input}`

  const headers = new Headers(options.headers || {})
  const token = tokenOverride || getAuthToken()
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const body = options.body
  if (
    body != null &&
    typeof body === 'string' &&
    !(options.headers instanceof Headers ? options.headers.has('Content-Type') : headers.has('Content-Type'))
  ) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(url, { ...options, headers })

  if (response.status === 401 && !tokenOverride) {
    clearAuth()
    if (window.location.pathname !== '/') {
      window.location.href = '/'
    }
  }

  return response
}

export default apiFetch