import { useEffect, useState } from "react";
import { fetchGame, fetchGameGuides, type AchievementTip, type AchievementVideo, type FeedItem, type GameAchievement } from "../../../api";
import type { Locale } from "../../../i18n";
import { AchievementPage } from "./AchievementPage";

/** What a post already knows, drawn at once while the game's own row loads. */
function rowOf(item: FeedItem): GameAchievement {
  return {
    achievement_id: item.achievement_id,
    name_ru: item.name,
    name_en: item.name,
    description_ru: item.description,
    description_en: item.description,
    icon_url: item.icon_url,
    is_secret: item.is_secret,
    gamerscore: item.gamerscore,
    trophy_type: item.trophy_type,
    rarity_percent: item.rarity_percent,
    is_unlocked: true,
    unlocked_at: item.unlocked_at,
  };
}

/** An achievement from a post or a gallery, on its own page (owner,
 * 2026-10-09): the post's own fields first, then the game's row on the
 * author's progress and the guides' tip and videos as they come. */
export function AchievementLoader({
  data,
  locale,
  item,
  onClose,
}: {
  data: string;
  locale: Locale;
  item: FeedItem;
  onClose: () => void;
}) {
  const [row, setRow] = useState<GameAchievement>(() => rowOf(item));
  const [tip, setTip] = useState<AchievementTip | undefined>();
  const [videos, setVideos] = useState<AchievementVideo[] | undefined>();

  useEffect(() => {
    let cancelled = false;
    void fetchGame(data, item.platform, item.title_id, { personId: item.person_id })
      .then((res) => {
        const found = res.achievements?.find((a) => a.achievement_id === item.achievement_id);
        if (!cancelled && found) setRow(found);
      })
      .catch(() => undefined);
    void fetchGameGuides(data, item.platform, item.title_id)
      .then((res) => {
        if (cancelled) return;
        setTip(res.tips?.[item.achievement_id]);
        setVideos(res.videos?.[item.achievement_id]);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [data, item.platform, item.title_id, item.achievement_id, item.person_id]);

  return (
    <AchievementPage
      row={row}
      tip={tip}
      videos={videos}
      game={item.game ?? ""}
      fallbackIcon={item.game_icon_url}
      locale={locale}
      onClose={onClose}
    />
  );
}
