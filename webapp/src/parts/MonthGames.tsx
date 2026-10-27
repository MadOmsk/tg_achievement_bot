import type { FeedItem, PersonPayload } from "../api";
import { useApp } from "../app/context";
import { tick } from "../core/haptic";
import { Cover } from "../ui/Pic";
import { Wave } from "../ui/Wave";
import { DoneMark } from "./DoneMark";

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

/** The month's games as one connected group; a tap opens the game on this
 * person's progress. */
export function MonthGames({
  games,
  person,
  loading,
}: {
  games: GameLine[];
  person: { id: number; name: string } | null;
  loading: boolean;
}) {
  const { tr, open } = useApp();
  return (
    <div className="group">
      <div className="group-items">
        {loading
          ? Array.from({ length: 3 }, (_, i) => <span key={i} className="row game-row-skel skel" />)
          : games.map((g) => {
              const done = Boolean(g.total && g.unlocked === g.total);
              return (
                <button
                  key={`${g.platform}:${g.titleId}`}
                  type="button"
                  className={`row row-tap game-row${done ? " game-row-done" : ""}`}
                  onClick={() => {
                    tick();
                    open({
                      kind: "game",
                      ref: {
                        platform: g.platform,
                        title_id: g.titleId,
                        name: g.name,
                        icon_url: g.cover,
                        person: person ? { person_id: person.id, name: person.name } : null,
                      },
                    });
                  }}
                >
                  <span className="game-row-cover-wrap">
                    <Cover src={g.cover} className="game-row-cover" />
                    {done && <DoneMark size={26} />}
                  </span>
                  <span className="row-text">
                    <span className="game-row-top">
                      <span className="row-title clamp-2">{g.name}</span>
                      {g.total ? (
                        <span className="game-row-num t-num">
                          {done ? (
                            "100 %"
                          ) : (
                            <>
                              {g.unlocked}
                              <small>/{g.total}</small>
                            </>
                          )}
                        </span>
                      ) : null}
                    </span>
                    {g.total ? <Wave value={g.unlocked ?? 0} total={g.total} /> : null}
                    <span className="game-row-gain">
                      +{g.month} {tr("gainThisMonth")}
                    </span>
                  </span>
                </button>
              );
            })}
      </div>
    </div>
  );
}
