import { useState } from "react";
import { peopleApi, type Relation } from "../../../api/people/peopleApi";
import { t, type Locale } from "../../../i18n";
import { Dropdown, DropdownArrow } from "../../shared/lib";

/** The one follow control (#157). Not following: "Подписаться" follows at once —
 * following needs no consent. Following: "Друзья ⌄" / "В подписках ⌄" opens the
 * rest, unfollow and block, so neither happens by a stray tap. Blocked:
 * "Разблокировать". */
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

  const act = (call: Promise<{ relation: Relation }>) => {
    if (busy) return;
    setBusy(true);
    void call
      .then((res) => onChange(res.relation))
      .catch((err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`))
      .finally(() => setBusy(false));
  };

  if (relation.blocked) {
    return (
      <button
        type="button"
        className="btn sm is-quiet follow-btn"
        disabled={busy}
        onClick={() => act(peopleApi.unblock(data, personId))}
      >
        {t(locale, "unblock")}
      </button>
    );
  }

  if (relation.following) {
    return (
      <Dropdown
        className="dd-trigger follow-btn follow-state"
        value=""
        options={[
          { value: "unfollow", label: t(locale, "unfollow") },
          { value: "block", label: t(locale, "block"), danger: true },
        ]}
        onChange={(action) => {
          if (action === "unfollow") act(peopleApi.unfollow(data, personId));
          if (action === "block") {
            if (!window.confirm(t(locale, "confirmBlock"))) return;
            act(peopleApi.block(data, personId));
          }
        }}
        trigger={
          <>
            {t(locale, relation.friends ? "friendsBtn" : "followingBtn")}
            <DropdownArrow />
          </>
        }
      />
    );
  }

  return (
    <button
      type="button"
      className="btn sm follow-btn"
      disabled={busy}
      onClick={() => act(peopleApi.follow(data, personId))}
    >
      {t(locale, "follow")}
    </button>
  );
}
