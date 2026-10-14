"use client";

import { usePathname } from "next/navigation";
import { Suspense, useEffect, useRef } from "react";

/**
 * MediaPlaybackCoordinator provides application-wide audio/video playback coordination:
 * 1. Pauses all playing media elements upon client-side page navigation (usePathname).
 * 2. Enforces single-media playback: when one video/audio starts playing, all other
 *    media elements are automatically paused (unless explicitly grouped via `data-sync-group`).
 * 3. Disconnect safety: Uses a MutationObserver to instantly pause any HTMLMediaElement
 *    that is unmounted/removed from the DOM by React, preventing orphaned background audio playback.
 */
function MediaPlaybackCoordinatorInner() {
  const pathname = usePathname();
  const prevPathnameRef = useRef<string>(pathname);

  // 1. Pause all active media on client-side route transitions
  useEffect(() => {
    if (prevPathnameRef.current !== pathname) {
      prevPathnameRef.current = pathname;
      document.querySelectorAll<HTMLMediaElement>("video, audio").forEach((media) => {
        try {
          if (!media.paused) {
            media.pause();
          }
        } catch {
          // Ignore any browser abort errors
        }
      });
    }
  }, [pathname]);

  // 2. Global single-playback enforcement & MutationObserver cleanup
  useEffect(() => {
    // Intercept 'play' events globally during the capture phase
    const handleGlobalPlay = (event: Event) => {
      const target = event.target;
      if (!(target instanceof HTMLMediaElement)) return;

      const syncGroup = target.getAttribute("data-sync-group");

      document.querySelectorAll<HTMLMediaElement>("video, audio").forEach((media) => {
        if (media === target) return;

        // Allow synchronized dual playback if sharing the same non-empty sync group (e.g. comparison view)
        if (syncGroup && media.getAttribute("data-sync-group") === syncGroup) {
          return;
        }

        try {
          if (!media.paused) {
            media.pause();
          }
        } catch {
          // Ignore any browser abort errors
        }
      });
    };

    window.addEventListener("play", handleGlobalPlay, true);

    // Safely pause media elements when detached from the DOM tree
    const pauseMediaInTree = (node: Node) => {
      if (node instanceof HTMLMediaElement) {
        try {
          node.pause();
        } catch {}
      } else if (node instanceof Element) {
        node.querySelectorAll<HTMLMediaElement>("video, audio").forEach((media) => {
          try {
            media.pause();
          } catch {}
        });
      }
    };

    // MutationObserver to catch any React unmount or DOM node removal
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        mutation.removedNodes.forEach((node) => {
          pauseMediaInTree(node);
        });
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
    });

    // Pause on pagehide / tab close
    const handlePageHide = () => {
      document.querySelectorAll<HTMLMediaElement>("video, audio").forEach((media) => {
        try {
          if (!media.paused) {
            media.pause();
          }
        } catch {}
      });
    };
    window.addEventListener("pagehide", handlePageHide);

    return () => {
      window.removeEventListener("play", handleGlobalPlay, true);
      window.removeEventListener("pagehide", handlePageHide);
      observer.disconnect();
    };
  }, []);

  return null;
}

export function MediaPlaybackCoordinator() {
  return (
    <Suspense fallback={null}>
      <MediaPlaybackCoordinatorInner />
    </Suspense>
  );
}
