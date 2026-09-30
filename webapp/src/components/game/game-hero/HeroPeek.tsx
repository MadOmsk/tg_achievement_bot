import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

/** Falls back to this fraction of the natural height when there's no
 * progress plate to measure against (e.g. a game with no achievements yet). */
const COLLAPSED_RATIO = 0.3;
/** The gap above the plate at rest. */
const PLATE_GAP = 32;
/** How far a swipe has to travel before it counts as one — past this, the
 * hero snaps open or closed outright; nothing follows the finger in between. */
const SWIPE_PX = 32;
/** A touch that has moved this far sideways before it has moved SWIPE_PX
 * vertically is the tab swiper's, not ours. */
const SIDEWAYS_PX = 10;

/**
 * Wraps the game hero so only a sliver of its bottom shows at rest, the
 * progress plate right under it — the picture was the same on every visit,
 * not worth the scroll it cost to get past. A small swipe down anywhere on
 * the game page while it's scrolled to its own top opens it outright (no
 * proportional follow, no partway state — a scroll-like drag here read as
 * unintentional and cheap-feeling); a small swipe up while open closes it
 * outright, the same way. Both animate via CSS transition, not the touch
 * position.
 *
 * Either swipe consumes the rest of that touch (`preventDefault` up to the
 * moment it's decided) so it can't also scroll the page underneath it; once
 * decided, the gesture is spent and further movement in the same touch is
 * left alone (a continued drag past that point can fall through to a real
 * scroll, same as lifting the finger and starting a fresh one would).
 *
 * The wrapped content's own height and layout are never touched — it
 * renders at its natural size and is just clipped and shifted within a
 * shorter window.
 *
 * The game page is its own `overflow-y: auto` box (a fixed full-screen
 * layer, not document scroll), so "at the top" means that box's own
 * scrollTop, never `window.scrollY` — the window itself never scrolls
 * while it's open.
 */
