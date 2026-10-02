import { useCallback, useEffect, useRef, useState } from "react";
import { peopleApi, type PersonRow, type Relation } from "../../api/people/peopleApi";
import { t, type Locale } from "../../i18n";
import { Avatar, EmptyState, SearchBar } from "../../components/shared/lib";
import { PersonSheet } from "../../components/people/person-sheet/PersonSheet";
import { FollowButton } from "../../components/people/follow-button/FollowButton";
import "./People.css";

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
}: {
  locale: Locale;
  data: string;
  refreshKey: number;
  /** Opened through the Find button: put the cursor in the search field. */
  focusSearch?: boolean;
  onFlash: (message: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [lists, setLists] = useState<Lists | null>(null);
  const [hits, setHits] = useState<PersonRow[] | null>(null);
  const [open, setOpen] = useState<PersonRow | null>(null);
  const searchSeq = useRef(0);

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
    setLists((current) => (current ? { ...current, suggested: patch(current.suggested) } : current));
    void load();
  };

  const line = (row: PersonRow) => (
    <div key={row.id} className="people-line">
      <button type="button" className="picker-row is-person" onClick={() => setOpen(row)}>
        <Avatar name={row.handle} tgId={row.tg_id ?? undefined} size={40} />
        <span className="picker-row-copy">
          <strong>{row.handle}</strong>
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

  const searching = query.trim().length >= SEARCH_MIN;
  const empty =
    lists !== null &&
    lists.following.length + lists.followers.length + lists.suggested.length === 0;

  return (
    <>
      <header className="page-head">
        <h1>{t(locale, "people")}</h1>
      </header>
      <SearchBar locale={locale} value={query} onChange={setQuery} focusKey={focusSearch} />
      {searching ? (
        hits === null ? null : hits.length === 0 ? (
          <p className="empty">{t(locale, "noResults")}</p>
        ) : (
          <div className="people-list">{hits.map(line)}</div>
        )
      ) : (
        <>
          {query.trim() !== "" && <p className="people-hint">{t(locale, "searchMin")}</p>}
          {lists === null ? null : empty ? (
            <EmptyState
              title={t(locale, "peopleEmptyTitle")}
              hint={t(locale, "peopleEmptyHint")}
            />
          ) : (
            <>
              {section("peopleFollowing", lists.following)}
              {section("peopleFollowers", lists.followers)}
              {section("peopleSuggested", lists.suggested)}
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
        />
      )}
    </>
  );
}
