import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Swiper as SwiperInstance } from "swiper/types";

// The edge of the window fades out; this much spare room keeps the fade
// off the neighbour's last letters.
const FADE_ROOM = 22;

/**
 * The tab bar above the game page's swiper. Keeps its own state and listens
 * to the Swiper itself, the same reason `UnlockSlider`'s own dots do
 * (`SliderDots`): if the page held this, every slide change would re-render
 * the whole Swiper and, looping, rebuild its cloned slides.
 *
 * The labels sit on a track three times over and slide left as the tab
 * changes: the active one is always first, only its neighbour shows beside
 * it, and after the last comes the first again. The track jumps back a
 * block, unseen, once a slide has landed on a copy — so the motion is always
 * a slide, never a swap, and it is clear which tab left and which came in.
 */
export function GameTabBar({
  swiper,
  labels,
  actions,
}: {
  swiper: SwiperInstance;
  labels: string[];
  /** Per tab: its own action row next to the labels, or nothing when a tab
   * (like "Об игре") has no action of its own — the row just isn't there. */
  actions: ReactNode[];
}) {
  const count = labels.length;
  const [active, setActive] = useState(swiper.realIndex);
  // Where the active tab is on the tripled track; always `active` modulo count.
  const [pos, setPos] = useState(count + swiper.realIndex);
  const [box, setBox] = useState({ shift: 0, width: 0 });
  const [animated, setAnimated] = useState(false);
  const trackRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onChange = () => {
      const next = swiper.realIndex;
      setActive(next);
      setPos((cur) => {
        let step = next - (cur % count);
        if (step > count / 2) step -= count;
        if (step < -count / 2) step += count;
        return cur + step;
      });
    };
    swiper.on("slideChange", onChange);
    return () => {
      swiper.off("slideChange", onChange);
    };
  }, [swiper, count]);

  // Measured before paint: how far to slide, and how wide the window is —
  // the active tab and its neighbour, no more.
  const key = labels.join("|");
  useLayoutEffect(() => {
    const kids = trackRef.current?.children;
    const current = kids?.[pos] as HTMLElement | undefined;
    if (!kids || !current) return;
    const next = kids[pos + 1] as HTMLElement | undefined;
    const end = next
      ? next.offsetLeft + next.offsetWidth
      : current.offsetLeft + current.offsetWidth;
    setBox({ shift: current.offsetLeft, width: end - current.offsetLeft });
  }, [pos, key]);

  // No slide on the first draw.
  useEffect(() => {
    const id = requestAnimationFrame(() => setAnimated(true));
    return () => cancelAnimationFrame(id);
  }, []);

  // A slide that landed on a copy jumps back to the middle block, unseen.
  const settle = (event: React.TransitionEvent) => {
    if (event.propertyName !== "transform") return;
    if (pos >= count && pos < count * 2) return;
    setAnimated(false);
    setPos((cur) => (cur < count ? cur + count : cur - count));
    requestAnimationFrame(() => requestAnimationFrame(() => setAnimated(true)));
  };

  return (
    <div className="game-tabs-row">
      <div
        className={animated ? "game-tabs is-animated" : "game-tabs"}
        role="tablist"
        style={{ width: box.width ? box.width + FADE_ROOM : undefined }}
      >
        <div
          ref={trackRef}
          className="game-tabs-track"
          style={{ transform: `translateX(${-box.shift}px)` }}
          onTransitionEnd={settle}
        >
          {[0, 1, 2].flatMap((block) =>
            labels.map((label, i) => (
              <button
                key={`${block}-${i}`}
                type="button"
                role="tab"
                aria-selected={active === i}
                aria-hidden={block !== 1 || undefined}
                tabIndex={block === 1 ? undefined : -1}
                className={active === i ? "is-on" : undefined}
                onClick={() => swiper.slideToLoop(i)}
              >
                {label}
              </button>
            )),
          )}
        </div>
      </div>
      {actions[active]}
    </div>
  );
}
