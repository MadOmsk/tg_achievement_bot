import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { CoverImg } from "../cover-img/CoverImg";
import { useBackHandler } from "../back-stack/backStack";
import { Icon } from "../icon/Icon";
import { t } from "../../../../i18n";
import "./Sheet.css";

/** What used to rise from the bottom as a drawer is a page of its own (owner,
 * 2026-10-07): over everything, its own scroll, the app's background, and a
 * head with the way back — the arrow, and the phone's back. A page names
 * itself by `title` (with `aside` at the head's right), or keeps the heading
 * of its own content. */
export function Sheet({
  children,
  onClose,
  title,
  head,
  aside,
  photo,
  tall,
  mid,
  compact,
}: {
  children: ReactNode;
  onClose: () => void;
  title?: string;
  /** In place of a title: whatever names the page (a person's face and name). */
  head?: ReactNode;
  aside?: ReactNode;
  photo?: boolean;
  tall?: boolean;
  mid?: boolean;
  compact?: boolean;
}) {
  const [leaving, setLeaving] = useState(false);
  const closed = useRef(false);
  const finish = () => {
    if (closed.current) return;
    closed.current = true;
    onClose();
  };
  const close = () => setLeaving(true);
  const backLabel = t(document.documentElement.lang === "en" ? "en" : "ru", "back");
  useBackHandler(true, close);
  useEffect(() => {
    const html = document.documentElement;
    const y = window.scrollY;
    html.classList.add("is-sheet-open");
    window.Telegram?.WebApp?.expand?.();
    return () => {
      html.classList.remove("is-sheet-open");
      window.scrollTo(0, y);
    };
  }, []);
  useEffect(() => {
    if (!leaving) return;
    const id = window.setTimeout(finish, 260);
    return () => window.clearTimeout(id);
  }, [leaving]);
  return createPortal(
    <div
      className={["sheet-page", leaving ? "is-leave" : ""].filter(Boolean).join(" ")}
      role="dialog"
      data-no-pull
    >
      {head ? (
        // Somebody's page: the same bar a profile and Home have.
        <header className="account-bar person-bar">
          <div className="account-top">
            <button type="button" className="person-back" onClick={close} aria-label={backLabel}>
              <Icon name="back" size={26} />
            </button>
            {head}
            {aside}
          </div>
        </header>
      ) : (
        <header className="page-head">
          <button type="button" className="icon-btn" onClick={close} aria-label={backLabel}>
            <Icon name="back" size={26} />
          </button>
          {title && <h1>{title}</h1>}
          {aside && <span className="page-head-aside">{aside}</span>}
        </header>
      )}
      <div
        className={[
          "sheet-body",
          photo ? "is-photo" : "",
          tall ? "is-tall" : "",
          mid ? "is-mid" : "",
          compact ? "is-compact" : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {children}
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
