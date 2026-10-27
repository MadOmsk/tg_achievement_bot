import { useLayoutEffect, useRef, useState } from "react";
import { tick } from "../core/haptic";
import { Icon, type IconName } from "./Icon";

export type BarTab<T extends string> = { id: T; icon: IconName; label: string };

/** The floating glass toolbar: the chosen tab widens into a pill with its
 * name, the others are icons; the pill slides from tab to tab. Search is a
 * separate accent button beside it. */
export function BottomBar<T extends string>({
  tabs,
  current,
  onTab,
  onSearch,
  searchLabel,
  hidden = false,
}: {
  tabs: BarTab<T>[];
  current: T | null;
  onTab: (tab: T) => void;
  onSearch: () => void;
  searchLabel: string;
  hidden?: boolean;
}) {
  const nav = useRef<HTMLElement>(null);
  const [pill, setPill] = useState<{ x: number; w: number } | null>(null);
  useLayoutEffect(() => {
    const place = () => {
      const on = nav.current?.querySelector<HTMLElement>(".bar-tab-on");
      setPill(on ? { x: on.offsetLeft, w: on.offsetWidth } : null);
    };
    place();
    const ro = new ResizeObserver(place);
    if (nav.current) ro.observe(nav.current);
    return () => ro.disconnect();
  }, [current, tabs.length]);
  return (
    <div className={`dock${hidden ? " dock-hidden" : ""}`}>
      <nav className="bar" aria-label="nav" ref={nav}>
        <span
          className={`bar-pill${pill ? "" : " bar-pill-off"}`}
          style={pill ? { transform: `translateX(${pill.x}px)`, width: pill.w } : undefined}
          aria-hidden="true"
        />
        {tabs.map((tab) => {
          const on = tab.id === current;
          return (
            <button
              key={tab.id}
              type="button"
              className={`bar-tab${on ? " bar-tab-on" : ""}`}
              aria-current={on ? "page" : undefined}
              aria-label={tab.label}
              onClick={() => {
                tick();
                onTab(tab.id);
              }}
            >
              <Icon name={tab.icon} filled={on} />
              <span className="bar-label">{tab.label}</span>
            </button>
          );
        })}
      </nav>
      <button
        type="button"
        className="fab"
        aria-label={searchLabel}
        onClick={() => {
          tick();
          onSearch();
        }}
      >
        <Icon name="search" size={26} />
      </button>
    </div>
  );
}
