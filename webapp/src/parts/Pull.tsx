import { useEffect, useRef, useState } from "react";
import { UI_CONFIG } from "../core/constants";
import { tick } from "../core/haptic";
import { Spinner } from "../ui/Controls";

const { THRESHOLD, MAX } = UI_CONFIG.PULL_TO_REFRESH;

/** Pull the list down from its top to ask again. Put it first in the
 * scrolling element; it listens on that element's touches. */
export function Pull({ onRefresh }: { onRefresh: () => Promise<unknown> | void }) {
  const holder = useRef<HTMLDivElement>(null);
  const [pull, setPull] = useState(0);
  const [busy, setBusy] = useState(false);
  const refresh = useRef(onRefresh);
  refresh.current = onRefresh;

  useEffect(() => {
    const scroller = holder.current?.closest<HTMLElement>("[data-scroll], .tab, .page-scroll");
    if (!scroller) return;
    let startY: number | null = null;
    let current = 0;
    let armed = false;
    const down = (e: TouchEvent) => {
      startY = scroller.scrollTop <= 0 ? e.touches[0].clientY : null;
    };
    const move = (e: TouchEvent) => {
      if (startY === null) return;
      const dy = e.touches[0].clientY - startY;
      if (dy <= 0) {
        current = 0;
        setPull(0);
        return;
      }
      current = Math.min(MAX, dy * 0.5);
      if (current >= THRESHOLD && !armed) {
        armed = true;
        tick();
      }
      if (current < THRESHOLD) armed = false;
      setPull(current);
    };
    const up = () => {
      if (startY === null) return;
      startY = null;
      if (current >= THRESHOLD) {
        setBusy(true);
        setPull(THRESHOLD * 0.75);
        Promise.resolve(refresh.current()).finally(() => {
          setBusy(false);
          setPull(0);
        });
      } else {
        setPull(0);
      }
      current = 0;
      armed = false;
    };
    scroller.addEventListener("touchstart", down, { passive: true });
    scroller.addEventListener("touchmove", move, { passive: true });
    scroller.addEventListener("touchend", up);
    return () => {
      scroller.removeEventListener("touchstart", down);
      scroller.removeEventListener("touchmove", move);
      scroller.removeEventListener("touchend", up);
    };
  }, []);

  return (
    <div className="pull" ref={holder} style={{ height: pull }} aria-hidden="true">
      {(pull > 12 || busy) && (
        <span style={{ transform: `rotate(${pull * 3}deg)`, opacity: Math.min(1, pull / THRESHOLD) }}>
          <Spinner size={28} />
        </span>
      )}
    </div>
  );
}
