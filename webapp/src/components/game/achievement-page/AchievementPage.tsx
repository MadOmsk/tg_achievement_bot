import type { AchievementTip, AchievementVideo, GameAchievement } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { ContentPage, Icon, TierDisc, asTier } from "../../shared/lib";
import { paragraphsOf } from "../post-text/postText";
import { RichLines, openUrl } from "../rich-text/RichText";
import { pickLocale } from "../utils";

/** "8 октября" — the year only when it is not this one. */
function longDay(iso: string, locale: Locale): string {
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
          <Icon name="forward" size={20} />
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

/** An achievement on a page of its own (owner, 2026-10-05), on the app's one
 * content page (`ContentPage`, owner 2026-10-12): its rarity and worth in the
 * bar, as a news post's page has its kind there; its picture; the game it is
 * in; the day it was earned, its name and what it asks; then how to get it —
 * the Steam guides' tip, whole, with
 * its pictures and videos — when there is one. */
export function AchievementPage({
  row,
  tip,
  videos,
  game,
  gameArt,
  gameProgress,
  onOpenGame,
  fallbackIcon,
  locale,
  onClose,
}: {
  row: GameAchievement;
  tip?: AchievementTip;
  /** Guide videos that name it, each from the moment it starts. */
  videos?: AchievementVideo[];
  /** The game's name. */
  game: string;
  /** The game's picture, for its line. */
  gameArt?: string | null;
  /** Opens the game; without it the game's line is only a label (the page
   * was opened from the game's own page). */
  onOpenGame?: () => void;
  /** How far along in the game the person whose page it is. */
  gameProgress?: { unlocked: number; total: number } | null;
  /** Shown when the achievement has no picture of its own. */
  fallbackIcon?: string | null;
  locale: Locale;
  onClose: () => void;
}) {
  const name = pickLocale(locale, row.name_ru, row.name_en, row.achievement_id) || t(locale, "secret");
  const description = pickLocale(locale, row.description_ru, row.description_en);
  const tier = asTier(row.trophy_type);

  const marks = [
    row.rarity_percent != null ? `${row.rarity_percent}%` : null,
    row.gamerscore && !tier ? `${row.gamerscore} G` : null,
  ].filter(Boolean);
  const earned =
    row.is_unlocked && row.unlocked_at
      ? `${t(locale, "achEarnedOn")} ${longDay(row.unlocked_at, locale)}`
      : t(locale, row.is_unlocked ? "achEarned" : "achNotEarned");

  return (
    <ContentPage
      kind={t(locale, "pageAchievement")}
      backLabel={t(locale, "back")}
      onClose={onClose}
      picture={row.icon_url}
      pictureKind="achievement"
      fallbackPicture={fallbackIcon}
      game={game ? { name: game, icon_url: gameArt ?? fallbackIcon ?? null, onOpen: onOpenGame, progress: gameProgress } : null}
      gameLabel={t(locale, "pageGame")}
      // Its rarity and worth at the bar's right, as the game page shows its
      // score; the day it was earned on the date line, as a post's day.
      aside={
        marks.length > 0 || tier ? (
          <>
            {marks.join(" · ")}
            {tier && <TierDisc tier={tier} size={17} />}
          </>
        ) : undefined
      }
      date={earned}
      title={name}
      lead={description}
      resetKey={row.achievement_id}
    >
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
    </ContentPage>
  );
}
