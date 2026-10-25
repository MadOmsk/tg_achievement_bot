import { t, type Locale } from "../../../i18n";
import { ContentPage } from "../../shared/lib";
import { clockOf, paragraphsOf } from "../post-text/postText";
import { RichLines, openUrl } from "../rich-text/RichText";

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

/** A developer's post, whole, on the app's one content page (`ContentPage`,
 * owner 2026-10-12): the picture, the game it is about, the kind and the day,
 * the title, the full text — never cut at a length, however long — and the
 * post on Steam last. Untranslated. */
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
  const kind = t(locale, post.kind === "patch" ? "newsPatch" : "newsPost");

  return (
    <ContentPage
      kind={kind}
      backLabel={t(locale, "back")}
      onClose={onClose}
      picture={post.image}
      pictureKind="game"
      game={game ?? null}
      gameLabel={t(locale, "pageGame")}
      date={dayOf(post.date, locale)}
      title={post.title}
      titleLang="en"
      resetKey={post}
      link={{ label: t(locale, "newsOnSteam"), onClick: () => openUrl(post.url) }}
    >
      <div className="post-page-text" lang="en">
        {paragraphsOf(body).map((paragraph, i) => (
          <p key={i}>
            <RichLines text={paragraph} className="rich-line" />
          </p>
        ))}
      </div>
    </ContentPage>
  );
}
