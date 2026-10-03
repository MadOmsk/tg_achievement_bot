import { useState } from "react";
import { peopleApi, type Relation } from "../../../api/people/peopleApi";
import { t, type Locale } from "../../../i18n";
import { Dropdown, DropdownArrow } from "../../shared/lib";

type State = "none" | "following" | "blocked";

export const FOLLOWS_CHANGED = "follows-changed";

/** The one follow control (#157): a picker of where you stand with somebody —
 * not following (the default), following, friends (following each other) or
 * blocked. Following needs no consent, so a pick acts at once; blocking asks first.
 *
 * The new state shows at once, with a short pop; the request runs behind it and
 * puts the old state back if the server refuses. */
export function FollowButton({
  locale,
  data,
  personId,
  relation,
  onChange,
  onFlash,
}: {
  locale: Locale;
  data: string;
  personId: number;
  relation: Relation;
  onChange: (relation: Relation) => void;
  onFlash: (message: string) => void;
}) {
  // Bumped on every change, so the pop animation replays.
  const [pop, setPop] = useState(0);
  const state: State = relation.blocked ? "blocked" : relation.following ? "following" : "none";

  const act = (next: Relation, call: () => Promise<{ relation: Relation }>) => {
    const previous = relation;
    onChange(next);
    setPop((n) => n + 1);
    void call()
      .then((res) => {
        onChange(res.relation);
        // Home, the feed and the ranking are about the people followed: they
        // refresh in the background (App listens).
        window.dispatchEvent(new Event(FOLLOWS_CHANGED));
      })
      .catch((err: unknown) => {
        onChange(previous);
        onFlash(
          // A re-follow right after an unfollow waits ten minutes (the server decides).
          String(err).includes("too_soon")
            ? t(locale, "followTooSoon")
            : `${t(locale, "error")}: ${String(err)}`,
        );
      });
  };

  const pick = (next: State) => {
    if (next === "blocked") {
      if (!window.confirm(t(locale, "confirmBlock"))) return;
      act({ following: false, followed_by: false, friends: false, blocked: true }, () =>
        peopleApi.block(data, personId),
      );
      return;
    }
    if (next === "none") {
      act(
        { ...relation, following: false, friends: false, blocked: false },
        state === "blocked"
          ? () => peopleApi.unblock(data, personId)
          : () => peopleApi.unfollow(data, personId),
      );
      return;
    }
    // Following, from blocked too: unblock first, then follow.
    act(
      { ...relation, blocked: false, following: true, friends: relation.followed_by },
      async () => {
        if (state === "blocked") await peopleApi.unblock(data, personId);
        return peopleApi.follow(data, personId);
      },
    );
  };

  // Following each other is friends: the same state, said as what it is.
  const followingLabel = t(
    locale,
    relation.followed_by && !relation.blocked ? "friendsBtn" : "stateFollowing",
  );
  const labels: Record<State, string> = {
    none: t(locale, "stateNone"),
    following: followingLabel,
    blocked: t(locale, "stateBlocked"),
  };
  const popClass = pop ? (pop % 2 ? " is-pop" : " is-pop2") : "";

  return (
    <Dropdown
      className={`dd-trigger follow-btn follow-state${popClass}`}
      value={state}
      options={[
        { value: "none" as State, label: labels.none },
        { value: "following" as State, label: followingLabel },
        { value: "blocked" as State, label: labels.blocked, danger: true },
      ]}
      onChange={pick}
      trigger={
        <>
          {labels[state]}
          <DropdownArrow />
        </>
      }
    />
  );
}
