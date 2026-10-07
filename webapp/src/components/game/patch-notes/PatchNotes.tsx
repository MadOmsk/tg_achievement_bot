import { useEffect, useState } from "react";
import type { GamePatch } from "../../../api";
import { t, timeAgo, type Locale } from "../../../i18n";
import { NewsPage } from "../news-page/NewsPage";
import { withoutLinks } from "../rich-text/RichText";

const FRESH_DAYS = 14;
/** The post as paragraphs, list lines kept together: Steam posts put a blank
 * line between nearly every line, which is far too airy to read. */
export function paragraphsOf(text: string): string[] {
  const out: string[] = [];
  for (const paragraph of text.split(/\n{2,}/)) {
    const isItem = paragraph.startsWith("- ");
    if (isItem && out.length > 0 && out[out.length - 1].startsWith("- ")) {
      out[out.length - 1] += `\n${paragraph}`;
    } else {
      out.push(paragraph);
    }
  }
  return out;
}

/** The closed card's few lines: the whole post run together in one paragraph. */
function previewOf(text: string): string {
  return withoutLinks(text)
    .replace(/^- /gm, "")
    .replace(/\s*\n+\s*/g, " ")
    .trim();
}

function isFresh(iso: string): boolean {
  const date = new Date(iso).getTime();
  return !Number.isNaN(date) && Date.now() - date < FRESH_DAYS * 86_400_000;
}

/** A post's hour and minute, in the reader's own time. */
export function clockOf(iso: string, locale: Locale): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime()) || iso.length <= 10) return "";
  return date.toLocaleTimeString(locale === "en" ? "en-GB" : "ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export type PostFilter = "all" | "news" | "patch";

/** The "Обновления" tab: the developer's posts from Steam, newest first, plain
 * rows with a hairline between, as every list. A row shows its kind and time,
 * the start of the post and its first picture; it opens whole on its own page
 * (NewsPage). */
export function PatchNotes({
  patches,
  locale,
  collapseKey,
  onLayout,
  game,
  filter = "all",
}: {
  /** undefined: still being asked. */
  patches: GamePatch[] | undefined;
  locale: Locale;
  /** Changes whenever the tab was switched: every card closes. */
  collapseKey?: number;
  /** Called after the content changed height (loaded, or a card opened). */
  onLayout?: () => void;
  /** The game these are of: a patch's own page names it, as a post from
   * «Новости» does (already on its page, it opens nothing). */
  game?: { name: string; icon_url: string | null };
  filter?: PostFilter;
}) {
  // A patch opens whole on a page of its own, as a post in «Новости» does.
  const [open, setOpen] = useState<GamePatch | null>(null);

  useEffect(() => {
    setOpen(null);
  }, [collapseKey]);

  useEffect(() => {
    onLayout?.();
  }, [patches, onLayout]);

  if (patches === undefined) {
    return (
      <div className="patch-list">
        {[0, 1, 2].map((i) => (
          <div key={i} className="patch-card">
            <span className="skel line" style={{ width: "40%" }} />
            <span
              className="skel line"
              style={{ width: "75%", marginTop: 10 }}
            />
            <span
              className="skel line"
              style={{ width: "95%", marginTop: 8 }}
            />
          </div>
        ))}
      </div>
    );
  }

  const shown = patches.filter((patch) => filter === "all" || (patch.kind ?? "patch") === filter);

  return (
    <div className="patch-list">
      {shown.length === 0 && (
        <p className="empty">{t(locale, "patchesEmpty")}</p>
      )}
      {shown.map((patch) => {
        const kind = t(locale, patch.kind === "news" ? "newsPost" : "newsPatch");
        return (
          <div
            key={`${patch.date}|${patch.title}`}
            role="button"
            tabIndex={0}
            className="patch-card"
            onClick={() => setOpen(patch)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") setOpen(patch);
            }}
          >
            {/* When on the left, as a feed post says it; the kind on the right. */}
            <span className="patch-card-meta">
              <span className="patch-card-when">{timeAgo(patch.date, locale)}</span>
              {isFresh(patch.date) && <span className="patch-card-new">{t(locale, "patchesNew")}</span>}
              <span className="patch-card-kind">{kind}</span>
            </span>
            <span className="patch-card-row">
              <span className="patch-card-main">
                <span className="patch-card-name">{patch.title}</span>
                {patch.text && <span className="patch-card-body is-preview">{previewOf(patch.text)}</span>}
              </span>
              {patch.image && <img className="patch-card-pic" src={patch.image} alt="" loading="lazy" />}
            </span>
          </div>
        );
      })}
      {open && (
        <NewsPage
          post={{
            title: open.title,
            date: open.date,
            text: open.text,
            image: open.image ?? null,
            url: open.url ?? "",
            kind: open.kind ?? "patch",
          }}
          locale={locale}
          game={game}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  );
}
