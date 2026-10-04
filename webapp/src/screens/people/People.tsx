import { useCallback, useEffect, useRef, useState } from "react";
import { peopleApi, type PersonRow, type Relation } from "../../api/people/peopleApi";
import { t, type Locale } from "../../i18n";
import { Avatar, EmptyState, SearchBar } from "../../components/shared/lib";
import { PersonSheet } from "../../components/people/person-sheet/PersonSheet";
import { FollowButton } from "../../components/people/follow-button/FollowButton";
import { FriendMark } from "../../components/people/friend-mark/FriendMark";
import { GameHits, GameSheet, useHltbSearch } from "../../components/hltb";
import type { HltbHit } from "../../api";
import "./People.css";
import { HandleName } from "../../components/shared/lib/handle-name/HandleName";

const SEARCH_MIN = 3;

type Lists = {
  following: PersonRow[];
  followers: PersonRow[];
  suggested: PersonRow[];
};

/** The People tab (#157): find someone by nickname, and see who you follow, who
 * follows you and who shares a chat with you. Following needs no consent. */
export function People({
  locale,
  data,
  refreshKey,
  focusSearch,
  onFlash,
  onOpenProfile,
}: {
  locale: Locale;
  data: string;
  refreshKey: number;
  /** Opened through the Find button: put the cursor in the search field. */
  focusSearch?: boolean;
  onFlash: (message: string) => void;
  /** Open someone's full profile page. */
  onOpenProfile?: (tgId: number) => void;
}) {
  const [query, setQuery] = useState("");
  const [lists, setLists] = useState<Lists | null>(null);
  const [hits, setHits] = useState<PersonRow[] | null>(null);
  const [open, setOpen] = useState<PersonRow | null>(null);
  const [leaving, setLeaving] = useState<Set<number>>(new Set());
  const searchSeq = useRef(0);
  const [game, setGame] = useState<HltbHit | null>(null);
  const games = useHltbSearch(data, query, locale, onFlash);

  const load = useCallback(async () => {
    try {
      const [following, followers, suggested] = await Promise.all([
        peopleApi.following(data),
        peopleApi.followers(data),
        peopleApi.suggestions(data),
      ]);
      setLists({
        following: following.people,
        followers: followers.people,
        suggested: suggested.people,
      });
    } catch (err) {
      onFlash(`${t(locale, "error")}: ${String(err)}`);
    }
  }, [data, locale, onFlash]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  useEffect(() => {
    const text = query.trim();
    if (text.length < SEARCH_MIN) {
      searchSeq.current += 1;
      setHits(null);
      return;
    }
    const seq = ++searchSeq.current;
    const id = window.setTimeout(() => {
      peopleApi
        .search(data, text)
        .then((res) => {
          if (seq === searchSeq.current) setHits(res.people);
        })
        .catch((err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`));
    }, 250);
    return () => window.clearTimeout(id);
  }, [query, data, locale, onFlash]);

  // A follow or unfollow anywhere updates the same person everywhere on screen.
  const apply = (id: number, relation: Relation) => {
    const patch = (rows: PersonRow[]) =>
      rows.map((row) => (row.id === id ? { ...row, relation } : row));
    setHits((rows) => (rows ? patch(rows) : rows));
    setOpen((row) => (row && row.id === id ? { ...row, relation } : row));
    // A suggestion just followed shows its new state for a moment and then
    // folds away: the list is for people not followed yet.
    const suggested = lists?.suggested.find((row) => row.id === id);
    if (suggested && relation.following && !suggested.relation.following) {
      window.setTimeout(() => setLeaving((all) => new Set(all).add(id)), 900);
      window.setTimeout(() => {
        setLists((current) =>
          current
            ? { ...current, suggested: current.suggested.filter((row) => row.id !== id) }
            : current,
        );
        setLeaving((all) => {
          const next = new Set(all);
          next.delete(id);
          return next;
        });
      }, 1250);
    }
    setLists((current) =>
      current
        ? {
            following: patch(current.following),
            followers: patch(current.followers),
            suggested: patch(current.suggested),
          }
        : current,
    );
  };

  const line = (row: PersonRow) => (
    <div key={row.id} className={leaving.has(row.id) ? "people-line is-leaving" : "people-line"}>
      <button type="button" className="picker-row is-person" onClick={() => setOpen(row)}>
        <FriendMark friend={row.relation.friends} label={t(locale, "friends")}>
          <Avatar name={row.handle} tgId={row.tg_id ?? undefined} size={40} />
        </FriendMark>
        <span className="picker-row-copy">
          <strong>
            <HandleName text={row.handle} />
          </strong>
          {row.relation.followed_by && !row.relation.friends && (
            <p>{t(locale, "followsYou")}</p>
          )}
        </span>
      </button>
      <FollowButton
        locale={locale}
        data={data}
        personId={row.id}
        relation={row.relation}
        onChange={(relation) => apply(row.id, relation)}
        onFlash={onFlash}
      />
    </div>
  );

  const section = (key: string, rows: PersonRow[]) =>
    rows.length > 0 && (
      <>
        <p className="kicker">{t(locale, key as never)}</p>
        <div className="people-list">{rows.map(line)}</div>
      </>
    );

  // Games are found from two letters, people from three (their nicknames).
  const searching = query.trim().length >= 2;
  const empty = lists !== null && lists.suggested.length === 0 && lists.following.length === 0;

  return (
    <>
      <header className="page-head">
        <h1>{t(locale, "searchTitle")}</h1>
      </header>
      <SearchBar locale={locale} value={query} onChange={setQuery} focusKey={focusSearch}
        placeholder={t(locale, "searchHint")}
      />
      {searching ? (
        <div className="search-pane">
          {hits && hits.length > 0 && (
            <>
              <p className="kicker">{t(locale, "people")}</p>
              <div className="people-list">{hits.map(line)}</div>
            </>
          )}
          <GameHits
            hits={games.hits}
            busy={games.busy}
            searched={games.searched}
            locale={locale}
            onOpen={setGame}
          />
          {!games.busy && games.searched && games.hits.length === 0 && hits?.length === 0 && (
            <p className="empty">{t(locale, "noResults")}</p>
          )}
        </div>
      ) : (
        <>
          {query.trim() !== "" && <p className="people-hint">{t(locale, "searchMin")}</p>}
          {lists === null ? null : empty ? (
            <EmptyState
              title={t(locale, "peopleEmptyTitle")}
              hint={t(locale, "peopleEmptyHint")}
              slide
            />
          ) : (
            <>
              {section("peopleSuggested", lists.suggested)}
              {lists.suggested.length === 0 && (
                <EmptyState
                  title={t(locale, "suggestedDoneTitle")}
                  hint={t(locale, "suggestedDone")}
                  slide
                />
              )}
            </>
          )}
        </>
      )}
      {open && (
        <PersonSheet
          locale={locale}
          data={data}
          person={open}
          onClose={() => setOpen(null)}
          onChange={(relation) => apply(open.id, relation)}
          onFlash={onFlash}
          onOpenProfile={
            onOpenProfile
              ? (id) => {
                  setOpen(null);
                  onOpenProfile(id);
                }
              : undefined
          }
        />
      )}
      {game && (
        <GameSheet
          preview={game}
          data={data}
          locale={locale}
          onClose={() => setGame(null)}
          onFlash={onFlash}
        />
      )}
    </>
  );
}
