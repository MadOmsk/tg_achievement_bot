import { useEffect, useRef, useState } from "react";
import { peopleApi, type PersonRow, type Relation } from "../../../api/people/peopleApi";
import { t, type Locale } from "../../../i18n";
import { Avatar, Dropdown, DropdownArrow, Icon, Sheet } from "../../shared/lib";
import { FollowButton } from "../../people/follow-button/FollowButton";
import "./FollowsSheet.css";

type Kind = "friends" | "following" | "followers";

const TITLE: Record<Kind, "friends" | "peopleFollowing" | "peopleFollowers"> = {
  friends: "friends",
  following: "peopleFollowing",
  followers: "peopleFollowers",
};
const EMPTY: Record<Kind, "friendsListEmpty" | "followingEmpty" | "followersEmpty"> = {
  friends: "friendsListEmpty",
  following: "followingEmpty",
  followers: "followersEmpty",
};

/** Whether a person still belongs in a list after a change. */
function stays(kind: Kind, relation: Relation): boolean {
  if (kind === "friends") return relation.friends && !relation.blocked;
  if (kind === "following") return relation.following;
  return !relation.blocked;
}

/** "All" from Home's friends block (#157): friends (following each other), the
 * people you follow and the people who follow you, one list at a time, picked in
 * the title. Opens on the people you follow. */
export function FollowsSheet({
  locale,
  data,
  onClose,
  onOpen,
  onFind,
  onFlash,
}: {
  locale: Locale;
  data: string;
  onClose: () => void;
  /** Open someone's full profile. */
  onOpen: (tgId: number) => void;
  onFind: () => void;
  onFlash: (message: string) => void;
}) {
  const [kind, setKind] = useState<Kind>("following");
  // Every list at once, so each count is known before switching to it.
  const [lists, setLists] = useState<Record<Kind, PersonRow[]> | null>(null);
  const rows = lists ? lists[kind] : null;

  useEffect(() => {
    let cancelled = false;
    Promise.all([peopleApi.following(data), peopleApi.followers(data)])
      .then(([following, followers]) => {
        if (cancelled) return;
        const friends = following.people.filter((row) => row.relation.friends);
        setLists({ friends, following: following.people, followers: followers.people });
      })
      .catch((err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`));
    return () => {
      cancelled = true;
    };
  }, [data, locale, onFlash]);

  // The last person folded out of the open list: nothing left to show, so the
  // drawer closes by itself.
  const hadRows = useRef(false);
  // Switching lists starts over; declared first so it runs before the check.
  useEffect(() => {
    hadRows.current = false;
  }, [kind]);
  useEffect(() => {
    if (!rows) return;
    if (rows.length > 0) hadRows.current = true;
    else if (hadRows.current) onClose();
  }, [rows, onClose]);

  // Somebody no longer in the open list (unfollowed, blocked) folds away from it.
  const [leaving, setLeaving] = useState<Set<number>>(new Set());
  const apply = (id: number, relation: Relation) => {
    const gone = !stays(kind, relation);
    if (gone) {
      window.setTimeout(() => setLeaving((all) => new Set(all).add(id)), 600);
      window.setTimeout(() => {
        // Only if it still holds: a refused change puts the person back.
        setLists((all) =>
          all
            ? {
                ...all,
                [kind]: all[kind].filter(
                  (row) =>
                    row.id !== id ||
                    stays(kind, row.relation),
                ),
              }
            : all,
        );
        setLeaving((all) => {
          const next = new Set(all);
          next.delete(id);
          return next;
        });
      }, 950);
    }
    setLists((all) =>
      all
        ? {
            friends: all.friends.map((row) => (row.id === id ? { ...row, relation } : row)),
            following: all.following.map((row) => (row.id === id ? { ...row, relation } : row)),
            followers: all.followers.map((row) => (row.id === id ? { ...row, relation } : row)),
          }
        : all,
    );
  };

  return (
    <Sheet onClose={onClose} mid>
      <div className="sheet-content score-sheet picker-sheet follows-sheet">
        <h2 className="follows-head">
          <Dropdown
            className="dd-trigger follows-switch"
            align="start"
            value={kind}
            options={[
              {
                value: "following" as Kind,
                label: t(locale, "peopleFollowing"),
                hint: lists ? String(lists.following.length) : undefined,
              },
              {
                value: "friends" as Kind,
                label: t(locale, "friends"),
                hint: lists ? String(lists.friends.length) : undefined,
              },
              {
                value: "followers" as Kind,
                label: t(locale, "peopleFollowers"),
                hint: lists ? String(lists.followers.length) : undefined,
              },
            ]}
            onChange={setKind}
            trigger={
              <>
                {t(locale, TITLE[kind])}
                {rows && <span className="follows-count">{rows.length}</span>}
                <DropdownArrow />
              </>
            }
          />
        </h2>
        {rows === null ? (
          <div className="picker-list" aria-busy="true">
            {[0, 1, 2].map((i) => (
              <div key={i} className="picker-row is-person">
                <span className="skel follows-skel-ava" />
                <span className="skel follows-skel-name" />
              </div>
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div className="follows-empty">
            <p>{t(locale, EMPTY[kind])}</p>
            <button type="button" className="see-all" onClick={onFind}>
              <span>{t(locale, "find")}</span>
              <Icon name="forward" size={16} />
            </button>
          </div>
        ) : (
          <div className="picker-list">
            {rows.map((row) => (
              <div
                key={row.id}
                className={leaving.has(row.id) ? "follows-line is-leaving" : "follows-line"}
              >
                <button
                  type="button"
                  className="picker-row is-person"
                  onClick={() => row.tg_id != null && onOpen(row.tg_id)}
                >
                  <Avatar name={row.handle} tgId={row.tg_id ?? undefined} size={40} />
                  <span className="picker-row-copy">
                    <strong>{row.handle}</strong>
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
            ))}
          </div>
        )}
      </div>
    </Sheet>
  );
}
