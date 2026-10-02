import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import "./Dropdown.css";

export type DropdownOption<T> = { value: T; label: string; hint?: string; danger?: boolean };

const ROW = 46;
const PAD = 8;
const GAP = 6;

/**
 * A menu that unfolds from whatever opens it: the app's own picker for choosing
 * one of a list, in place of the system's. Opens below the trigger, or above it
 * when there is no room; a long list scrolls with the chosen item in view.
 */
export function Dropdown<T extends string | number>({
  value,
  options,
  onChange,
  trigger,
  className,
  align = "end",
  label,
}: {
  value: T;
  options: Array<DropdownOption<T>>;
  onChange: (value: T) => void;
  /** What the closed dropdown shows. */
  trigger: ReactNode;
  className?: string;
  /** Which edge of the trigger the menu lines up with. */
  align?: "start" | "end";
  label?: string;
}) {
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<{ top?: number; bottom?: number; left?: number; right?: number; maxHeight: number } | null>(null);

  const open = () => {
    const rect = button.current?.getBoundingClientRect();
    if (!rect) return;
    const want = options.length * ROW + PAD * 2;
    // Keep clear of the dock floating at the bottom of the screen.
    const below = window.innerHeight - rect.bottom - GAP - 104;
    const above = rect.top - GAP - 16;
    const down = below >= Math.min(want, 240) || below >= above;
    const room = down ? below : above;
    const side =
      align === "end"
        ? { right: Math.max(12, window.innerWidth - rect.right) }
        : { left: Math.max(12, rect.left) };
    setPlace({
      ...(down ? { top: rect.bottom + GAP } : { bottom: window.innerHeight - rect.top + GAP }),
      ...side,
      maxHeight: Math.min(want, room),
    });
  };
  const close = () => setPlace(null);

  useLayoutEffect(() => {
    if (!place || !menu.current) return;
    const chosen = menu.current.querySelector<HTMLElement>(".dd-item.is-on");
    chosen?.scrollIntoView({ block: "center" });
  }, [place]);

  useEffect(() => {
    if (!place) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", close);
    };
  }, [place]);

  return (
    <>
      <button
        ref={button}
        type="button"
        className={className ?? "dd-trigger"}
        aria-haspopup="listbox"
        aria-expanded={place != null}
        aria-label={label}
        onClick={() => (place ? close() : open())}
      >
        {trigger}
      </button>
      {place &&
        createPortal(
          <div className="dd-layer" onClick={close}>
            <div
              ref={menu}
              className="dd-menu"
              role="listbox"
              style={place}
              onClick={(e) => e.stopPropagation()}
            >
              {options.map((o) => (
                <button
                  key={String(o.value)}
                  type="button"
                  role="option"
                  aria-selected={o.value === value}
                  className={["dd-item", o.value === value ? "is-on" : "", o.danger ? "is-danger" : ""].filter(Boolean).join(" ")}
                  onClick={() => {
                    close();
                    if (o.value !== value) onChange(o.value);
                  }}
                >
                  <span className="dd-label">
                    {o.label}
                    {o.hint && <small>{o.hint}</small>}
                  </span>
                  {o.value === value && <span className="dd-check">✓</span>}
                </button>
              ))}
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

/** The small down-pointing arrow a dropdown trigger ends with. */
export function DropdownArrow() {
  return (
    <svg className="dd-arrow" width="14" height="14" viewBox="0 0 24 24" aria-hidden>
      <path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
