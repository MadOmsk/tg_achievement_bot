import { useEffect, useRef, useState } from "react";
import { peopleApi, type PersonRow, type Relation } from "../../../api/people/peopleApi";
import { t, type Locale, type TranslationKey } from "../../../i18n";
import { Avatar, Dropdown, DropdownArrow, EmptyState, Sheet } from "../../shared/lib";
import { FollowButton } from "../../people/follow-button/FollowButton";
import { FriendMark } from "../../people/friend-mark/FriendMark";
import "./FollowsSheet.css";
import { HandleName } from "../../shared/lib/handle-name/HandleName";

type Kind = "friends" | "following" | "followers" | "blocked";

const TITLE: Record<Kind, TranslationKey> = {
  friends: "friends",
  following: "peopleFollowing",
  followers: "peopleFollowers",
  blocked: "blockedTitle",
};
const EMPTY: Record<Kind, TranslationKey | undefined> = {
  friends: "friendsListEmpty",
  following: "followingEmpty",
  followers: "followersEmpty",
  blocked: undefined,
};

const EMPTY_TITLE: Record<Kind, TranslationKey> = {
  friends: "friendsListEmptyTitle",
  following: "followingEmptyTitle",
  followers: "followersEmptyTitle",
  blocked: "blockedEmpty",
};
const THEIR_EMPTY: Record<Kind, TranslationKey> = {
  friends: "friendsListEmptyTitle",
  following: "theirFollowingEmpty",
  followers: "followersEmptyTitle",
  blocked: "blockedEmpty",
};

/** Whether a person still belongs in a list after a change. Somebody else's
 * lists do not depend on what the viewer does. */
function stays(kind: Kind, relation: Relation, theirs: boolean): boolean {
  if (theirs) return !relation.blocked;
  if (kind === "blocked") return relation.blocked;
  if (kind === "friends") return relation.friends && !relation.blocked;
  if (kind === "following") return relation.following;
  return !relation.blocked;
}

/** "All" from Home's friends block (#157): friends (following each other), the
 * people you follow and the people who follow you, one list at a time, picked in
 * the title. Opens on the people you follow. With `owner`, the same for somebody
 * else: their friends, whom they follow and who follows them. */
export function FollowsSheet({
  locale,
  data,
  onClose,
  onOpen,
  onFind,
  onFlash,
  owner,
  initial = "following",
}: {
  locale: Locale;
  data: string;
  /** Somebody else's lists instead of one's own. */
  owner?: number;
  initial?: Kind;
  onClose: () => void;
  /** Open someone's full profile. */
  onOpen: (personId: number) => void;
  onFind: () => void;
  onFlash: (message: string) => void;
}) {
  const [kind, setKind] = useState<Kind>(initial);
  const theirs = owner != null;
  // Every list at once, so each count is known before switching to it.
  const [lists, setLists] = useState<Record<Kind, PersonRow[]> | null>(null);
  const rows = lists ? lists[kind] : null;
  // The friend marks show friends of either: the owner's of these lists, and the viewer's.
  const [ownerFriends, setOwnerFriends] = useState<Set<number>>(new Set());

  useEffect(() => {
    let cancelled = false;
    Promise.all(
      owner != null
        ? [peopleApi.followingOf(data, owner), peopleApi.followersOf(data, owner)]
        : [peopleApi.following(data), peopleApi.followers(data), peopleApi.blocked(data)],
    )
      .then(([following, followers, blocked]) => {
        if (cancelled) return;
        // Friends follow each other: one's own from the relation, somebody
        // else's as the people in both of their lists.
        const theirFollowers = new Set(followers.people.map((row) => row.id));
        const friends =
          owner != null
            ? following.people.filter((row) => theirFollowers.has(row.id))
            : following.people.filter((row) => row.relation.friends);
        // The list owner's friends (the ones marked) at the top of every list.
        const ids = new Set(friends.map((row) => row.id));
        setOwnerFriends(ids);
        const first = (rows: PersonRow[]) =>
          [...rows].sort(
            (a, b) =>
              Number(ids.has(b.id) || b.relation.friends) - Number(ids.has(a.id) || a.relation.friends),
          );
        setLists({
          friends,
          following: first(following.people),
          followers: first(followers.people),
          blocked: blocked?.people ?? [],
        });
      })
      .catch((err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`));
    return () => {
      cancelled = true;
    };
  }, [data, locale, onFlash, owner]);

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
    else if (hadRows.current && !theirs) onClose();
  }, [rows, onClose, theirs]);

  // Somebody no longer in the open list (unfollowed, blocked) folds away from it.
  const [leaving, setLeaving] = useState<Set<number>>(new Set());
  const apply = (id: number, relation: Relation) => {
    const gone = !stays(kind, relation, theirs);
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
                    stays(kind, row.relation, theirs),
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
    setLists((all) => {
      if (!all) return all;
      const update = (rows: PersonRow[]) => rows.map((row) => (row.id === id ? { ...row, relation } : row));
      // Blocked from another list: they show up in the blocked one at once.
      const person = [...all.following, ...all.followers].find((row) => row.id === id);
      const blocked =
        relation.blocked && person && !all.blocked.some((row) => row.id === id)
          ? [{ ...person, relation }, ...all.blocked]
          : update(all.blocked);
      return {
        friends: update(all.friends),
        following: update(all.following),
        followers: update(all.followers),
        blocked,
      };
    });
  };

  return (
    <Sheet onClose={onClose} mid>
      <div className="sheet-content score-sheet picker-sheet follows-sheet">
        <h2 className="follows-head">
          <Dropdown
            className="dd-trigger follows-switch"
            align="start"
            value={kind}
            options={(theirs
              ? (["following", "friends", "followers"] as Kind[])
              : (["following", "friends", "followers", "blocked"] as Kind[])
            ).map((value) => ({
              value,
              label: t(locale, TITLE[value]),
              hint: lists ? String(lists[value].length) : undefined,
            }))}
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
          <EmptyState
            title={t(locale, theirs ? THEIR_EMPTY[kind] : EMPTY_TITLE[kind])}
            hint={theirs || !EMPTY[kind] ? undefined : t(locale, EMPTY[kind])}
            action={theirs || kind === "blocked" ? undefined : { label: t(locale, "find"), onClick: onFind }}
            slide
          />
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
                  onClick={() => onOpen(row.id)}
                >
                  <FriendMark
                    friend={row.relation.friends || ownerFriends.has(row.id)}
                    label={t(locale, "friends")}
                  >
                    <Avatar name={row.handle} personId={row.id} size={40} />
                  </FriendMark>
                  <span className="picker-row-copy">
                    <strong>
                      <HandleName text={row.handle} />
                    </strong>
                  </span>
                </button>
                {!row.is_me && (
                  <FollowButton
                    locale={locale}
                    data={data}
                    personId={row.id}
                    relation={row.relation}
                    onChange={(relation) => apply(row.id, relation)}
                    onFlash={onFlash}
                  />
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </Sheet>
  );
}
