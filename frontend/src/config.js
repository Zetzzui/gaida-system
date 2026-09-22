// If VITE_BACKEND_URL isn't set, fall back to whatever host the page itself
// was loaded from (same hostname, port 8000). That makes local LAN testing
// from a phone work automatically: loading the app at http://192.168.x.x:5173
// makes it call http://192.168.x.x:8000, instead of a hardcoded "localhost"
// that would only ever mean the phone itself.
export const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL || `http://${window.location.hostname}:8000`