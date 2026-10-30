import { createContext, useContext, useEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";
import { useBackHandler } from "../core/back-stack";
import { t } from "../i18n";
import { IconButton } from "./Controls";

const inTelegram = () => Boolean(window.Telegram?.WebApp?.initData);
/** The page's language is set from the person's (App sets `<html lang>`). */
const word = (key: "back" | "close") => t(document.documentElement.lang === "en" ? "en" : "ru", key);

/** Where a page's bar keeps its actions, for `BarAction`. */
const BarSlot = createContext<HTMLElement | null>(null);

/** A page's own action — following a person, a game's heart — riding up into
 * the page's bar once its place in the page (`anchor`) has scrolled up under
 * the bar, so it stays a tap away (the app's way, for every page with an
 * action in its head). Its place in the page stays as it is; the bar shows
 * this compact twin. */
/** A page's action in its bar: shown once `anchor` (its twin on the page)
 * scrolls under the bar, or always with no anchor. */
export function BarAction({ children, anchor }: { children: ReactNode; anchor?: RefObject<HTMLElement | null> }) {
  const slot = useContext(BarSlot);
  const [shown, setShown] = useState(!anchor);
  // The anchor may come after the page does (a person's card loads first):
  // look for it after every render, watch it once it is there.
  const watched = useRef<{ node: HTMLElement; io: IntersectionObserver } | null>(null);
  useEffect(() => {
    if (!anchor) return;
    const node = anchor.current;
    if (watched.current?.node === node) return;
    watched.current?.io.disconnect();
    watched.current = null;
    const scroller = node?.closest<HTMLElement>("[data-scroll]");
    if (!node || !scroller) return;
    const bar = slot?.closest<HTMLElement>(".appbar")?.offsetHeight ?? 64;
    const io = new IntersectionObserver(
      ([e]) => setShown(!e.isIntersecting && e.boundingClientRect.top < (e.rootBounds?.top ?? 0) + bar),
      { root: scroller, rootMargin: `-${bar}px 0px 0px 0px` },
    );
    io.observe(node);
    watched.current = { node, io };
  });
  useEffect(
    () => () => {
      watched.current?.io.disconnect();
      watched.current = null;
    },
    [],
  );
  return slot ? createPortal(<span className={`bar-action${shown ? " bar-action-on" : ""}`}>{children}</span>, slot) : null;
}

/** A page opened over the tabs: slides in from the side, scrolls on its own,
 * and the phone's back (or Telegram's header button) closes it. Inside
 * Telegram the header's own arrow is the way back, so ours is not drawn. */
export function Page({
  title,
  onBack,
  actions,
  children,
  hero = false,
  className = "",
  style,
  layer,
  bare = false,
}: {
  title?: ReactNode;
  onBack: () => void;
  actions?: ReactNode;
  children: ReactNode;
  /** The page starts with a picture under the bar: the bar is see-through
   * until the page scrolls. */
  hero?: boolean;
  className?: string;
  style?: CSSProperties;
  /** Names what is open, so a reused page counts as a new step back. */
  layer?: string;
  /** No bar at all: the page draws its own way out. */
  bare?: boolean;
}) {
  useBackHandler(true, onBack, layer);
  const scroller = useRef<HTMLDivElement>(null);
  const [scrolled, setScrolled] = useState(false);
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  useEffect(() => {
    scroller.current?.scrollTo(0, 0);
  }, [layer]);
  return (
    <div className={`page ${className}`} style={style}>
      <div
        className="page-scroll"
        data-scroll
        ref={scroller}
        onScroll={(e) => setScrolled(e.currentTarget.scrollTop > 8)}
      >
        {!bare && (
          <header className={`appbar${hero ? " appbar-hero" : ""}${scrolled ? " appbar-solid" : ""}`}>
            {!inTelegram() ? (
              <IconButton icon="back" label={word("back")} variant={hero ? "glass" : "plain"} onClick={onBack} />
            ) : (
              <span className="appbar-spacer" />
            )}
            <span className="appbar-title clamp-1">{title}</span>
            <span className="appbar-actions" ref={setSlot}>
              {actions}
            </span>
          </header>
        )}
        <BarSlot.Provider value={slot}>{children}</BarSlot.Provider>
      </div>
    </div>
  );
}

/** A sheet from the bottom over a dimmed screen. */
export function Sheet({
  onClose,
  children,
  title,
  layer,
}: {
  onClose: () => void;
  children: ReactNode;
  title?: string;
  layer?: string;
}) {
  useBackHandler(true, onClose, layer);
  // Pulled down — from its top, or from its list scrolled to the top — the
  // sheet follows the finger and, past a short way, goes.
  const sheet = useRef<HTMLDivElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const drag = useRef<{ y: number; dy: number } | null>(null);
  const [pull, setPull] = useState(0);
  const start = (y: number, target: EventTarget, fromBody: boolean) => {
    if (fromBody && (body.current?.scrollTop ?? 0) > 0) return;
    // A control that drags by itself (a crop frame, a slider) keeps the finger.
    if ((target as Element).closest?.("[data-no-pull], input[type=range]")) return;
    drag.current = { y, dy: 0 };
  };
  const move = (y: number) => {
    if (!drag.current) return;
    drag.current.dy = Math.max(0, y - drag.current.y);
    setPull(drag.current.dy);
  };
  const end = () => {
    if (!drag.current) return;
    const far = drag.current.dy > Math.min(120, (sheet.current?.offsetHeight ?? 400) * 0.25);
    drag.current = null;
    setPull(0);
    if (far) onClose();
  };
  // Over everything, the toolbar included: a page is a layer of its own.
  return createPortal(
    <div className="sheet-wrap" role="dialog" aria-modal="true">
      <button
        type="button"
        className="sheet-scrim"
        aria-label={word("close")}
        onClick={onClose}
        style={pull ? { opacity: Math.max(0.2, 1 - pull / 300) } : undefined}
      />
      <div
        ref={sheet}
        className={`sheet${pull ? " sheet-pulled" : ""}`}
        style={pull ? { transform: `translateY(${pull}px)` } : undefined}
        onTouchStart={(e) => start(e.touches[0].clientY, e.target, body.current?.contains(e.target as Node) ?? false)}
        onTouchMove={(e) => move(e.touches[0].clientY)}
        onTouchEnd={end}
        onTouchCancel={end}
      >
        <span className="sheet-grab" />
        {title && <h2 className="sheet-title t-title">{title}</h2>}
        <div ref={body} className="sheet-body">
          {children}
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** A yes/no question over everything. */
export function Confirm({
  text,
  yes,
  no,
  danger = false,
  onYes,
  onNo,
}: {
  text: string;
  yes: string;
  no: string;
  danger?: boolean;
  onYes: () => void;
  onNo: () => void;
}) {
  useBackHandler(true, onNo, "confirm");
  return createPortal(
    <div className="dialog-wrap" role="alertdialog" aria-modal="true">
      <button type="button" className="sheet-scrim" aria-label={no} onClick={onNo} />
      <div className="dialog">
        <p className="dialog-text">{text}</p>
        <div className="dialog-actions">
          <button type="button" className="btn btn-text" onClick={onNo}>
            {no}
          </button>
          <button type="button" className={`btn ${danger ? "btn-danger" : "btn-filled"}`} onClick={onYes}>
            {yes}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
