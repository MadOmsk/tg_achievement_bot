import { useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { UI_CONFIG } from "../../constants";
import "./PullToRefresh.css";

/** Mobile-style pull-to-refresh at the top of the page scroll. */
export function usePullToRefresh(onRefresh: () => void | Promise<void>) {
  const [pull, setPull] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const startY = useRef(0);
  const pulling = useRef(false);
  const armed = useRef(false);
  const refresh = useRef(onRefresh);
  refresh.current = onRefresh;

  useEffect(() => {
    const { THRESHOLD, MAX } = UI_CONFIG.PULL_TO_REFRESH;
    const onStart = (event: TouchEvent) => {
      if (document.documentElement.classList.contains("is-sheet-open")) return;
      if (refreshing) return;
      // A layer with a scroll of its own (the game page) is not the page: a
      // drag down inside it scrolls it, it must never start a refresh.
      if ((event.target as Element | null)?.closest?.("[data-no-pull]")) return;
      if (window.scrollY > 1) return;
      startY.current = event.touches[0]?.clientY ?? 0;
      pulling.current = true;
      armed.current = false;
    };
    const onMove = (event: TouchEvent) => {
      if (!pulling.current || refreshing) return;
      if (document.documentElement.classList.contains("is-sheet-open")) {
        pulling.current = false;
        setPull(0);
        return;
      }
      if (window.scrollY > 1) {
        pulling.current = false;
        setPull(0);
        return;
      }
      const y = event.touches[0]?.clientY ?? 0;
      const dy = y - startY.current;
      if (dy <= 0) {
        setPull(0);
        armed.current = false;
        return;
      }
      const next = Math.min(MAX, dy * 0.42);
      setPull(next);
      armed.current = next >= THRESHOLD;
      if (dy > 12) event.preventDefault();
    };
    const onEnd = () => {
      if (!pulling.current) return;
      pulling.current = false;
      if (armed.current) {
        setRefreshing(true);
        setPull(THRESHOLD);
        void Promise.resolve(refresh.current())
          .catch(() => undefined)
          .finally(() => {
            setRefreshing(false);
            setPull(0);
          });
      } else {
        setPull(0);
      }
      armed.current = false;
    };
    document.addEventListener("touchstart", onStart, { passive: true });
    document.addEventListener("touchmove", onMove, { passive: false });
    document.addEventListener("touchend", onEnd);
    document.addEventListener("touchcancel", onEnd);
    return () => {
      document.removeEventListener("touchstart", onStart);
      document.removeEventListener("touchmove", onMove);
      document.removeEventListener("touchend", onEnd);
      document.removeEventListener("touchcancel", onEnd);
    };
  }, [refreshing]);

  const indicator =
    (pull > 0 || refreshing) && createPortal(
          <div
            className={[
              "pull-refresh",
              refreshing ? "is-busy" : "",
              pull >= 68 && !refreshing ? "is-armed" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            style={
              {
                height: Math.max(pull, refreshing ? 52 : 0),
                ["--pull-turn"]: String(Math.min(1, pull / 68)),
              } as CSSProperties
            }
            aria-hidden
          >
            <span className="pull-refresh-spinner" />
          </div>,
          document.body,
        );

  return { indicator, refreshing };
}
