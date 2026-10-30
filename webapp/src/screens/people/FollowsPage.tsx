import { useState } from "react";
import { peopleApi, type PersonRow } from "../../api/people/peopleApi";
import { useApp } from "../../app/context";
import { useLoad } from "../../app/useLoad";
import { matchQuery } from "../../core/feed-utils";
import { tick } from "../../core/haptic";
import { FollowButton } from "../../parts/FollowButton";
import { Button, Empty, Field, Segmented } from "../../ui/Controls";
import { Face } from "../../ui/Face";
import { Page } from "../../ui/Page";
import "./People.css";

type Which = "following" | "followers" | "friends" | "blocked";

export function FollowsPage({
  personId,
  which,
  onClose,
  layer,
}: {
  personId: number | null;
  which: Which;
  onClose: () => void;
  layer: string;
}) {
  const { data, tr } = useApp();
  const mine = personId === null;
  const [tab, setTab] = useState<Which>(which);
  const [q, setQ] = useState("");
  const list = useLoad(`follows:${personId ?? "me"}:${tab}`, () => {
    if (!mine) return tab === "followers" ? peopleApi.followersOf(data, personId) : peopleApi.followingOf(data, personId);
    if (tab === "followers") return peopleApi.followers(data);
    if (tab === "blocked") return peopleApi.blocked(data);
    return peopleApi.following(data);
  });
  const people = (list.data?.people ?? [])
    .filter((p) => (tab === "friends" ? p.relation.friends : true))
    .filter((p) => !q.trim() || matchQuery(p.handle, q))
    // Friends first, then whoever follows the viewer, then the rest, each
    // group in the order the server gave.
    .map((p, i) => ({ p, i, rank: p.relation.friends ? 0 : p.relation.followed_by ? 1 : 2 }))
    .sort((a, b) => a.rank - b.rank || a.i - b.i)
    .map(({ p }) => p);

  const options: Array<{ value: Which; label: string }> = mine
    ? [
        { value: "following", label: tr("peopleFollowing") },
        { value: "friends", label: tr("friends") },
        { value: "followers", label: tr("peopleFollowers") },
      ]
    : [
        { value: "following", label: tr("peopleFollowing") },
        { value: "followers", label: tr("peopleFollowers") },
      ];

  const emptyTitle =
    tab === "followers"
      ? tr("followersEmptyTitle")
      : tab === "friends"
        ? tr("friendsListEmptyTitle")
        : tab === "blocked"
          ? tr("blockedEmpty")
          : mine
            ? tr("followingEmptyTitle")
            : tr("theirFollowingEmpty");

  return (
    <Page title={tab === "blocked" ? tr("blockedTitle") : tr("people")} onBack={onClose} layer={layer}>
      {tab !== "blocked" && (
        <div className="fl-tabs">
          <Segmented options={options} value={tab} onChange={setTab} />
        </div>
      )}
      <div className="fl-search">
        <Field icon="search" placeholder={tr("searchPeople")} value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {!list.data && list.loading && (
        <div className="group">
          <div className="group-items">
            {[0, 1, 2].map((i) => (
              <span key={i} className="row skel" style={{ height: 72 }} />
            ))}
          </div>
        </div>
      )}
      {list.error && !list.data ? <Empty icon="refresh" title={tr("loadFailed")} action={<Button variant="tonal" onClick={list.reload}>{tr("retry")}</Button>} /> : null}
      {list.data && people.length === 0 && (
        <Empty icon="people" title={q ? tr("noResults") : emptyTitle} text={!q && tab === "following" && mine ? tr("followingEmpty") : null} />
      )}
      {people.length > 0 && (
        <div className="group">
          <div className="group-items">
            {people.map((p) => (
              <PersonLine key={p.id} person={p} />
            ))}
          </div>
        </div>
      )}
    </Page>
  );
}

export function PersonLine({ person, sub }: { person: PersonRow; sub?: string | null }) {
  const { tr, open } = useApp();
  const [relation, setRelation] = useState(person.relation);
  return (
    <div className="row person-line">
      <button
        type="button"
        className="person-line-main"
        onClick={() => {
          tick();
          open({ kind: "person", personId: person.id });
        }}
      >
        <Face personId={person.id} name={person.handle} size={44} />
        <span className="row-text">
          <span className="row-title clamp-1">{person.handle}</span>
          <span className="row-sub clamp-1">
            {sub ??
              (relation.friends
                ? tr("friendsBtn")
                : relation.followed_by
                  ? tr("followsYou")
                  : relation.blocked
                    ? tr("stateBlocked")
                    : "")}
          </span>
        </span>
      </button>
      {!person.is_me && <FollowButton personId={person.id} relation={relation} onChange={setRelation} small />}
    </div>
  );
}
