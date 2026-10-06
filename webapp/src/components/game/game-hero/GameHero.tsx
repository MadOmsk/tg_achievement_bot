import { useEffect, useState, type CSSProperties } from "react";
import { t, type Locale } from "../../../i18n";
import { CoverImg, FitImg, Icon, tick } from "../../shared/lib";

const CELEBRATED_KEY = "celebrated-games";
const SPARKS = 14;
// Where the twinkling stars stand round the medal: x, y (from its centre), size, delay.
const STARS: [string, string, string, string][] = [
  ["-74px", "-30px", "7px", "0s"],
  ["-58px", "26px", "5px", "1.1s"],
  ["66px", "-38px", "6px", "0.5s"],
  ["78px", "14px", "8px", "1.7s"],
  ["-24px", "-62px", "4px", "2.3s"],
  ["34px", "-64px", "5px", "0.9s"],
];

/** Whether this game's 100% was celebrated already on this device; marks it so. */
function firstTime(key: string): boolean {
  try {
    const seen = new Set<string>(JSON.parse(localStorage.getItem(CELEBRATED_KEY) ?? "[]"));
    if (seen.has(key)) return false;
    seen.add(key);
    localStorage.setItem(CELEBRATED_KEY, JSON.stringify([...seen].slice(-500)));
    return true;
  } catch {
    return false;
  }
}

function dayOf(iso: string, locale: Locale): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(locale === "en" ? "en-GB" : "ru-RU", {
    day: "numeric",
    month: "long",
    year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  });
}

/**
 * The top of a game's page: the picture across the full width (over a blurred
 * copy of itself for whatever its shape leaves bare) and, hanging off its lower
 * edge, how far along the person is — a plate with an achievement icon, a bar and
 * the percentage. A game with every achievement earned gets a platinum medal
 * instead (owner, 2026-10-06: beautiful but laconic, and a real joy): a metal
 * disc on an iridescent rim, a soft glow, the day it was finished; and
 * the first time one's own finished game is opened, the medal pops in with a
 * burst of sparks and a tap of the phone — once per game on this device.
 */
export function GameHero({
  cover,
  pct,
  total,
  isCompleted,
  loading = false,
  locale,
  compact = false,
  completedAt,
  celebrateKey,
}: {
  cover: string | null;
  pct: number;
  total: number;
  isCompleted: boolean;
  /** The game is still being fetched: an empty plate stands in. */
  loading?: boolean;
  locale: Locale;
  /** Collapsed (HeroPeek at rest): a plain platinum plate instead of the big
   * glowing medal — the rays and shine are sized for the full picture and
   * only make sense once it's actually open. */
  compact?: boolean;
  /** When the last achievement was earned (the day it was finished, at 100%). */
  completedAt?: string | null;
  /** Set on one's own finished game: its first opening is celebrated. */
  celebrateKey?: string | null;
}) {
  const done = isCompleted && !loading;
  const [party, setParty] = useState(false);

  useEffect(() => {
    if (!done || !celebrateKey || !firstTime(celebrateKey)) return;
    setParty(true);
    tick();
    const end = window.setTimeout(() => setParty(false), 1800);
    return () => window.clearTimeout(end);
  }, [done, celebrateKey]);

  return (
    <div
      className={[
        "game-hero",
        done && "is-done",
        done && compact && "is-compact",
        (done || loading || total > 0) && "has-medal",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="game-cover">
        <CoverImg src={cover} kind="game" className="game-cover-back" />
        <FitImg src={cover} mode="width" kind="game" />
        {done && <i className="game-edge" aria-hidden />}
      </div>
      {done ? (
        <div className={party ? "game-medal is-party" : "game-medal"}>
          {/* A few stars twinkling round it, out of step. */}
          <span className="game-stars" aria-hidden>
            {STARS.map(([x, y, s, d], i) => (
              <i key={i} style={{ left: x, top: y, width: s, height: s, animationDelay: d } as CSSProperties} />
            ))}
          </span>
          <span className="game-medal-ring" aria-hidden>
            <span className="game-medal-disc">
              <Icon name="cup" size={38} filled />
            </span>
          </span>
          {party && (
            <span className="game-sparks" aria-hidden>
              {Array.from({ length: SPARKS }, (_, i) => (
                <i key={i} style={{ "--a": `${(360 / SPARKS) * i}deg`, "--d": `${i % 3}` } as CSSProperties} />
              ))}
            </span>
          )}
          <span className="game-medal-label">{t(locale, "gameCompleted")}</span>
          {completedAt && <span className="game-medal-date">{dayOf(completedAt, locale)}</span>}
        </div>
      ) : (
        (loading || total > 0) && (
          // Not finished yet: the medal's own shape, its rim filled as far as
          // the person got (owner, 2026-10-06), so the two read as one thing.
          <div className="game-medal is-progress">
            <span
              className="game-medal-ring"
              style={{ "--p": loading ? 0 : Math.min(100, Math.max(0, pct)) } as CSSProperties}
              aria-hidden
            >
              <span className="game-medal-disc">
                <Icon name="cup" size={34} filled />
              </span>
              {/* A light at the end of the filled arc. */}
              {!loading && pct > 0 && <i className="game-medal-tip" />}
            </span>
            {loading ? (
              <span className="skel game-medal-pct-skel" aria-hidden />
            ) : (
              // The percentage under the rim, and the day of the last
              // achievement as on the platinum; how many is in the tab's title.
              <>
                <span className="game-medal-label">{pct}%</span>
                {completedAt && <span className="game-medal-date">{dayOf(completedAt, locale)}</span>}
              </>
            )}
          </div>
        )
      )}
    </div>
  );
}

