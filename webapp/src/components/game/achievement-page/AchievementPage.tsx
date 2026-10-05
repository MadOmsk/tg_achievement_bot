import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import type { AchievementTip, GameAchievement } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, CoverImg, FitImg, TierDisc, asTier, useImageRatio, openImage } from "../../shared/lib";
import { paragraphsOf } from "../patch-notes/PatchNotes";
import { RichLines } from "../rich-text/RichText";
import { pickLocale } from "../utils";
import "../post-page/PostPage.css";

function dayOf(iso: string, locale: Locale): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(locale === "en" ? "en-GB" : "ru-RU", {
    day: "numeric",
    month: "long",
    year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  });
}

/** An achievement on a page of its own (owner, 2026-10-05), laid out as a
 * post's page: the game named in the head; its picture, all of it; its rarity,
 * its points or trophy, and when it was earned; its name and description; then
 * how to get it — the Steam guides' tip, whole, with its pictures and videos —
 * when there is one. */
export function AchievementPage({
  row,
  tip,
  game,
  fallbackIcon,
  locale,
  onClose,
}: {
  row: GameAchievement;
  tip?: AchievementTip;
  /** The game's name, for the head. */
  game: string;
  /** Shown when the achievement has no picture of its own. */
  fallbackIcon?: string | null;
  locale: Locale;
  onClose: () => void;
}) {
  const page = useRef<HTMLDivElement>(null);
  const picture = row.icon_url || fallbackIcon || null;
  const ratio = useImageRatio(picture);
  const name = pickLocale(locale, row.name_ru, row.name_en, row.achievement_id) || t(locale, "secret");
  const description = pickLocale(locale, row.description_ru, row.description_en);
  const tier = asTier(row.trophy_type);
  const marks = [
    row.rarity_percent != null ? `${row.rarity_percent}%` : null,
    row.gamerscore && !tier ? `${row.gamerscore} G` : null,
  ].filter(Boolean);

  useEffect(() => {
    page.current?.scrollTo(0, 0);
  }, [row.achievement_id]);

  return createPortal(
    <div className="post-page" ref={page} data-no-pull>
      <BackHead
        title={game}
        backLabel={t(locale, "back")}
        onBack={onClose}
        aside={
          marks.length > 0 || tier ? (
            <>
              {marks.join(" · ")}
              {tier && <TierDisc tier={tier} size={17} />}
            </>
          ) : undefined
        }
      />
      <div className="post-page-pic" style={{ aspectRatio: ratio }} onClick={() => picture && openImage(picture)}>
        <CoverImg src={picture} kind="achievement" className="post-page-back" />
        <FitImg src={picture} kind="achievement" mode="contain" />
      </div>
      <article className="post-page-body">
        <div className="post-page-meta">
          <span className="post-page-date">
            {row.is_unlocked && row.unlocked_at
              ? `${t(locale, "achEarnedOn")} ${dayOf(row.unlocked_at, locale)}`
              : t(locale, row.is_unlocked ? "achEarned" : "achNotEarned")}
          </span>
        </div>
        <h1 className="post-page-title">{name}</h1>
        {description && <p className="post-page-lead">{description}</p>}
        {tip && (
          <section className="post-page-section">
            <h2>{t(locale, "achHowTo")}</h2>
            <div className="post-page-text">
              {paragraphsOf(tip.text).map((paragraph, i) => (
                <p key={i}>
                  <RichLines text={paragraph} className="rich-line" />
                </p>
              ))}
            </div>
            <p className="post-page-source">{t(locale, "achTipSource")}</p>
          </section>
        )}
      </article>
    </div>,
    document.body,
  );
}
