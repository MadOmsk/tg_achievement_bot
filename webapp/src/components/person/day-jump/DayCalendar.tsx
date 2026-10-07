import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { Locale } from "../../../i18n";
import { Icon } from "../../shared/lib";
import "./DayCalendar.css";

const GAP = 6;
/** The calendar's own height: the month row, the weekdays and six weeks. */
const HEIGHT = 380;

/** The `Y-M-D` key (no zero padding) the feed groups its days by. */
function calendarKey(year: number, month: number, day: number): string {
  return `${year}-${month + 1}-${day}`;
}

/**
 * A month's calendar that unfolds from a day label, the screen's width
 * (owner, 2026-10-07): only days that have something are enabled, with how
 * many; the arrows step between the months that have any.
 */
export function DayCalendar({
  locale,
  days,
  current,
  onPick,
  trigger,
  className,
}: {
  locale: Locale;
  /** day key -> how many entries fall on it */
  days: Map<string, number>;
  /** the day key the label stands for */
  current: string;
  onPick: (key: string) => void;
  trigger: ReactNode;
  className?: string;
}) {
  const button = useRef<HTMLButtonElement>(null);
  const [place, setPlace] = useState<{ top?: number; bottom?: number } | null>(null);
  const [cursor, setCursor] = useState(() => monthOf(current));

  const months = [...new Set([...days.keys()].map((key) => monthIndex(monthOf(key))))].sort((a, b) => a - b);

  const open = () => {
    const rect = button.current?.getBoundingClientRect();
    if (!rect) return;
    // Keep clear of the dock floating at the bottom of the screen.
    const below = window.innerHeight - rect.bottom - GAP - 104;
    setCursor(monthOf(current));
    setPlace(
      below >= HEIGHT || below >= rect.top
        ? { top: rect.bottom + GAP }
        : { bottom: window.innerHeight - rect.top + GAP },
    );
  };
  const close = () => setPlace(null);

  const isOpen = place != null;
  useEffect(() => {
    if (!isOpen) return;
    const y = window.scrollY;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    const freeze = () => {
      if (window.scrollY !== y) window.scrollTo(0, y);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", freeze, { passive: true });
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", freeze);
    };
  }, [isOpen]);

  const intl = locale === "en" ? "en-GB" : "ru-RU";
  const first = new Date(cursor.year, cursor.month, 1);
  const length = new Date(cursor.year, cursor.month + 1, 0).getDate();
  // Monday first: getDay() is 0 for Sunday.
  const lead = (first.getDay() + 6) % 7;
  const weekdays = Array.from({ length: 7 }, (_, i) =>
    new Date(2024, 0, 1 + i).toLocaleDateString(intl, { weekday: "short" }),
  );
  const now = new Date();
  const todayKey = calendarKey(now.getFullYear(), now.getMonth(), now.getDate());
  const at = months.indexOf(monthIndex(cursor));
  const step = (by: number) => {
    const next = months[at + by];
    if (next != null) setCursor({ year: Math.floor(next / 12), month: next % 12 });
  };

  return (
    <>
      <button
        ref={button}
        type="button"
        className={className}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        onClick={() => (isOpen ? close() : open())}
      >
        {trigger}
      </button>
      {place &&
        createPortal(
          <div className="dd-layer" onClick={close}>
            <div className="day-cal" role="dialog" style={place} onClick={(e) => e.stopPropagation()}>
              <div className="day-cal-head">
                <button
                  type="button"
                  className="day-cal-step"
                  disabled={at <= 0}
                  onClick={() => step(-1)}
                >
                  <Icon name="back" size={18} />
                </button>
                <strong>{first.toLocaleDateString(intl, { month: "long", year: "numeric" })}</strong>
                <button
                  type="button"
                  className="day-cal-step is-next"
                  disabled={at < 0 || at >= months.length - 1}
                  onClick={() => step(1)}
                >
                  <Icon name="back" size={18} />
                </button>
              </div>
              <div className="day-cal-grid">
                {weekdays.map((name) => (
                  <span key={name} className="day-cal-week">
                    {name}
                  </span>
                ))}
                {Array.from({ length: lead }, (_, i) => (
                  <span key={`gap-${i}`} />
                ))}
                {Array.from({ length }, (_, i) => {
                  const key = calendarKey(cursor.year, cursor.month, i + 1);
                  const count = days.get(key) ?? 0;
                  return (
                    <button
                      key={key}
                      type="button"
                      disabled={count === 0}
                      className={[
                        "day-cal-day",
                        count > 0 ? "has-items" : "",
                        key === current ? "is-on" : "",
                        key === todayKey ? "is-today" : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      onClick={() => {
                        close();
                        onPick(key);
                      }}
                    >
                      <span>{i + 1}</span>
                      {count > 0 && <small>{count}</small>}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

function monthOf(key: string): { year: number; month: number } {
  const [year, month] = key.split("-").map(Number);
  if (!year || !month) {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() };
  }
  return { year, month: month - 1 };
}

function monthIndex(at: { year: number; month: number }): number {
  return at.year * 12 + at.month;
}
