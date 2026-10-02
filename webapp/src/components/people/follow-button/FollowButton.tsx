import { useState } from "react";
import { peopleApi, type Relation } from "../../../api/people/peopleApi";
import { t, type Locale } from "../../../i18n";

/** Follow / Following / Friends, one tap each way (#157): following needs no
 * consent, so the button just flips. A blocked person has no button. */
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
  const [busy, setBusy] = useState(false);
  if (relation.blocked) return null;

  const label = relation.friends
    ? t(locale, "friendsBtn")
    : relation.following
      ? t(locale, "followingBtn")
      : t(locale, "follow");

  const toggle = () => {
    if (busy) return;
    setBusy(true);
    const call = relation.following
      ? peopleApi.unfollow(data, personId)
      : peopleApi.follow(data, personId);
    void call
      .then((res) => onChange(res.relation))
      .catch((err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`))
      .finally(() => setBusy(false));
  };

  return (
    <button
      type="button"
      className={relation.following ? "btn sm follow-btn is-on" : "btn sm follow-btn"}
      disabled={busy}
      onClick={toggle}
    >
      {label}
    </button>
  );
}
