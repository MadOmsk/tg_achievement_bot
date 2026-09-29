import { ru, type TranslationKey } from "./locales/ru";
import { en } from "./locales/en";
import type { TimezoneOption } from "../components/shared/constants/timezones";
import { RARITY_MODES } from "../components/shared/constants/rarity";

export type Locale = "ru" | "en";

const catalogs = { ru, en };

export function t(locale: string, key: TranslationKey): string {
  const cat = locale === "en" ? catalogs.en : catalogs.ru;
  return cat[key];
}

export function formatOffset(minutes: number | null | undefined, locale: string): string {
  if (minutes == null) return t(locale, "tzUnset");
  const sign = minutes >= 0 ? "+" : "−";
  const abs = Math.abs(minutes);
  const h = Math.floor(abs / 60);
  const m = abs % 60;
  return m ? `UTC${sign}${h}:${String(m).padStart(2, "0")}` : `UTC${sign}${h}`;
}

// A known offset (TIMEZONES) names its city through a locale key; a custom
// offset a chat/person typed in has no city, only the UTC±H:MM itself.
export function timezoneLabel(
  entry: TimezoneOption | { min: number; label: string },
  locale: string,
): string {
  return "key" in entry ? t(locale, entry.key) : entry.label;
}

export function rarityLabel(mode: string | null, locale: string): string {
  if (mode === RARITY_MODES.RARE) return t(locale, "rarityRare");
  if (mode === RARITY_MODES.HIDDEN) return t(locale, "rarityHidden");
  return t(locale, "rarityAll");
}

export function digestLabel(threshold: number | null, locale: string): string {
  if (threshold == null) return "—";
  if (threshold >= 99) return t(locale, "never");
  return String(threshold);
}

export function dayKey(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

export function dayLabel(iso: string | null, locale: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const start = (value: Date) => new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
  const diff = Math.round((start(now) - start(d)) / 86_400_000);
  if (diff === 0) return t(locale, "dayToday");
  if (diff === 1) return t(locale, "dayYesterday");
  return d.toLocaleDateString(locale === "en" ? "en-GB" : "ru-RU", {
    day: "numeric",
    month: "long",
    year: d.getFullYear() === now.getFullYear() ? undefined : "numeric",
  });
}

export function timeAgo(iso: string | null, locale: string): string {
  if (!iso) return "";
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 2) return t(locale, "justNow");
  if (mins < 60) return `${mins} ${t(locale, "minutesAgo")}`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} ${t(locale, "hoursAgo")}`;
  return `${Math.round(hours / 24)} ${t(locale, "daysAgo")}`;
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
