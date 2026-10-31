import { gamesApi } from "../../api";
import { useApp } from "../../app/context";
import { useLoad } from "../../app/useLoad";
import { achOfList } from "../../app/views";
import { Button, Empty } from "../../ui/Controls";
import { Page } from "../../ui/Page";
import { AchievementPage } from "./AchievementPage";

/** An achievement known only by its ids — a notice's, a push's link: its
 * game's list is read on that person's progress, then its own page opens. */
export function AchievementByRef({
  platform,
  titleId,
  achievementId,
  person,
  onClose,
  layer,
}: {
  platform: string;
  titleId: string;
  achievementId: string;
  person: { id: number; name: string } | null;
  onClose: () => void;
  layer: string;
}) {
  const { data, tr, locale } = useApp();
  const list = useLoad(`ach-ref:${platform}:${titleId}:${person?.id ?? "me"}`, () =>
    gamesApi.fetchGame(data, platform, titleId, { personId: person?.id }),
  );
  const d = list.data;
  const found = d?.achievements.find((a) => a.achievement_id === achievementId);
  if (d && found) {
    const owner = person ?? null;
    return (
      <AchievementPage
        ach={achOfList(found, { platform, titleId, game: d.game?.name ?? d.name, icon: d.game?.poster ?? d.icon_url, gameId: d.game?.game_id }, owner, locale)}
        onClose={onClose}
        layer={layer}
      />
    );
  }
  return (
    <Page title={tr("pageAchievement")} onBack={onClose} hero layer={layer}>
      {!d && !list.error && <div className="hero ach-ref-skel skel" />}
      {(list.error || (d && !found)) && (
        <Empty
          icon="trophy"
          title={tr("loadFailed")}
          action={
            <Button variant="tonal" onClick={list.reload}>
              {tr("retry")}
            </Button>
          }
        />
      )}
    </Page>
  );
}
