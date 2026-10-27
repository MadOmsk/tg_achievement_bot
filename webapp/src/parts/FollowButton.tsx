import { useState } from "react";
import { ApiError } from "../api";
import { peopleApi, type Relation } from "../api/people/peopleApi";
import { useApp } from "../app/context";
import { Button } from "../ui/Controls";
import { Icon } from "../ui/Icon";
import { Confirm } from "../ui/Page";

export const FOLLOWS_CHANGED = "follows-changed";
/** A heart put on or taken off a game: the lists of favorites read again. */
export const FAVORITES_CHANGED = "favorites-changed";

/** Follow, or what following already is: "following", "friends" — a tap on
 * those asks before it unfollows, or opens `onMenu` where the page has one. */
export function FollowButton({
  personId,
  relation,
  onChange,
  onMenu,
  small = false,
}: {
  personId: number;
  relation: Relation;
  onChange: (relation: Relation) => void;
  onMenu?: () => void;
  small?: boolean;
}) {
  const { data, tr, toast } = useApp();
  const [busy, setBusy] = useState(false);
  const [ask, setAsk] = useState(false);

  const run = async (follow: boolean) => {
    setBusy(true);
    try {
      const res = follow ? await peopleApi.follow(data, personId) : await peopleApi.unfollow(data, personId);
      onChange(res.relation);
      window.dispatchEvent(new Event(FOLLOWS_CHANGED));
    } catch (err) {
      toast(err instanceof ApiError && err.code === "too_soon" ? tr("followTooSoon") : tr("somethingWrong"), "error");
    } finally {
      setBusy(false);
    }
  };

  if (relation.blocked) return null;
  const label = relation.friends
    ? tr("friendsBtn")
    : relation.following
      ? tr("followingBtn")
      : relation.followed_by
        ? tr("followBack")
        : tr("follow");
  return (
    <>
      <Button
        variant={relation.following ? "tonal" : "filled"}
        icon={relation.following ? "check" : "plus"}
        busy={busy}
        className={small ? "btn-small" : ""}
        onClick={() => (relation.following ? (onMenu ? onMenu() : setAsk(true)) : void run(true))}
      >
        {label}
        {relation.following && onMenu && <Icon name="down" size={18} />}
      </Button>
      {ask && (
        <Confirm
          text={tr("confirmUnfollow")}
          yes={tr("unfollow")}
          no={tr("cancel")}
          onYes={() => {
            setAsk(false);
            void run(false);
          }}
          onNo={() => setAsk(false)}
        />
      )}
    </>
  );
}
