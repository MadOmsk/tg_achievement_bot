// The one place every screen name is spelled out as a string literal —
// everywhere else (App.tsx's routing, Club.tsx's own pane switch, the
// dock's nav) reads one of these constants instead of retyping the word.
export const SCREEN_NAMES = {
  HOME: "home",
  FEED: "feed",
  SUMMARY: "summary",
  SETTINGS: "settings",
  ADMIN: "admin",
  CONNECT_STEAM: "connect-steam",
  CONNECT_PSN: "connect-psn",
} as const;

export const SCREENS = {
  home: { name: SCREEN_NAMES.HOME },
  feed: { name: SCREEN_NAMES.FEED },
  summary: { name: SCREEN_NAMES.SUMMARY },
  settings: { name: SCREEN_NAMES.SETTINGS },
  admin: { name: SCREEN_NAMES.ADMIN },
  "connect-steam": { name: SCREEN_NAMES.CONNECT_STEAM },
  "connect-psn": { name: SCREEN_NAMES.CONNECT_PSN },
} as const;

export type Screen = (typeof SCREENS)[keyof typeof SCREENS];
export type DockTab =
  | typeof SCREEN_NAMES.FEED
  | typeof SCREEN_NAMES.SUMMARY
  | typeof SCREEN_NAMES.SETTINGS;

// The three tabs a deep link (?t=... or the Mini App start_param) may open
// straight into, and the three panes Club.tsx itself switches between —
// the same set, in the order they fall back through in launchContext().
export const LAUNCH_TABS = [
  SCREEN_NAMES.HOME,
  SCREEN_NAMES.FEED,
  SCREEN_NAMES.SUMMARY,
] as const;
export type LaunchTab = (typeof LAUNCH_TABS)[number];
export type ClubPane = LaunchTab;

export function asLaunchTab(value: string | null): LaunchTab {
  return (LAUNCH_TABS as readonly string[]).includes(value ?? "")
    ? (value as LaunchTab)
    : SCREEN_NAMES.HOME;
}
