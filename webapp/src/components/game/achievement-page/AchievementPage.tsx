import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import type { AchievementTip, AchievementVideo, GameAchievement } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, CoverImg, FitImg, Icon, TierDisc, asTier, useImageRatio, openImage } from "../../shared/lib";
import { paragraphsOf } from "../patch-notes/PatchNotes";
import { RichLines, openUrl } from "../rich-text/RichText";
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

function clock(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

/** A guide video, opened on YouTube at the moment it is about. */
/** A video's title without the game it begins with — the page names it already —
 * and without the channel's "🏆 Trophy / Achievement Guide" tail. */
function shortTitle(title: string, game: string): string {
  let text = title.split("🏆")[0].trim();
  const lower = text.toLowerCase();
  const prefix = `${game.toLowerCase()} - `;
  if (lower.startsWith(prefix)) text = text.slice(prefix.length);
  return text.replace(/\s+[-–—]\s*$/, "").trim() || title;
}

function GuideVideo({ video, game, locale }: { video: AchievementVideo; game: string; locale: Locale }) {
  const from = video.start > 0 ? `${t(locale, "achVideoFrom")} ${clock(video.start)}` : null;
  const byline = [video.channel, video.part ? `${t(locale, "achVideoPart")} ${video.part}` : null]
    .filter(Boolean)
    .join(" · ");
  return (
    <button type="button" className="guide-video" onClick={() => openUrl(video.url)}>
      <span className="guide-video-pic">
        <img src={`https://i.ytimg.com/vi/${video.id}/mqdefault.jpg`} alt="" loading="lazy" />
        <span className="guide-video-play" aria-hidden>
          <Icon name="play" size={18} />
        </span>
        {from && <span className="guide-video-from">{from}</span>}
      </span>
      <span className="guide-video-copy">
        <span className="guide-video-title" lang="en">
          {shortTitle(video.title, game)}
        </span>
        {byline && <span className="guide-video-by">{byline}</span>}
      </span>
    </button>
  );
}

/** An achievement on a page of its own (owner, 2026-10-05), laid out as a
 * post's page: the game named in the head; its picture, all of it; its rarity,
 * its points or trophy, and when it was earned; its name and description; then
 * how to get it — the Steam guides' tip, whole, with its pictures and videos —
 * when there is one. */
export function AchievementPage({
  row,
  tip,
  videos,
  game,
  fallbackIcon,
  locale,
  onClose,
}: {
  row: GameAchievement;
  tip?: AchievementTip;
  /** Guide videos that name it, each from the moment it starts. */
  videos?: AchievementVideo[];
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
        {(tip || videos?.length) && (
          <section className="post-page-section">
            <h2>{t(locale, "achHowTo")}</h2>
            {videos && videos.length > 0 && (
              <div className="guide-videos">
                {videos.map((video) => (
                  <GuideVideo key={`${video.id}:${video.start}`} video={video} game={game} locale={locale} />
                ))}
              </div>
            )}
            {tip && (
              <>
                <div className="post-page-text">
                  {paragraphsOf(tip.text).map((paragraph, i) => (
                    <p key={i}>
                      <RichLines text={paragraph} className="rich-line" />
                    </p>
                  ))}
                </div>
                <p className="post-page-source">{t(locale, "achTipSource")}</p>
              </>
            )}
          </section>
        )}
      </article>
    </div>,
    document.body,
  );
}
