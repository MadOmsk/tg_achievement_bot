import type { MeResponse } from "../../../../api";
import { t, type Locale } from "../../../../i18n";
import { PlatformLogo } from "../platform/Platform";
import { Sheet } from "../sheet/Sheet";
import { TierMedals, type TierCounts } from "../tier-medals/TierMedals";
import "./ScoreCup.css";

export type ScoreCupLine = {
  platform: string;
  count: number;
  day?: number | null;
  month?: number | null;
  extra?: string | null;
  unit?: string | null;
  tiers?: TierCounts | null;
};

export function ScoreCup({
  locale,
  lines,
  onEmpty,
  markSize = 18,
  open,
  onOpenChange,
}: {
  locale: Locale;
  onEmpty?: () => void;
  lines: ScoreCupLine[];
  /** The size of each platform mark — smaller where the cup sits inline,
   * next to the nick, rather than as its own button. */
  markSize?: number;
  /** Controlled: the nick beside it opens the same sheet. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  if (lines.length === 0) {
    if (!onEmpty) return null;
    return (
      <div className="score-cup">
        <button type="button" className="score-connect" onClick={onEmpty}>
          {t(locale, "join")}
        </button>
      </div>
    );
  }
  return (
    <div className="score-cup">
      <button
        type="button"
        className="score-cup-btn"
        onClick={(e) => {
          e.stopPropagation();
          onOpenChange(true);
        }}
        aria-expanded={open}
        aria-label={t(locale, "scoreSummary")}
      >
        <span className="score-plats">
          {lines.map((line) => (
            <PlatformLogo key={line.platform} platform={line.platform} size={markSize} />
          ))}
        </span>
      </button>
      {open && (
        <Sheet onClose={() => onOpenChange(false)}>
          <div className="sheet-content score-sheet">
            <h2>{t(locale, "scoreSummary")}</h2>
            {lines.map((line) => (
              <div key={line.platform} className="score-row">
                <PlatformLogo platform={line.platform} size={22} />
                <strong>
                  {line.count.toLocaleString("ru-RU")}
                  {line.unit && <small>{line.unit}</small>}
                </strong>
                {line.tiers && <TierMedals counts={line.tiers} />}
                {(line.month != null && line.day != null) && (
                  <span className="score-meta">
                    {line.month.toLocaleString("ru-RU")} {t(locale, "homeMonthShort")}
                    <i aria-hidden> · </i>
                    {line.day.toLocaleString("ru-RU")} {t(locale, "homeDayShort")}
                  </span>
                )}
              </div>
            ))}
          </div>
        </Sheet>
      )}
    </div>
  );
}

export function meScoreLines(
  me: MeResponse,
  locale: Locale,
): ScoreCupLine[] {
  const lines: ScoreCupLine[] = [];
  if (me.xbox.linked) {
    lines.push({
      platform: "xbox",
      count: me.xbox.gamerscore ?? me.xbox.achievement_count,
      day: me.xbox.day,
      month: me.xbox.month,
      extra: me.xbox.completed_games ? `🌀 ${me.xbox.completed_games}` : null,
      unit: me.xbox.gamerscore != null ? "G" : null,
    });
  }
  if (me.psn.linked) {
    lines.push({
      platform: "psn",
      count: me.psn.trophy_count,
      day: me.psn.day,
      month: me.psn.month,
      extra: me.psn.trophy_level != null ? `${t(locale, "level")} ${me.psn.trophy_level}` : null,
      tiers: {
        bronze: me.psn.bronze,
        silver: me.psn.silver,
        gold: me.psn.gold,
        platinum: me.psn.platinum_count,
      },
    });
  }
  if (me.steam.linked) {
    lines.push({
      platform: "steam",
      count: me.steam.achievement_count,
      day: me.steam.day,
      month: me.steam.month,
      extra: me.steam.completed_games ? `👾 ${me.steam.completed_games}` : null,
    });
  }
  return lines;
}
