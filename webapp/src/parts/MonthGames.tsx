import type { FeedItem, PersonPayload } from "../api";
import { useApp } from "../app/context";
import { Wave } from "../ui/Wave";
import { DoneMark } from "./DoneMark";
import { GameTile } from "./GameTile";

export type GameLine = {
  platform: string;
  titleId: string;
  name: string;
  month: number;
  unlocked: number | null;
  total: number | null;
  cover: string | null;
};

/** A month's games with their progress: the counts from `games`, the totals
 * and pictures from the month's own feed, which carries both. */
export function gameLines(payload: PersonPayload): GameLine[] {
  const byGame = new Map<string, FeedItem>();
  for (const item of payload.feed) {
    const key = `${item.platform}:${item.title_id}`;
    if (!byGame.has(key)) byGame.set(key, item);
  }
  return payload.games
    .filter((g) => g.title_id && g.platform)
    .map((g) => {
      const item = byGame.get(`${g.platform}:${g.title_id}`);
      return {
        platform: g.platform as string,
        titleId: g.title_id as string,
        name: g.name || item?.game || "",
        month: g.unlocked ?? 0,
        unlocked: item?.progress?.unlocked ?? null,
        total: item?.progress?.total ?? null,
        cover: item?.game_icon_url ?? null,
      };
    });
}

/** The month's games as a rail of cards: the cover (a check on it when the
 * list is earned whole), the name, the progress wave, what the month added.
 * A tap opens the game on this person's progress. */
export function MonthGames({
  games,
  person,
  loading,
}: {
  games: GameLine[];
  person: { id: number; name: string } | null;
  loading: boolean;
}) {
  const { open } = useApp();
  return (
    <div className="rail month-games">
      {loading
        ? Array.from({ length: 3 }, (_, i) => <span key={i} className="game-tile game-tile-skel skel" />)
        : games.map((g) => {
            const done = Boolean(g.total && g.unlocked === g.total);
            return (
              <GameTile
                key={`${g.platform}:${g.titleId}`}
                cover={g.cover}
                name={g.name}
                done={done}
                mark={done ? <DoneMark size={34} /> : null}
                onOpen={() =>
                  open({
                    kind: "game",
                    ref: {
                      platform: g.platform,
                      title_id: g.titleId,
                      name: g.name,
                      icon_url: g.cover,
                      person: person ? { person_id: person.id, name: person.name } : null,
                    },
                  })
                }
              >
                {g.total ? <Wave value={g.unlocked ?? 0} total={g.total} /> : null}
                <span className="game-tile-foot">
                  <span className="game-tile-gain">+{g.month}</span>
                  {g.total ? (
                    <span className="game-tile-num t-num">{`${g.unlocked}/${g.total}`}</span>
                  ) : null}
                </span>
              </GameTile>
            );
          })}
    </div>
  );
}
