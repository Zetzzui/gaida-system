/**
 * sw.js — GAIDA Service Worker
 * ─────────────────────────────────────────────────────────────
 * Handles:
 *   1. App shell caching        → Chat UI works offline
 *   2. Past messages caching    → View previous conversations offline
 *   3. Offline message queue    → Messages sent when back online
 * ─────────────────────────────────────────────────────────────
 */

const CACHE_VERSION = "gaida-v3";
const SHELL_CACHE   = `${CACHE_VERSION}-shell`;
const DATA_CACHE    = `${CACHE_VERSION}-data`;
const QUEUE_STORE   = "gaida-offline-queue";


// Required by vite-plugin-pwa injectManifest strategy
const WB_MANIFEST = self.__WB_MANIFEST || [];

// ── App Shell — files to cache on install ────────────────────
const APP_SHELL_FILES = [
  "/",
  "/index.html",
  "/offline.html",
  "/manifest.json",
  "/favicon.ico",
  "/icons/favicon.svg",
  "/icons/favicon-32x32.png",
  "/icons/icon-192x192.png",
  "/icons/icon-512x512.png",
];

// ── API routes to cache responses from ───────────────────────
const API_CACHE_ROUTES = [
  "/api/session/",
  "/api/counselor/chat/",
  "/api/counselor/alerts",
  "/api/counselor/student-profile/",
];

// ── API routes that should be queued when offline ────────────
const QUEUEABLE_ROUTES = [
  "/virtual-agent",
  "/api/counselor/request-counselor",
  "/api/counselor/takeover",
  "/api/counselor/typing/",
];


// ── Install — cache app shell + precache build assets ─────────
self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);
      console.log("[GAIDA SW] Caching app shell...");
      await cache.addAll(APP_SHELL_FILES);
      // Precache the hashed build assets listed in __WB_MANIFEST so the
      // app is fully usable offline from the very first visit. Failures
      // are tolerated individually so one 404 can't break installation.
      const precacheUrls = (WB_MANIFEST).map((entry) =>
        typeof entry === "string" ? entry : entry.url
      );
      if (precacheUrls.length) {
        await Promise.allSettled(precacheUrls.map((url) => cache.add(url)));
      }
    })()
  );
  self.skipWaiting();
});


// ═════════════════════════════════════════════════════════════
// ACTIVATE — clean up old caches
// ═════════════════════════════════════════════════════════════
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith("gaida-") && key !== SHELL_CACHE && key !== DATA_CACHE)
          .map((key) => {
            console.log("[GAIDA SW] Removing old cache:", key);
            return caches.delete(key);
          })
      )
    )
  );
  self.clients.claim();
});


// ═════════════════════════════════════════════════════════════
// FETCH — intercept all requests
// ═════════════════════════════════════════════════════════════
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Engage the SW for:
  //   • same-origin requests (app shell, JS/CSS assets, navigation)
  //   • GAIDA backend API calls, matched by PATHNAME so it works no
  //     matter where the backend is hosted (localhost, Render, etc.)
  // Everything else (foreign origins like Google scripts, fonts, Supabase)
  // passes through untouched — never cache-first'd.
  const isSameOrigin = url.origin === self.location.origin;
  const isApiRoute   = API_CACHE_ROUTES.some((route) => url.pathname.includes(route));
  const isQueueable  = QUEUEABLE_ROUTES.some((route) => url.pathname.includes(route));
  if (!isSameOrigin && !isApiRoute && !isQueueable) return;

  // Skip non-GET requests that aren't queueable API calls
  if (request.method === "POST") {
    if (isQueueable) {
      event.respondWith(handleQueueablePost(request));
      return;
    }
    return;
  }

  if (request.method !== "GET") return;

  // API data routes — network first, cache fallback
  if (isApiRoute) {
    event.respondWith(networkFirstWithCache(request));
    return;
  }

  // App shell routes — cache first, network fallback
  event.respondWith(cacheFirstWithNetwork(request));
});


// ═════════════════════════════════════════════════════════════
// STRATEGY: Cache First (App Shell)
// Serve from cache immediately. If missing, fetch & cache it.
// ═════════════════════════════════════════════════════════════
async function cacheFirstWithNetwork(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response && response.status === 200) {
      const cache = await caches.open(SHELL_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    // Offline fallback for navigation requests
    if (request.mode === "navigate") {
      const fallback = await caches.match("/offline.html");
      if (fallback) return fallback;
    }
    return new Response("Offline", { status: 503, statusText: "Service Unavailable" });
  }
}


