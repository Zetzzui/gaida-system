/**
 * usePWA.js
 * ─────────────────────────────────────────────────────────────
 * React hook that handles all PWA logic for GAIDA:
 *   - Service worker registration
 *   - Install prompt (Add to Home Screen)
 *   - Online/offline status
 *   - Offline message queue sync listener
 *
 * Usage:
 *   const { isOnline, isInstallable, installApp, queuedMessages } = usePWA();
 * ─────────────────────────────────────────────────────────────
 */

import { useState, useEffect, useCallback, useRef } from "react";

export function usePWA({ onQueuedMessageSent } = {}) {
  const [isOnline, setIsOnline]           = useState(navigator.onLine);
  const [isInstallable, setIsInstallable] = useState(false);
  const [isInstalled, setIsInstalled]     = useState(false);
  const [swReady, setSwReady]             = useState(false);
  const [queuedMessages, setQueuedMessages] = useState([]);

  const deferredPromptRef = useRef(null);

  // ── Register service worker ─────────────────────────────────
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .then((registration) => {
        console.log("[GAIDA PWA] Service worker registered:", registration.scope);
        setSwReady(true);

        // Trigger background sync when back online
        window.addEventListener("online", () => {
          // Background Sync (Chrome / Edge / Android)
          if ("sync" in registration) {
            registration.sync
              .register("gaida-sync-messages")
              .catch((err) => console.warn("[GAIDA PWA] Sync registration failed:", err));
          }
          // Fallback for browsers without Background Sync (iOS Safari):
          // ask the service worker to flush the queue right away.
          navigator.serviceWorker.controller?.postMessage({ type: "FLUSH_QUEUE" });
        });
      })
      .catch((err) => {
        console.error("[GAIDA PWA] Service worker registration failed:", err);
      });
  }, []);

  // ── Listen for messages FROM service worker ─────────────────
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    const handleMessage = (event) => {
      const { type, payload } = event.data || {};

      if (type === "MESSAGE_QUEUED") {
        // A message was saved to the offline queue
        setQueuedMessages((prev) => [...prev, payload]);
      }

      if (type === "QUEUED_MESSAGE_SENT") {
        // A queued message was successfully sent after reconnecting.
        // Compare by value (JSON) — the original and this payload are
        // separate object instances, so reference equality never matches.
        setQueuedMessages((prev) =>
          prev.filter(
            (m) => JSON.stringify(m) !== JSON.stringify(payload.original || {})
          )
        );
        if (onQueuedMessageSent) {
          onQueuedMessageSent(payload);
        }
      }
    };

    navigator.serviceWorker.addEventListener("message", handleMessage);
    return () => navigator.serviceWorker.removeEventListener("message", handleMessage);
  }, [onQueuedMessageSent]);

  // ── Online / Offline status ─────────────────────────────────
  useEffect(() => {
    const handleOnline  = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener("online",  handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online",  handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  // ── Install prompt ──────────────────────────────────────────
  useEffect(() => {
    const handleBeforeInstallPrompt = (e) => {
      e.preventDefault();
      deferredPromptRef.current = e;
      setIsInstallable(true);
    };

    const handleAppInstalled = () => {
      setIsInstalled(true);
      setIsInstallable(false);
      deferredPromptRef.current = null;
      console.log("[GAIDA PWA] App installed to home screen.");
    };

    window.addEventListener("beforeinstallprompt", handleBeforeInstallPrompt);
    window.addEventListener("appinstalled", handleAppInstalled);

    // Check if already installed (standalone mode)
    if (window.matchMedia("(display-mode: standalone)").matches) {
      setIsInstalled(true);
    }

    return () => {
      window.removeEventListener("beforeinstallprompt", handleBeforeInstallPrompt);
      window.removeEventListener("appinstalled", handleAppInstalled);
    };
  }, []);

  // ── Trigger install prompt ──────────────────────────────────
  const installApp = useCallback(async () => {
    if (!deferredPromptRef.current) return false;
    deferredPromptRef.current.prompt();
    const { outcome } = await deferredPromptRef.current.userChoice;
    deferredPromptRef.current = null;
    setIsInstallable(false);
    return outcome === "accepted";
  }, []);

  return {
    isOnline,
    isOffline: !isOnline,
    isInstallable,
    isInstalled,
    swReady,
    installApp,
    queuedMessages,
    queuedCount: queuedMessages.length,
  };
}