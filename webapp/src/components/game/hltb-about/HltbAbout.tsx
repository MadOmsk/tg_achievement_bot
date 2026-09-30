import { useState, type ReactNode } from "react";
import type { GameHltb, HltbTimeName } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Icon } from "../../shared/lib";

const MAIN_TIMES: HltbTimeName[] = ["main", "extra", "completionist"];

const TIME_LABELS: Record<HltbTimeName, Parameters<typeof t>[1]> = {
  main: "hltbMain",
  extra: "hltbExtra",
  completionist: "hltbComplete",
  all: "hltbAll",
  coop: "hltbCoop",
  multi: "hltbMulti",
};

const MODE_LABELS = {
  single: "hltbModeSingle",
  coop: "hltbModeCoop",
  multi: "hltbModeMulti",
} as const;

/** 0.7 → "42 мин", 4.25 → "4,3", 15.81 → "16" — a tenth only where it
 * still matters, never HLTB's own two decimals. */
function amount(hours: number, locale: Locale): string {
  return hours.toLocaleString(locale === "ru" ? "ru-RU" : "en-US", {
    maximumFractionDigits: hours < 10 ? 1 : 0,
  });
}

function duration(hours: number, locale: Locale): string {
  return hours < 1
    ? `${Math.max(1, Math.round(hours * 60))} ${t(locale, "minutes")}`
    : `${amount(hours, locale)} ${t(locale, "hours")}`;
}

function releaseDate(iso: string, locale: Locale): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(locale === "ru" ? "ru-RU" : "en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** The "Об игре" tab: HLTB's hours, then everything else its page knows. */
export function HltbAbout({
  hltb,
  locale,
}: {
  hltb: GameHltb;
  locale: Locale;
}) {
  const details = hltb.details ?? {};
  const times = details.times ?? {};
  const averages: Partial<Record<HltbTimeName, number | null>> = {
    main: hltb.main_hours,
    extra: hltb.extra_hours,
    completionist: hltb.completionist_hours,
    all: times.all?.average,
    coop: times.coop?.average,
    multi: times.multi?.average,
  };
  const shownTimes = (Object.keys(TIME_LABELS) as HltbTimeName[]).filter(
    (name) => averages[name] != null,
  );

  const releases = details.releases ?? {};
  const world = releases.world;
  const regional = (["na", "eu", "jp"] as const)
    .filter((region) => releases[region] && releases[region] !== world)
    .map(
      (region) =>
        `${region.toUpperCase()} ${releaseDate(releases[region]!, locale)}`,
    );

  const rows: Array<[string, ReactNode]> = [];
  if (hltb.genre) rows.push([t(locale, "hltbGenre"), hltb.genre]);
  if (world || regional.length || hltb.release_year) {
    rows.push([
      t(locale, "hltbRelease"),
      [world ? releaseDate(world, locale) : hltb.release_year, ...regional]
        .filter(Boolean)
        .join(" · "),
    ]);
  }
  if (details.publisher && details.publisher !== details.developer) {
    rows.push([t(locale, "hltbPublisher"), details.publisher]);
  }
  if (details.developer)
    rows.push([t(locale, "hltbDeveloper"), details.developer]);
  if (details.modes?.length) {
    rows.push([
      t(locale, "hltbModes"),
      details.modes.map((m) => t(locale, MODE_LABELS[m])).join(", "),
    ]);
  }
  if (details.review_score != null) {
    rows.push([
      t(locale, "hltbScore"),
      <span className="about-game-score">
        <b>{details.review_score}</b>
        <small>/100</small>
      </span>,
    ]);
  }
  // The hours are the table's last row: the three everyone means by "how
  // long is it" on one line, and a tap unfolds every time as rows of the
  // same table. The description follows.
  const mainTimes = shownTimes.filter((name) => MAIN_TIMES.includes(name));
  const [open, setOpen] = useState(false);
  const toggle = () => setOpen((cur) => !cur);

  return (
    <>
      {(rows.length > 0 || shownTimes.length > 0) && (
        <dl className="about-game-facts">
          {rows.map(([label, value]) => (
            <div key={label} className="about-game-fact">
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
          {shownTimes.length > 0 && (
            <div
              className="about-game-fact is-toggle"
              role="button"
              tabIndex={0}
              aria-expanded={open}
              onClick={toggle}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") toggle();
              }}
            >
              <dt>{t(locale, "hltbTime")}</dt>
              <dd>
                {(mainTimes.length ? mainTimes : shownTimes)
                  .map((name) => duration(averages[name]!, locale))
                  .join(" · ")}
                <span
                  className={
                    open ? "about-game-more is-open" : "about-game-more"
                  }
                >
                  <Icon name="forward" size={16} />
                </span>
              </dd>
            </div>
          )}
          {open &&
            shownTimes.map((name) => (
              <div key={name} className="about-game-fact is-sub">
                <dt>{t(locale, TIME_LABELS[name])}</dt>
                <dd>{duration(averages[name]!, locale)}</dd>
              </div>
            ))}
        </dl>
      )}
      {hltb.description && (
        <p className="about-game-desc">{hltb.description}</p>
      )}
    </>
  );
}
