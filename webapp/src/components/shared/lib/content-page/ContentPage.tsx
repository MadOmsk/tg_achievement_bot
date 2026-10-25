import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { BackHead } from "../back-head/BackHead";
import { CoverImg } from "../cover-img/CoverImg";
import { FitImg } from "../fit-img/FitImg";
import { Icon } from "../icon/Icon";
import { openImage } from "../image-viewer";
import { useImageRatio } from "../img-ratio";
import "./PostPage.css";
import "./ContentPage.css";

export type ContentGame = {
  name: string;
  icon_url: string | null;
  /** Opens the game; without it the line is only a label. */
  onOpen?: () => void;
  /** How far along the person whose page it is: a count and a thin bar. */
  progress?: { unlocked: number; total: number } | null;
};

export type ContentFact = {
  /** What it is, in small capitals. */
  label: string;
  value: ReactNode;
  /** A unit after the value ("ч.", "G"). */
  unit?: string;
};

/** The game a page belongs to, as a line of the page: the cover, the name and
 * — when known — how far along the person is; the arrow when it opens. */
function ContentGameRow({ game, label }: { game: ContentGame; label?: string }) {
  const progress = game.progress && game.progress.total > 0 ? game.progress : null;
  const done = Boolean(progress && progress.unlocked >= progress.total);
  return (
    <button
      type="button"
      className={done ? "cpage-game is-done" : "cpage-game"}
      onClick={game.onOpen}
      disabled={!game.onOpen}
    >
      <CoverImg src={game.icon_url} kind="game" className="cpage-game-art" />
      <span className="cpage-game-copy">
        {!progress && label && <small>{label}</small>}
        <strong>{game.name}</strong>
        {progress && (
          <span className="played-bar cpage-game-bar" aria-hidden>
            <span
              className="played-bar-fill"
              style={{ width: `${(100 * Math.min(progress.unlocked, progress.total)) / progress.total}%` }}
            />
          </span>
        )}
      </span>
      {game.onOpen && <Icon name="forward" size={18} />}
    </button>
  );
}

/**
 * The one page every piece of content opens on (owner, 2026-10-12): an
 * achievement, a patch, a news post, a game from HowLongToBeat. Over the
 * whole app, with its own scroll and a bar with the way back, the kind of page
 * it is and — at its right — what the thing is worth: an achievement's rarity
 * and points or trophy. Everything else is in the body, always in this order:
 *
 * 1. the picture, edge to edge (a small one stands on its own ground);
 * 2. the game it belongs to, a line that opens it;
 * 3. what it is called: the kind, the day, the title, the line under it;
 * 4. its facts, as tiles — a game's hours;
 * 5. what the page is about: the sections, the whole text;
 * 6. where else it can be read, an accent link with its arrow.
 */
export function ContentPage({
  kind,
  backLabel,
  onClose,
  picture,
  pictureKind = "game",
  fallbackPicture,
  game,
  gameLabel,
  badge,
  date,
  title,
  titleLang,
  lead,
  facts,
  resetKey,
  link,
  aside,
  children,
}: {
  /** What this page is, for the bar: «Достижение», «Патч», «Игра». */
  kind: string;
  backLabel: string;
  onClose: () => void;
  picture?: string | null;
  pictureKind?: "game" | "achievement";
  /** Shown when there is no picture of its own (an achievement's game cover). */
  fallbackPicture?: string | null;
  game?: ContentGame | null;
  /** The small caption over the game's name: «Игра». */
  gameLabel?: string;
  /** The kind's pill beside the day. */
  badge?: string | null;
  date?: string | null;
  title: string;
  titleLang?: string;
  lead?: string | null;
  facts?: ContentFact[];
  /** A new value scrolls the page back to its top (the same page, another item). */
  resetKey?: unknown;
  link?: { label: string; onClick: () => void } | null;
  /** At the bar's right: what it is worth (rarity, points, a trophy). */
  aside?: ReactNode;
  children?: ReactNode;
}) {
  const page = useRef<HTMLDivElement>(null);
  const shown = picture || fallbackPicture || null;
  const ratio = useImageRatio(shown, { fallback: 16 / 9 });

  useEffect(() => {
    page.current?.scrollTo(0, 0);
  }, [resetKey]);

  return createPortal(
    <div className="post-page content-page" ref={page} data-no-pull>
      <BackHead title={kind} backLabel={backLabel} onBack={onClose} aside={aside} />
      {shown && (
        <div
          className="post-page-pic"
          style={{ aspectRatio: ratio }}
          onClick={() => openImage(shown)}
        >
          <CoverImg src={shown} kind={pictureKind} className="post-page-back" />
          <FitImg src={shown} kind={pictureKind} mode="contain" />
        </div>
      )}
      <article className="post-page-body">
        {game && (
          <ContentGameRow game={game} label={gameLabel} />
        )}
        <header className="cpage-title">
          {(badge || date) && (
            <div className="post-page-meta">
              {badge && <span className="cpage-badge">{badge}</span>}
              {date && <span className="post-page-date">{date}</span>}
            </div>
          )}
          <h1 className="post-page-title" lang={titleLang}>
            {title}
          </h1>
          {lead && <p className="post-page-lead">{lead}</p>}
        </header>
        {facts && facts.length > 0 && (
          <div
            className="cpage-facts"
            style={{ gridTemplateColumns: `repeat(${Math.min(facts.length, 3)}, minmax(0, 1fr))` }}
          >
            {facts.map((fact) => (
              <div key={fact.label} className="cpage-fact">
                <p>{fact.label}</p>
                <strong>
                  {fact.value}
                  {fact.unit && <em>{fact.unit}</em>}
                </strong>
              </div>
            ))}
          </div>
        )}
        {children}
        {link && (
          <button type="button" className="see-all post-page-steam" onClick={link.onClick}>
            <span>{link.label}</span>
            <Icon name="forward" size={16} />
          </button>
        )}
      </article>
    </div>,
    document.body,
  );
}