// ═════════════════════════════════════════════════════════════
// STRATEGY: Network First (API Data / Chat History)
// Always try network. On failure, serve cached version.
// ═════════════════════════════════════════════════════════════
async function networkFirstWithCache(request) {
  try {
    const response = await fetch(request);
    if (response && response.status === 200) {
      const cache = await caches.open(DATA_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response(
      JSON.stringify({ error: "offline", message: "You are offline. Showing cached data." }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
}


// ═════════════════════════════════════════════════════════════
// STRATEGY: Queue POST (Offline Message Queue)
// If online → send immediately.
// If offline → save to IndexedDB queue, return optimistic response.
// ═════════════════════════════════════════════════════════════
async function handleQueueablePost(request) {
  try {
    // Try sending immediately if online
    const response = await fetch(request.clone());
    return response;
  } catch {
    // Offline — queue the message
    try {
      const body = await request.clone().json();
      await addToQueue({
        url: request.url,
        method: request.method,
        headers: Object.fromEntries(request.headers.entries()),
        body,
        timestamp: Date.now(),
        id: crypto.randomUUID(),
      });

      // Notify all open tabs that a message was queued
      const clients = await self.clients.matchAll({ type: "window" });
      clients.forEach((client) =>
        client.postMessage({ type: "MESSAGE_QUEUED", payload: body })
      );

      // Return optimistic offline response as NDJSON — matches the
      // /virtual-agent/stream format the chat frontend consumes.
      return new Response(
        JSON.stringify({
          type: "done",
          result: {
            session_id: null,
            response: "It looks like you're offline right now. I've saved your message and will respond as soon as you're back online. 💙",
          },
        }) + "\n",
        {
          status: 200,
          headers: { "Content-Type": "application/x-ndjson" },
        }
      );
    } catch (queueError) {
      console.error("[GAIDA SW] Failed to queue message:", queueError);
      return new Response(
        JSON.stringify({ error: "offline", message: "Failed to queue message." }),
        { status: 503, headers: { "Content-Type": "application/json" } }
      );
    }
  }
}


// ═════════════════════════════════════════════════════════════
// SYNC — flush offline queue when back online
// ═════════════════════════════════════════════════════════════
self.addEventListener("sync", (event) => {
  if (event.tag === "gaida-sync-messages") {
    event.waitUntil(flushMessageQueue());
  }
});


// ═════════════════════════════════════════════════════════════
// FALLBACK FLUSH — browsers without Background Sync (iOS Safari)
// The page posts a FLUSH_QUEUE message when it reconnects.
// ═════════════════════════════════════════════════════════════
self.addEventListener("message", (event) => {
  const data = event.data || {};
  if (data.type === "FLUSH_QUEUE" && typeof event.waitUntil === "function") {
    event.waitUntil(flushMessageQueue());
  }
});

async function flushMessageQueue() {
  const queue = await getQueue();
  if (!queue.length) return;

  console.log(`[GAIDA SW] Flushing ${queue.length} queued messages...`);

  for (const item of queue) {
    try {
      const response = await fetch(item.url, {
        method: item.method,
        headers: { ...item.headers, "Content-Type": "application/json" },
        body: JSON.stringify(item.body),
      });

      if (response.ok) {
        await removeFromQueue(item.id);
        // The stream endpoint replies with NDJSON — grab the final done.result.
        const result = await readStreamDone(response);

        // Notify tabs that the queued message was sent and got a response
        const clients = await self.clients.matchAll({ type: "window" });
        clients.forEach((client) =>
          client.postMessage({
            type: "QUEUED_MESSAGE_SENT",
            payload: {
              original: item.body,
              response: { response: result?.response || item.body?.message },
            },
          })
        );
        console.log("[GAIDA SW] Queued message sent:", item.id);
      }
    } catch (err) {
      console.error("[GAIDA SW] Failed to flush message:", item.id, err);
    }
  }
}


// Reads an NDJSON stream and returns the final "done" event's result (or null).
async function readStreamDone(response) {
  try {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let result = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop(); // keep incomplete line for the next chunk

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          const event = JSON.parse(trimmed);
          if (event.type === "done") result = event.result || null;
        } catch { /* skip malformed line */ }
      }
    }
    return result;
  } catch (err) {
    console.error("[GAIDA SW] Failed to read stream:", err);
    return null;
  }
}


// ═════════════════════════════════════════════════════════════
// INDEXEDDB QUEUE HELPERS
// ═════════════════════════════════════════════════════════════
function openQueueDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(QUEUE_STORE, 1);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains("messages")) {
        db.createObjectStore("messages", { keyPath: "id" });
      }
    };
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror = (e) => reject(e.target.error);
  });
}

async function addToQueue(item) {
  const db = await openQueueDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("messages", "readwrite");
    tx.objectStore("messages").add(item);
    tx.oncomplete = resolve;
    tx.onerror = (e) => reject(e.target.error);
  });
}

async function getQueue() {
  const db = await openQueueDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("messages", "readonly");
    const req = tx.objectStore("messages").getAll();
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror = (e) => reject(e.target.error);
  });
}

async function removeFromQueue(id) {
  const db = await openQueueDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("messages", "readwrite");
    tx.objectStore("messages").delete(id);
    tx.oncomplete = resolve;
    tx.onerror = (e) => reject(e.target.error);
  });
}