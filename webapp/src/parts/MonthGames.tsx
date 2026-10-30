import type { FeedItem, PersonPayload } from "../api";
import { useApp } from "../app/context";
import { Wave } from "../ui/Wave";
import { DoneMark } from "./DoneMark";
import { GameTile } from "./GameTile";

/** One platform's list of a month's game: its own progress, never summed. */
export type GameLineList = {
  platform: string;
  titleId: string;
  unlocked: number | null;
  total: number | null;
};

export type GameLine = {
  /** The catalog's game; none for a list in no game yet. */
  gameId: number | null;
  platform: string;
  titleId: string;
  name: string;
  month: number;
  cover: string | null;
  lists: GameLineList[];
};

/** A month's games, one a catalog game (owner, 2026-10-30): the counts from
 * `games`, each list's progress and a fallback picture from the month's own
 * feed, which carries both. */
export function gameLines(payload: PersonPayload): GameLine[] {
  const byList = new Map<string, FeedItem>();
  for (const item of payload.feed) {
    const key = `${item.platform}:${item.title_id}`;
    if (!byList.has(key)) byList.set(key, item);
  }
  return payload.games
    .filter((g) => g.title_id && g.platform)
    .map((g) => {
      const first = byList.get(`${g.platform}:${g.title_id}`);
      const lists = (g.lists ?? [{ platform: g.platform as string, title_id: g.title_id as string, unlocked: g.unlocked ?? 0 }]).map(
        (l) => {
          const item = byList.get(`${l.platform}:${l.title_id}`);
          return {
            platform: l.platform,
            titleId: l.title_id,
            unlocked: item?.progress?.unlocked ?? null,
            total: item?.progress?.total ?? null,
          };
        },
      );
      return {
        gameId: g.game_id ?? null,
        platform: g.platform as string,
        titleId: g.title_id as string,
        name: g.name || first?.game || "",
        month: g.unlocked ?? 0,
        // The game's own poster, as its page and a favorite show it.
        cover: g.poster ?? first?.game_poster ?? first?.game_icon_url ?? null,
        lists,
      };
    });
}

const doneList = (l: GameLineList) => Boolean(l.total && l.unlocked === l.total);
const share = (l: GameLineList) => (l.total ? (l.unlocked ?? 0) / l.total : -1);

/** The list a card shows: the furthest along of the game's platforms (owner,
 * 2026-10-30) — the game's page switches between them. */
function leadList(lists: GameLineList[]): GameLineList | null {
  return lists.reduce<GameLineList | null>(
    (best, l) => (!best || share(l) > share(best) || (share(l) === share(best) && (l.unlocked ?? 0) > (best.unlocked ?? 0)) ? l : best),
    null,
  );
}

/** The month's games as a rail of cards: the cover (a check on it when its
 * list is earned whole), the name, the progress of the platform furthest
 * along, what the month added. A tap opens the game on this person's progress. */
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
        ? [0, 1, 2].map((i) => <span key={i} className="game-tile game-tile-skel skel" />)
        : games.map((g) => {
            const lead = leadList(g.lists);
            const done = lead ? doneList(lead) : false;
            return (
              <GameTile
                key={g.gameId ?? `${g.platform}:${g.titleId}`}
                cover={g.cover}
                name={g.name}
                done={done}
                mark={done ? <DoneMark size={34} /> : null}
                onOpen={() =>
                  open({
                    kind: "game",
                    ref: {
                      game_id: g.gameId ?? undefined,
                      platform: g.platform,
                      title_id: g.titleId,
                      name: g.name,
                      icon_url: g.cover,
                      person: person ? { person_id: person.id, name: person.name } : null,
                    },
                  })
                }
              >
                {lead?.total ? <Wave value={lead.unlocked ?? 0} total={lead.total} /> : null}
                <span className="game-tile-foot">
                  <span className="game-tile-gain">+{g.month}</span>
                  {lead?.total ? <span className="game-tile-num t-num">{`${lead.unlocked}/${lead.total}`}</span> : null}
                </span>
              </GameTile>
            );
          })}
    </div>
  );
}
