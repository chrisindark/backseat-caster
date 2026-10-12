/**
 * Browser history and URL query parameter synchronization utilities for modals.
 * Enables persistent modal state across page reloads and browser Back/Forward navigation.
 */

export function getQueryParam(key: string): string | null {
  if (typeof window === "undefined") return null;
  const params = new URLSearchParams(window.location.search);
  return params.get(key);
}

export function getAllQueryParams(): URLSearchParams {
  if (typeof window === "undefined") return new URLSearchParams();
  return new URLSearchParams(window.location.search);
}

export function setQueryParams(
  params: Record<string, string | null | undefined>,
  options: { replace?: boolean } = {}
) {
  if (typeof window === "undefined") return;

  const url = new URL(window.location.href);
  let hasChanges = false;

  Object.entries(params).forEach(([key, value]) => {
    const existing = url.searchParams.get(key);
    if (value === null || value === undefined || value === "") {
      if (url.searchParams.has(key)) {
        url.searchParams.delete(key);
        hasChanges = true;
      }
    } else if (existing !== value) {
      url.searchParams.set(key, value);
      hasChanges = true;
    }
  });

  if (!hasChanges) return;

  const queryString = url.searchParams.toString();
  const nextPath = url.pathname + (queryString ? `?${queryString}` : "") + url.hash;

  if (options.replace) {
    window.history.replaceState({ ...window.history.state }, "", nextPath);
  } else {
    window.history.pushState({ ...window.history.state }, "", nextPath);
  }
}

export function removeQueryParams(keys: string[], options: { replace?: boolean } = {}) {
  const updates: Record<string, null> = {};
  keys.forEach((k) => {
    updates[k] = null;
  });
  setQueryParams(updates, options);
}
