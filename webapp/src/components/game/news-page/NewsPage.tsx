import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { t, type Locale } from "../../../i18n";
import { BackHead, CoverImg, FitImg, Icon, useImageRatio, openImage } from "../../shared/lib";
import { clockOf, paragraphsOf } from "../patch-notes/PatchNotes";
import { RichLines, openUrl } from "../rich-text/RichText";
import "../post-page/PostPage.css";

export type NewsPost = {
  title: string;
  /** ISO date. */
  date: string;
  /** The whole post: pictures and videos on lines of their own. */
  text: string;
  image: string | null;
  /** The post on Steam. */
  url: string;
  kind?: "patch" | "news";
};

function dayOf(iso: string, locale: Locale): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const day = date.toLocaleDateString(locale === "en" ? "en-GB" : "ru-RU", {
    day: "numeric",
    month: "long",
    year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  });
  const clock = clockOf(iso, locale);
  return clock ? `${day}, ${clock}` : day;
}

/** A developer's post, whole, on a page of its own (owner, 2026-10-05): a post
 * may be long, with many pictures, videos and tables. Over everything — the
 * game page too, when it is a patch from there — with its own scroll and a way
 * back (the arrow, and the phone's back). The game named in the head; the
 * picture edge to edge, all of it; the kind and the day, the title, the full
 * text; the post on Steam last.
 * Untranslated. */
export function NewsPage({
  post,
  locale,
  game,
  onClose,
}: {
  post: NewsPost;
  locale: Locale;
  /** The game it is about, when the page was opened from outside the game. */
  game?: { name: string; icon_url: string | null; onOpen?: () => void };
  onClose: () => void;
}) {
  const page = useRef<HTMLDivElement>(null);
  // Nothing lies over the picture here: the frame is its own shape.
  const ratio = useImageRatio(post.image, { fallback: 16 / 9 });

  useEffect(() => {
    page.current?.scrollTo(0, 0);
  }, [post]);

  // The top picture is usually the post's first one too: not shown twice.
  let skipped = false;
  const body = post.text
    .split("\n")
    .filter((line) => {
      if (!skipped && post.image && line.trim() === post.image) {
        skipped = true;
        return false;
      }
      return true;
    })
    .join("\n")
    .trim();

  return createPortal(
    <div className="post-page" ref={page} data-no-pull>
      <BackHead
        title={game?.name ?? t(locale, post.kind === "patch" ? "newsPatch" : "newsPost")}
        backLabel={t(locale, "back")}
        onBack={onClose}
      />
      {post.image && (
        <div className="post-page-pic" style={{ aspectRatio: ratio }} onClick={() => post.image && openImage(post.image)}>
          <CoverImg src={post.image} kind="game" className="post-page-back" />
          <FitImg src={post.image} kind="game" mode="contain" />
        </div>
      )}
      <article className="post-page-body">
        {/* The game is in the head; when on the left, the kind on the right, as
            the list of updates has them. */}
        <div className="post-page-meta">
          <span className="post-page-date">{dayOf(post.date, locale)}</span>
          {post.kind && (
            <span className="post-page-kind">
              {t(locale, post.kind === "patch" ? "newsPatch" : "newsPost")}
            </span>
          )}
        </div>
        <h1 className="post-page-title" lang="en">
          {post.title}
        </h1>
        <div className="post-page-text" lang="en">
          {paragraphsOf(body).map((paragraph, i) => (
            <p key={i}>
              <RichLines text={paragraph} className="rich-line" />
            </p>
          ))}
        </div>
        {/* Somewhere else, not an action here: the accent link with its arrow. */}
        <button type="button" className="see-all post-page-steam" onClick={() => openUrl(post.url)}>
          <span>{t(locale, "newsOnSteam")}</span>
          <Icon name="forward" size={16} />
        </button>
      </article>
    </div>,
    document.body,
  );
}