export function HeroPeek({ children }: { children: (open: boolean) => ReactNode }) {
  const innerRef = useRef<HTMLDivElement>(null);
  const [naturalH, setNaturalH] = useState(0);
  const [collapsedH, setCollapsedH] = useState(0);
  const [open, setOpen] = useState(false);
  const openRef = useRef(open);
  openRef.current = open;
  const dragging = useRef(false);
  const decided = useRef(false);
  // Only set once decided: true when this touch actually triggered an
  // open/close and the rest of it should keep being swallowed; false when
  // it turned out not to be one (already open and dragged further open,
  // already closed and dragged further closed, or a plain scroll) — that
  // touch is native's from here on, same as if it had never been decided.
  const consuming = useRef(false);
  const startY = useRef(0);
  const startX = useRef(0);
  // Until the person actually swipes it once, no measurement is animated —
  // covers not just the very first paint (useLayoutEffect already handles
  // that one) but every remeasure before that first swipe, e.g. the
  // progress plate's skeleton swapping for its real, differently-sized
  // content once the achievements finish loading. Without this, that swap
  // alone was enough to trigger the height transition and visibly nudge
  // the page right after it opened.
  const interacted = useRef(false);

  // Layout effect, not the usual effect: it must measure and set the
  // collapsed height *before* the browser's first paint. A regular effect
  // runs after that paint, so the page would flash the picture at full
  // height for a frame and then visibly animate down into place — this
  // makes sure it's already collapsed in the very first frame shown.
  useLayoutEffect(() => {
    const el = innerRef.current;
    if (!el) return;
    // Collapsed height is set from the progress plate's (or, for a
    // completed game, the platinum medal's) own height plus a fixed gap
    // above it — measured against that marker itself, not a flat ratio of
    // the whole picture, so it's always shown in full, never cut through.
    const measure = () => {
      let h = el.offsetHeight;
      // The medal sits below the cover on a *margin*, not real layout
      // height (it's positioned absolutely, past the cover's own bottom
      // edge) — a margin that collapses straight through this wrapper and
      // never shows up in offsetHeight. Measured that way, naturalH came
      // out shorter than the medal actually reaches, and the open state's
      // clip (which is naturalH tall) cut the bottom of it off. Extend h
      // to the medal's real bottom edge when there is one.
      const medal = el.querySelector<HTMLElement>(".game-medal");
      if (medal) {
        const elTop = el.getBoundingClientRect().top;
        const medalBottom = medal.getBoundingClientRect().bottom - elTop;
        h = Math.max(h, medalBottom);
      }
      setNaturalH(h);
      const marker = el.querySelector<HTMLElement>(".game-plate, .game-medal");
      if (marker) {
        setCollapsedH(marker.getBoundingClientRect().height + PLATE_GAP);
      } else {
        setCollapsedH(h * COLLAPSED_RATIO);
      }
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
    // Also re-measure right when `open` flips: the compact plate and the
    // full medal swap in GameHero at that point, but since the medal's own
    // margin doesn't affect this wrapper's own box (see above), that swap
    // doesn't always register as a resize on its own.
  }, [open]);

  useEffect(() => {
    const inner = innerRef.current;
    const scrollEl = inner?.closest<HTMLElement>(".game-page");
    if (!scrollEl) return;
    const atTop = () => scrollEl.scrollTop <= 1;
    const onStart = (event: TouchEvent) => {
      if (!atTop()) return;
      dragging.current = true;
      decided.current = false;
      consuming.current = false;
      startY.current = event.touches[0]?.clientY ?? 0;
      startX.current = event.touches[0]?.clientX ?? 0;
    };
    const onMove = (event: TouchEvent) => {
      if (!dragging.current) return;
      if (decided.current) {
        // The swipe already fired earlier in this same touch — consume the
        // rest of it outright. Letting the browser's scroll pick up
        // mid-touch, right as setOpen() is reflowing everything under the
        // still-down finger, is what read as "scrolls off on its own, no
        // telling which way": the touch's coordinates stop lining up with
        // what's now underneath them. A fresh touch (lift and drag again)
        // scrolls normally; this one is spent. A touch that turned out
        // *not* to be a swipe (consuming false) was never held past here —
        // it's been scrolling for real since the moment that became clear.
        if (consuming.current) event.preventDefault();
        return;
      }
      const y = event.touches[0]?.clientY ?? 0;
      const dy = y - startY.current;
      const dx = (event.touches[0]?.clientX ?? 0) - startX.current;
      if (Math.abs(dx) >= SIDEWAYS_PX && Math.abs(dx) > Math.abs(dy)) {
        // Sideways: flipping between the achievements and "Об игре" tabs.
        // Never ours — let the tab swiper have the whole touch, untouched.
        decided.current = true;
        return;
      }
      if (Math.abs(dy) < SWIPE_PX) {
        // Still deciding what this touch is — hold the scroll off until it
        // either commits to a swipe or turns out to be something else.
        event.preventDefault();
        return;
      }
      decided.current = true;
      if (dy > 0 && !openRef.current) {
        setOpen(true);
        interacted.current = true;
        consuming.current = true;
      } else if (dy < 0 && openRef.current) {
        setOpen(false);
        interacted.current = true;
        consuming.current = true;
      }
      // Not a swipe we act on (already open and pulled further, already
      // closed and pushed further, or just a plain scroll) — nothing to
      // prevent; the browser picks the rest of this touch up as a normal
      // scroll from here, a beat later than usual but not blocked outright.
      if (consuming.current) event.preventDefault();
    };
    const onEnd = () => {
      dragging.current = false;
    };
    scrollEl.addEventListener("touchstart", onStart, { passive: true });
    scrollEl.addEventListener("touchmove", onMove, { passive: false });
    scrollEl.addEventListener("touchend", onEnd);
    scrollEl.addEventListener("touchcancel", onEnd);
    return () => {
      scrollEl.removeEventListener("touchstart", onStart);
      scrollEl.removeEventListener("touchmove", onMove);
      scrollEl.removeEventListener("touchend", onEnd);
      scrollEl.removeEventListener("touchcancel", onEnd);
    };
  }, []);

  const pull = open ? 1 : 0;
  const clipH = naturalH ? collapsedH + (naturalH - collapsedH) * pull : undefined;
  const shift = naturalH ? (naturalH - collapsedH) * (1 - pull) : 0;
  // Collapsed, the bottom edge of the picture (only the picture — the
  // progress plate under it stays as it is) fades toward transparent, a
  // soft cut instead of a hard one and a hint there's more above it. Fully
  // open, it's opaque all the way down. Set as a custom property, not an
  // inline mask, so it can reach .game-cover specifically instead of the
  // whole hero (see game.css).
  const peekFade = { "--peek-fade": pull } as CSSProperties;
  const noTransition = !interacted.current;

  return (
    <div
      className="hero-peek"
      style={
        clipH
          ? {
              height: clipH,
              transition: noTransition ? "none" : undefined,
              ...peekFade,
            }
          : undefined
      }
    >
      <div
        ref={innerRef}
        className="hero-peek-inner"
        style={{
          transform: `translateY(${-shift}px)`,
          transition: noTransition ? "none" : undefined,
        }}
      >
        {children(open)}
      </div>
    </div>
  );
}
