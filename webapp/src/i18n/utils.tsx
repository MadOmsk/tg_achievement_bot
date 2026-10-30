import { ru, type TranslationKey } from "./locales/ru";
import { en } from "./locales/en";
import { RARITY_MODES } from "../core/constants/rarity";

export type Locale = "ru" | "en";

const catalogs = { ru, en };

export function t(locale: string, key: TranslationKey): string {
  const cat = locale === "en" ? catalogs.en : catalogs.ru;
  return cat[key];
}

/** A counted word: Russian's one/few/many ("1 достижение, 3 достижения, 5
 * достижений"), English's one/other (the `few` key doubles as plural). */
export function plural(
  locale: string,
  n: number,
  keys: [TranslationKey, TranslationKey, TranslationKey],
): string {
  const [one, few, many] = keys;
  if (locale === "en") return t(locale, n === 1 ? one : few);
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return t(locale, one);
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return t(locale, few);
  return t(locale, many);
}

/** A number as the reader writes it: "2 100", "2,100". */
export function num(n: number | null | undefined, locale: string): string {
  return (n ?? 0).toLocaleString(locale === "en" ? "en-US" : "ru-RU");
}

/** A rarity as a percentage: "0,04 %", "21,7 %". */
export function pct(value: number | null | undefined, locale: string): string {
  if (value == null) return "";
  const digits = value < 1 ? 2 : value < 10 ? 1 : 0;
  return `${value.toLocaleString(locale === "en" ? "en-US" : "ru-RU", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  })} %`;
}

export function formatOffset(minutes: number | null | undefined, locale: string): string {
  if (minutes == null) return t(locale, "tzUnset");
  const sign = minutes >= 0 ? "+" : "−";
  const abs = Math.abs(minutes);
  const h = Math.floor(abs / 60);
  const m = abs % 60;
  return m ? `UTC${sign}${h}:${String(m).padStart(2, "0")}` : `UTC${sign}${h}`;
}

export function rarityLabel(mode: string | null, locale: string): string {
  if (mode === RARITY_MODES.RARE) return t(locale, "rarityRare");
  if (mode === RARITY_MODES.HIDDEN) return t(locale, "rarityHidden");
  return t(locale, "rarityAll");
}

export function dayKey(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

/** A day as people say it: today, yesterday, «4 дн назад» this month, else
 * its date. `exact` keeps the date where a time of day follows it. */
export function dayLabel(iso: string | null, locale: string, exact = false): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const start = (value: Date) => new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
  const diff = Math.round((start(now) - start(d)) / 86_400_000);
  if (diff === 0) return t(locale, "dayToday");
  if (diff === 1) return t(locale, "dayYesterday");
  // This month's days count back from today (owner, 2026-10-29).
  if (!exact && diff > 1 && d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth()) {
    return `${diff} ${t(locale, "daysBack")}`;
  }
  return d.toLocaleDateString(locale === "en" ? "en-GB" : "ru-RU", {
    day: "numeric",
    month: "long",
    year: d.getFullYear() === now.getFullYear() ? undefined : "numeric",
  });
}

const MONTHS_RU = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
const MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** When something happened, as people say it (owner, 2026-10-29): «12 мин
 * назад» within the hour, «5 ч назад» within the day, «4 дн назад» this month,
 * else its date and time — or, `short` (a list's narrow column), its day and
 * month alone, «4 сен», the year only when it is another. */
export function whenLabel(iso: string | null, locale: string, short = false): string {
  if (!iso) return "";
  // A day with no time of its own (a release day) is a day in the reader's
  // calendar, never «5 ч назад».
  const dayOnly = iso.length <= 10;
  const d = new Date(dayOnly ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  if (dayOnly) {
    const startOf = (v: Date) => new Date(v.getFullYear(), v.getMonth(), v.getDate()).getTime();
    const back = Math.round((startOf(now) - startOf(d)) / 86_400_000);
    if (back === 0) return t(locale, "dayToday");
    if (back > 0 && d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth()) {
      return `${back} ${t(locale, "daysBack")}`;
    }
  }
  // A moment that has passed counts back from now; a day to come is a date.
  if (!dayOnly && d.getTime() <= now.getTime()) {
    const mins = Math.floor((now.getTime() - d.getTime()) / 60000);
    if (mins < 1) return t(locale, "justNow");
    if (mins < 60) return `${mins} ${t(locale, "minutesAgo")}`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours} ${t(locale, "hoursAgo")}`;
    if (d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth()) {
      return `${Math.floor(hours / 24)} ${t(locale, "daysBack")}`;
    }
  }
  if (short) {
    // Three letters a month, no dots, as «дн» and «мин»: «9 сен», «4 дек 2025».
    const month = (locale === "en" ? MONTHS_EN : MONTHS_RU)[d.getMonth()];
    return `${d.getDate()} ${month}${d.getFullYear() === now.getFullYear() ? "" : ` ${d.getFullYear()}`}`;
  }
  const date = d.toLocaleDateString(locale === "en" ? "en-GB" : "ru-RU", {
    day: "numeric",
    month: "long",
    year: d.getFullYear() === now.getFullYear() ? undefined : "numeric",
  });
  if (dayOnly) return date;
  const time = d.toLocaleTimeString(locale === "en" ? "en-GB" : "ru-RU", { hour: "2-digit", minute: "2-digit" });
  return `${date}, ${time}`;
}

export function timeAgo(iso: string | null, locale: string): string {
  if (!iso) return "";
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 2) return t(locale, "justNow");
  if (mins < 60) return `${mins} ${t(locale, "minutesAgo")}`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} ${t(locale, "hoursAgo")}`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} ${t(locale, "daysAgo")}`;
  if (days < 365) return `${Math.round(days / 30)} ${t(locale, "monthsAgo")}`;
  return `${Math.round(days / 365)} ${t(locale, "yearsAgo")}`;
}

export function platformMark(platform: string): string {
  if (platform === "steam") return "steam";
  if (platform === "psn") return "psn";
  return "xbox";
}

export function scorePlus(score: number | null | undefined): string {
  if (!score) return "";
  return ` (+${score.toLocaleString("ru-RU")} G)`;
}

export function formatWhen(iso: string | null | undefined, locale: string): string {
  if (!iso) return t(locale, "never");
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return t(locale, "never");
  return date.toLocaleString(locale === "en" ? "en-GB" : "ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function platformLabel(platform: string, locale: string): string {
  if (platform === "steam") return t(locale, "platformSteam");
  if (platform === "psn") return t(locale, "platformPsn");
  return t(locale, "platformXbox");
}
