import type { GameGroup } from "../../api";
import { t, timeAgo, type Locale } from "../../i18n";
import { TROPHY_BADGES } from "../shared/constants";

export type FilterType = "all" | "unlocked" | "locked";

export function pickLocale(
  locale: Locale,
  ru: string | null | undefined,
  en: string | null | undefined,
  fallback: string | null | undefined = null,
): string {
  const primary = locale === "en" ? en : ru;
  const secondary = locale === "en" ? ru : en;
  return (primary || secondary || fallback || "").trim();
}

export function trophyBadge(type: string | null | undefined): string | null {
  if (!type) return null;
  const key = type.toLowerCase();
  if (key === "bronze") return TROPHY_BADGES.BRONZE;
  if (key === "silver") return TROPHY_BADGES.SILVER;
  if (key === "gold") return TROPHY_BADGES.GOLD;
  if (key === "platinum") return TROPHY_BADGES.PLATINUM;
  return null;
}

export function groupLabel(
  group: GameGroup,
  locale: Locale,
  gameName: string,
): string {
  const raw = pickLocale(locale, group.name_ru, group.name_en, group.name);
  if (!raw) return t(locale, "mainGame");
  const game = gameName.trim().toLowerCase();
  if (game && raw.trim().toLowerCase() === game) {
    return t(locale, "mainGame");
  }
  if (game && raw.toLowerCase().startsWith(game)) {
    const rest = raw.slice(gameName.length).replace(/^[\s:·\-—]+/, "").trim();
    if (rest) return rest;
  }
  return raw;
}

export function formatUnlockDate(
  iso: string | null | undefined,
  locale: Locale,
): string | null {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    const now = Date.now();
    const diffHours = (now - d.getTime()) / (1000 * 60 * 60);
    if (diffHours < 48) {
      return timeAgo(iso, locale);
    }
    const loc = locale === "en" ? "en-US" : "ru-RU";
    return d.toLocaleDateString(loc, {
      day: "numeric",
      month: "short",
    });
  } catch {
    return null;
  }
}
