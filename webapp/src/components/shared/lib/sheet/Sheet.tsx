import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { CoverImg } from "../cover-img/CoverImg";
import "./Sheet.css";

export function Sheet({
  children,
  onClose,
  closeLabel,
  photo,
  tall,
  mid,
  compact,
  noClose: _noClose,
}: {
  children: ReactNode;
  onClose: () => void;
  closeLabel: string;
  photo?: boolean;
  tall?: boolean;
  mid?: boolean;
  compact?: boolean;
  noClose?: boolean;
}) {
  const [leaving, setLeaving] = useState(false);
  const closed = useRef(false);
  const armed = useRef(false);
  const finish = () => {
    if (closed.current) return;
    closed.current = true;
    onClose();
  };
  const close = () => setLeaving(true);
  useEffect(() => {
    armed.current = false;
    const id = window.setTimeout(() => {
      armed.current = true;
    }, 400);
    return () => window.clearTimeout(id);
  }, []);
  useEffect(() => {
    const html = document.documentElement;
    const y = window.scrollY;
    html.classList.add("is-sheet-open");
    window.Telegram?.WebApp?.expand?.();
    const freeze = () => {
      if (window.scrollY !== y) window.scrollTo(0, y);
    };
    const block = (event: TouchEvent) => {
      const node = event.target;
      if (!(node instanceof Element)) return;
      // The game page is a scroll layer of its own; when it is opened over a
      // sheet (a game tapped inside a drawer) it must still scroll.
      if (node.closest(".sheet-body, .game-page")) return;
      event.preventDefault();
    };
    window.addEventListener("scroll", freeze, { passive: true });
    document.addEventListener("touchmove", block, { passive: false });
    return () => {
      html.classList.remove("is-sheet-open");
      window.removeEventListener("scroll", freeze);
      document.removeEventListener("touchmove", block);
      window.scrollTo(0, y);
    };
  }, []);
  useEffect(() => {
    if (!leaving) return;
    const id = window.setTimeout(finish, 340);
    return () => window.clearTimeout(id);
  }, [leaving]);
  return createPortal(
    <div
      className={["sheet", compact ? "is-compact" : "", leaving ? "is-leave" : ""]
        .filter(Boolean)
        .join(" ")}
      onClick={() => {
        if (!armed.current) return;
        close();
      }}
      onAnimationEnd={(e) => {
        if (leaving && e.target === e.currentTarget) finish();
      }}
      role="presentation"
    >
      <div className="sheet-stack">
        <button
          type="button"
          className="sheet-dismiss"
          onClick={(e) => {
            e.stopPropagation();
            close();
          }}
          aria-label={closeLabel}
        >
          ✕
        </button>
        <div
          className={[
            "sheet-body glass",
            photo ? "is-photo" : "",
            tall ? "is-tall" : "",
            mid ? "is-mid" : "",
            compact ? "is-compact" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          onClick={(e) => e.stopPropagation()}
          role="dialog"
        >
          {children}
        </div>
      </div>
    </div>,
    document.body,
  );
}

export function SheetHero({
  src,
  secret,
  title,
  text,
  corner,
  lead,
  veil,
  children,
}: {
  src?: string | null;
  secret?: boolean;
  title: string;
  text?: string | null;
  corner?: ReactNode;
  lead?: ReactNode;
  veil?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className={secret ? "sheet-hero is-secret" : "sheet-hero"}>
      <div className="profile-hero-layers">
        <CoverImg src={src} kind="achievement" className="profile-hero-art" />
      </div>
      <div className="profile-hero-wash" />
      {lead}
      {corner}
      <div className="profile-hero-copy">
        <div className="profile-hero-words">
          <h2>{title}</h2>
          {text && <p>{text}</p>}
          {children}
        </div>
      </div>
      {veil}
    </div>
  );
}
