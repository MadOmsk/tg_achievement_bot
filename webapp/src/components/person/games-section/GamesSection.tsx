import { useEffect, useState } from "react";
import type { FeedItem } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Dropdown, DropdownArrow, Icon, PlayedGamesSkel } from "../../shared/lib";
import { currentMonth, formatMonth } from "../../club/utils";
import { PlayedGames } from "../played-games/PlayedGames";
import "./GamesSection.css";

/**
 * The games a person played in a month, with the month picked in the block's
 * own head (owner, 2026-10-09) — the only month picker on Home and a profile.
 * Picking it moves this list alone; the gallery above stays on the month now.
 * The sort sits left of it: by date, or by how far each game got.
 */
export function GamesSection({
  items,
  months,
  liveMonth,
  locale,
  load,
}: {
  /** This month's achievements, already loaded with the page. */
  items: FeedItem[];
  /** Every month with achievements, newest first. */
  months: string[];
  liveMonth?: string;
  locale: Locale;
  /** A past month's achievements. */
  load: (month: string) => Promise<FeedItem[]>;
}) {
  const now = liveMonth || months[0] || currentMonth();
  const [month, setMonth] = useState(now);
  const [sort, setSort] = useState<"recent" | "progress">("recent");
  const [past, setPast] = useState<{ month: string; items: FeedItem[] } | null>(null);
  const busy = month !== now && past?.month !== month;

  useEffect(() => {
    if (month === now) return;
    let cancelled = false;
    load(month)
      .then((rows) => {
        if (!cancelled) setPast({ month, items: rows });
      })
      .catch(() => {
        if (!cancelled) setPast({ month, items: [] });
      });
    return () => {
      cancelled = true;
    };
    // `load` is a fresh closure on every render; the month is what is asked for.
  }, [month, now]);

  const shown = month === now ? items : (past?.items ?? []);
  const count = new Set(shown.filter((row) => row.game).map((row) => `${row.platform}:${row.title_id}`)).size;
  const choices = months.includes(now) ? months : [now, ...months];

  return (
    <>
      <div className="section-head achievements-head">
        <span className="section-title-group">
          <h1 className="kicker" style={{ margin: 0 }}>
            {t(locale, "games")}
          </h1>
          {!busy && count > 0 && <span className="section-count">{count}</span>}
        </span>
        <span className="games-tools">
        {!busy && count > 1 && (
          <button
            type="button"
            className="sort-toggle"
            aria-label={t(locale, sort === "recent" ? "sortProgress" : "sortRecent")}
            onClick={() => setSort((cur) => (cur === "recent" ? "progress" : "recent"))}
          >
            <Icon name={sort === "recent" ? "sort" : "stats"} size={18} />
          </button>
        )}
        {choices.length > 1 && (
          <Dropdown
            className="dd-trigger games-month"
            value={month}
            options={choices.map((m) => ({
              value: m,
              label: formatMonth(m, locale, "sheet"),
              hint: m === now ? t(locale, "nowMonth") : undefined,
            }))}
            onChange={setMonth}
            trigger={
              <>
                {formatMonth(month, locale, "chip")}
                <DropdownArrow />
              </>
            }
          />
        )}
        </span>
      </div>
      {busy ? (
        <PlayedGamesSkel />
      ) : shown.length > 0 ? (
        <PlayedGames items={shown} locale={locale} sort={sort} />
      ) : (
        <p className="games-empty">{t(locale, month === now ? "emptyTitleNow" : "emptyTitlePast")}</p>
      )}
    </>
  );
}
