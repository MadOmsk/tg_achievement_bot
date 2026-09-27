import type { TranslationKey } from "../../../i18n";

export interface TimezoneOption {
  min: number;
  key: TranslationKey;
}

// City names live in the locale files (i18n/locales/*.ts, keys tzM480..tzP720)
// like every other piece of user-visible text — this table only says which
// offset maps to which key, in display order.
export const TIMEZONES: readonly TimezoneOption[] = [
  { min: -480, key: "tzM480" },
  { min: -300, key: "tzM300" },
  { min: 0, key: "tz0" },
  { min: 60, key: "tzP60" },
  { min: 120, key: "tzP120" },
  { min: 180, key: "tzP180" },
  { min: 240, key: "tzP240" },
  { min: 300, key: "tzP300" },
  { min: 360, key: "tzP360" },
  { min: 420, key: "tzP420" },
  { min: 480, key: "tzP480" },
  { min: 540, key: "tzP540" },
  { min: 600, key: "tzP600" },
  { min: 660, key: "tzP660" },
  { min: 720, key: "tzP720" },
] as const;
