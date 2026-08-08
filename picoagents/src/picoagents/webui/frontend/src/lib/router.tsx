/**
 * Minimal hash router. Zero dependencies.
 *
 * Hash routing (#/agents/weather) works with FastAPI's static file mount
 * without an SPA fallback, and gives back/forward, refresh, and deep links.
 */

import {
  createContext,
  useCallback,
  useContext,
  useSyncExternalStore,
} from "react";

function getHashPath(): string {
  const hash = window.location.hash.replace(/^#/, "");
  return hash.startsWith("/") ? hash : `/${hash}`;
}

function subscribe(callback: () => void): () => void {
  window.addEventListener("hashchange", callback);
  return () => window.removeEventListener("hashchange", callback);
}

/** Current path, e.g. "/agents/weather_agent". Re-renders on navigation. */
export function usePath(): string {
  return useSyncExternalStore(subscribe, getHashPath, () => "/");
}

export function navigate(path: string, { replace = false } = {}): void {
  const target = `#${path.startsWith("/") ? path : `/${path}`}`;
  if (replace) {
    window.location.replace(target);
  } else {
    window.location.hash = target.slice(1);
  }
}

/** Split a path into decoded segments: "/agents/a%20b" -> ["agents", "a b"] */
export function segments(path: string): string[] {
  return path
    .split("/")
    .filter(Boolean)
    .map((s) => decodeURIComponent(s));
}

const PathContext = createContext<string>("/");

export function RouterProvider({ children }: { children: React.ReactNode }) {
  const path = usePath();
  return <PathContext.Provider value={path}>{children}</PathContext.Provider>;
}

export function useSegments(): string[] {
  return segments(useContext(PathContext));
}

interface LinkProps extends Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "href"> {
  to: string;
}

export function Link({ to, onClick, children, ...props }: LinkProps) {
  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLAnchorElement>) => {
      onClick?.(e);
    },
    [onClick]
  );
  return (
    <a href={`#${to}`} onClick={handleClick} {...props}>
      {children}
    </a>
  );
}
