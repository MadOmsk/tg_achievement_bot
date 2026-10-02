import { useEffect, useState } from "react";
import { peopleApi, type PersonProfile, type PersonRow, type Relation } from "../../../api/people/peopleApi";
import { t, type Locale } from "../../../i18n";
import { Avatar, Sheet } from "../../shared/lib";
import { FollowButton } from "../follow-button/FollowButton";

/** A person's card in the People tab: the nickname, how many follow them, the
 * follow button, and the two things only the other person's side needs —
 * removing them from your followers, and blocking them (#157). */
export function PersonSheet({
  locale,
  data,
  person,
  onClose,
  onChange,
  onFlash,
}: {
  locale: Locale;
  data: string;
  person: PersonRow;
  onClose: () => void;
  onChange: (relation: Relation) => void;
  onFlash: (message: string) => void;
}) {
  const [profile, setProfile] = useState<PersonProfile | null>(null);
  const [busy, setBusy] = useState(false);
  const relation = person.relation;

  useEffect(() => {
    let cancelled = false;
    peopleApi
      .profile(data, person.id)
      .then((res) => {
        if (!cancelled) setProfile(res);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [data, person.id, relation.following, relation.blocked, relation.followed_by]);

  const act = (call: Promise<{ relation: Relation }>) => {
    if (busy) return;
    setBusy(true);
    void call
      .then((res) => onChange(res.relation))
      .catch((err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`))
      .finally(() => setBusy(false));
  };

  return (
    <Sheet onClose={onClose} mid>
      <div className="sheet-content person-sheet">
        <Avatar name={person.handle} tgId={person.tg_id ?? undefined} size={72} />
        <h2>{person.handle}</h2>
        <p className="person-sheet-sub">
          {relation.friends
            ? t(locale, "friendsBtn")
            : relation.followed_by
              ? t(locale, "followsYou")
              : ""}
        </p>
        {profile && (
          <p className="person-sheet-counts">
            <strong>{profile.followers}</strong> {t(locale, "followersCount")} ·{" "}
            <strong>{profile.following}</strong> {t(locale, "followingCount")}
          </p>
        )}
        {profile && !profile.can_view && (
          <p className="person-sheet-sub">{t(locale, "activityHidden")}</p>
        )}
        <div className="person-sheet-actions">
          <FollowButton
            locale={locale}
            data={data}
            personId={person.id}
            relation={relation}
            onChange={onChange}
            onFlash={onFlash}
          />
          {relation.followed_by && !relation.blocked && (
            <button
              type="button"
              className="btn sm"
              disabled={busy}
              onClick={() => act(peopleApi.removeFollower(data, person.id))}
            >
              {t(locale, "removeFollower")}
            </button>
          )}
          {relation.blocked ? (
            <button
              type="button"
              className="btn sm"
              disabled={busy}
              onClick={() => act(peopleApi.unblock(data, person.id))}
            >
              {t(locale, "unblock")}
            </button>
          ) : (
            <button
              type="button"
              className="btn sm danger"
              disabled={busy}
              onClick={() => {
                if (!window.confirm(t(locale, "confirmBlock"))) return;
                act(peopleApi.block(data, person.id));
              }}
            >
              {t(locale, "block")}
            </button>
          )}
        </div>
      </div>
    </Sheet>
  );
}
