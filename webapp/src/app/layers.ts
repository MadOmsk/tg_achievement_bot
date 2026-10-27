import type { GameRef, NewsItem } from "../api";
import type { AdminScreen } from "../core/constants";
import type { Video } from "../ui/VideoPlayer";

/** An achievement as its own page shows it, from whichever list opened it. */
export type AchView = {
  key: string;
  name: string;
  description: string | null;
  icon: string | null;
  rarity: number | null;
  gamerscore: number | null;
  trophy: string | null;
  /** Xbox's Mythic (the last of a base list); PSN's platinum is the same tier. */
  mythic?: boolean;
  secret: boolean;
  unlockedAt: string | null;
  platform: string;
  titleId: string;
  achievementId: string;
  game: string | null;
  gameIcon: string | null;
  person: { id: number; name: string } | null;
  /** Everybody who earned it together, the first of them `person`. */
  together?: { id: number; name: string; at: string | null }[];
};

export type SettingsPaneName =
  | "root"
  | "profile"
  | "accounts"
  | "publishing"
  | "privacy"
  | "logins"
  | "notifications"
  | "general"
  | "appearance"
  | "invites";

/** Everything that opens over the tabs, topmost last. */
export type Layer =
  | { kind: "game"; ref: GameRef }
  | {
      kind: "achievements";
      platform: string;
      titleId: string;
      name: string | null;
      /** The game's cover the page opening it already shows. */
      cover?: string | null;
      person: { id: number; name: string } | null;
      /** The other platforms the person played the game on, to switch to. */
      lists?: { platform: string; title_id: string; count?: number; total?: number | null }[];
    }
  | { kind: "achievement"; ach: AchView }
  | { kind: "pass" }
  | { kind: "gallery"; game: string; cover: string | null; videos: Video[]; screenshots: string[] }
  | {
      kind: "achievementRef";
      platform: string;
      titleId: string;
      achievementId: string;
      person: { id: number; name: string } | null;
    }
  | { kind: "person"; personId: number }
  | { kind: "follows"; personId: number | null; which: "following" | "followers" | "friends" | "blocked" }
  | {
      kind: "news";
      appid: number;
      gid: string;
      item: NewsItem | null;
      game: { platform: string; title_id: string; name: string | null; icon_url: string | null } | null;
    }
  | { kind: "notifications" }
  | { kind: "search" }
  | { kind: "settings"; pane: SettingsPaneName }
  | { kind: "connect"; platform: "steam" | "psn" }
  | { kind: "admin"; screen: AdminScreen | null };

export type Tab = "home" | "feed" | "summary";

export const TABS: Tab[] = ["home", "feed", "summary"];
