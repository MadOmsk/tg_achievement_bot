import { useEffect, useState } from "react";
import { peopleApi, type PersonRow, type Relation } from "../../../api/people/peopleApi";
import { t, type Locale } from "../../../i18n";
import { Avatar, Dropdown, DropdownArrow, Icon, Sheet } from "../../shared/lib";
import { FollowButton } from "../../people/follow-button/FollowButton";
import "./FollowsSheet.css";

type Kind = "following" | "followers";

/** "All" from Home's friends block (#157): the people you follow and the people
 * who follow you, one list at a time, picked in the title. */
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
  // Both lists at once, so each count is known before switching to it.
  const [lists, setLists] = useState<Record<Kind, PersonRow[]> | null>(null);
  const rows = lists ? lists[kind] : null;

  useEffect(() => {
    let cancelled = false;
    Promise.all([peopleApi.following(data), peopleApi.followers(data)])
      .then(([following, followers]) => {
        if (!cancelled) setLists({ following: following.people, followers: followers.people });
      })
      .catch((err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`));
    return () => {
      cancelled = true;
    };
  }, [data, locale, onFlash]);

  const apply = (id: number, relation: Relation) =>
    setLists((all) =>
      all
        ? {
            following: all.following.map((row) => (row.id === id ? { ...row, relation } : row)),
            followers: all.followers.map((row) => (row.id === id ? { ...row, relation } : row)),
          }
        : all,
    );

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
                value: "followers" as Kind,
                label: t(locale, "peopleFollowers"),
                hint: lists ? String(lists.followers.length) : undefined,
              },
            ]}
            onChange={setKind}
            trigger={
              <>
                {t(locale, kind === "following" ? "peopleFollowing" : "peopleFollowers")}
                <DropdownArrow />
              </>
            }
          />
          {rows && <span className="follows-count">{rows.length}</span>}
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
            <p>{t(locale, kind === "following" ? "followingEmpty" : "followersEmpty")}</p>
            <button type="button" className="see-all" onClick={onFind}>
              <span>{t(locale, "find")}</span>
              <Icon name="forward" size={16} />
            </button>
          </div>
        ) : (
          <div className="picker-list">
            {rows.map((row) => (
              <div key={row.id} className="follows-line">
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
