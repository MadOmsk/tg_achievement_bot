import { useEffect, useState } from "react";
import type { GamePatch } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Icon } from "../../shared/lib";
import { RichLines, withoutLinks } from "../rich-text/RichText";

const FRESH_DAYS = 14;
/** The post as paragraphs, list lines kept together: Steam posts put a blank
 * line between nearly every line, which is far too airy to read. */
function paragraphsOf(text: string): string[] {
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

function formatDate(iso: string, locale: Locale): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(locale === "ru" ? "ru-RU" : "en-US", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function isFresh(iso: string): boolean {
  const date = new Date(`${iso}T00:00:00`).getTime();
  return !Number.isNaN(date) && Date.now() - date < FRESH_DAYS * 86_400_000;
}

/** The "Обновления" tab: a game's latest patches from Steam, one soft card
 * each. A card shows the start of the post and opens in place to all of it. */
export function PatchNotes({
  patches,
  locale,
  onLayout,
}: {
  /** undefined: still being asked. */
  patches: GamePatch[] | undefined;
  locale: Locale;
  /** Called after the content changed height (loaded, or a card opened). */
  onLayout?: () => void;
}) {
  const [openDate, setOpenDate] = useState<string | null>(null);

  useEffect(() => {
    onLayout?.();
  }, [patches, openDate, onLayout]);

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

  return (
    <div className="patch-list">
      {patches.length === 0 && (
        <p className="empty">{t(locale, "patchesEmpty")}</p>
      )}
      {patches.map((patch) => {
        const key = `${patch.date}|${patch.title}`;
        const open = openDate === key;
        return (
          <div
            key={key}
            role="button"
            tabIndex={0}
            className={open ? "patch-card is-open" : "patch-card"}
            aria-expanded={open}
            onClick={() => setOpenDate(open ? null : key)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ")
                setOpenDate(open ? null : key);
            }}
          >
            <span className="patch-card-head">
              <span className="patch-card-date">
                {formatDate(patch.date, locale)}
              </span>
              {isFresh(patch.date) && (
                <span className="patch-card-new">
                  {t(locale, "patchesNew")}
                </span>
              )}
              <span className="patch-card-chevron">
                <Icon name="forward" size={16} />
              </span>
            </span>
            <span className="patch-card-name">{patch.title}</span>
            {patch.text &&
              (open ? (
                <span className="patch-card-body">
                  {paragraphsOf(patch.text).map((paragraph, i) => (
                    <span key={i} className="patch-card-p">
                      <RichLines text={paragraph} className="rich-line" />
                    </span>
                  ))}
                </span>
              ) : (
                <span className="patch-card-body is-preview">
                  {previewOf(patch.text)}
                </span>
              ))}
          </div>
        );
      })}
    </div>
  );
}
