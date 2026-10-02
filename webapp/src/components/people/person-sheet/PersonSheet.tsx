import { useEffect, useState } from "react";
import { peopleApi, type PersonProfile, type PersonRow, type Relation } from "../../../api/people/peopleApi";
import { t, type Locale } from "../../../i18n";
import { Avatar, PlatformLogo, Sheet } from "../../shared/lib";
import { FollowButton } from "../follow-button/FollowButton";
import "./PersonSheet.css";

/** A person's card in the People tab (#157): who they are and what they are doing
 * now, how many follow them, their accounts and latest unlocks (when their privacy
 * lets you see them), then follow — and, quietly below, remove follower and block. */
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

  const activity = profile?.activity ?? null;
  const presence = activity?.presence ?? null;
  const online = Boolean(presence && (presence.playing || presence.state === "Online"));
  const status = presence?.playing
    ? `${t(locale, "playing")} ${presence.title_name ?? ""}`.trim()
    : online
      ? t(locale, "online")
      : activity
        ? t(locale, "notOnline")
        : "";
  const tie = relation.friends
    ? t(locale, "friendsBtn")
    : relation.followed_by
      ? t(locale, "followsYou")
      : "";

  return (
    <Sheet onClose={onClose} mid>
      <div className="person-sheet">
        <div className="ps-scroll">
        <div className="ps-head">
          <Avatar
            name={person.handle}
            tgId={person.tg_id ?? undefined}
            online={online}
            playing={Boolean(presence?.playing)}
            size={64}
          />
          <div className="ps-head-copy">
            <h2>{person.handle}</h2>
            {profile === null ? (
              <span className="skel ps-skel-line" aria-hidden />
            ) : (
              (status || tie) && (
                <p className="ps-sub">{[tie, status].filter(Boolean).join(" · ")}</p>
              )
            )}
          </div>
        </div>

        {profile === null && (
          // The card opens at its loaded height and shape; nothing jumps when it fills.
          <>
            <div className="ps-stats" aria-hidden>
              <span className="skel ps-skel-tile" />
              <span className="skel ps-skel-tile" />
              <span className="skel ps-skel-tile" />
            </div>
            <div className="ps-section" aria-hidden>
              <span className="skel ps-skel-label" />
              {[0, 1].map((i) => (
                <div key={i} className="ps-row">
                  <span className="skel ps-skel-icon" />
                  <span className="skel ps-skel-text" />
                </div>
              ))}
            </div>
            <div className="ps-section" aria-hidden>
              <span className="skel ps-skel-label" />
              {[0, 1, 2].map((i) => (
                <div key={i} className="ps-row">
                  <span className="skel ps-skel-icon" />
                  <span className="skel ps-skel-text" />
                </div>
              ))}
            </div>
          </>
        )}

        {profile !== null && (
        <div className="ps-stats">
          <div>
            <strong>{profile?.followers ?? "–"}</strong>
            <span>{t(locale, "followersCount")}</span>
          </div>
          <div>
            <strong>{profile?.following ?? "–"}</strong>
            <span>{t(locale, "followingCount")}</span>
          </div>
          {activity && (
            <div>
              <strong>{activity.month.count}</strong>
              <span>{t(locale, "perMonth")}</span>
            </div>
          )}
        </div>
        )}

        {profile && !profile.can_view && (
          <p className="ps-hidden">{t(locale, "activityHidden")}</p>
        )}

        {activity && activity.platforms.length > 0 && (
          <div className="ps-section">
            <p className="ps-label">{t(locale, "accounts")}</p>
            {activity.platforms.map((p) => (
              <div key={p.platform} className="ps-row">
                <span className="ps-mark">
                  <PlatformLogo platform={p.platform} size={22} />
                </span>
                <span className="ps-row-main">{p.name}</span>
                <span className="ps-row-value">
                  {p.achievement_count ?? p.trophy_count ?? 0}
                </span>
              </div>
            ))}
          </div>
        )}

        {activity && activity.recent.length > 0 && (
          <div className="ps-section">
            <p className="ps-label">{t(locale, "recentUnlocks")}</p>
            {activity.recent.map((item) => (
              <div key={`${item.platform}:${item.title_id}:${item.achievement_id}`} className="ps-row">
                {item.icon_url ? (
                  <img className="ps-icon" src={item.icon_url} alt="" loading="lazy" />
                ) : (
                  <span className="ps-icon" aria-hidden />
                )}
                <span className="ps-row-main">
                  <strong>{item.is_secret ? t(locale, "secretAchievement") : item.name}</strong>
                  {item.game && <small>{item.game}</small>}
                </span>
              </div>
            ))}
          </div>
        )}

        </div>

        <div className="ps-actions">
          <FollowButton
            locale={locale}
            data={data}
            personId={person.id}
            relation={relation}
            onChange={onChange}
            onFlash={onFlash}
            wide
          />
          <div className="ps-quiet">
            {relation.followed_by && !relation.blocked && (
              <button
                type="button"
                disabled={busy}
                onClick={() => act(peopleApi.removeFollower(data, person.id))}
              >
                {t(locale, "removeFollower")}
              </button>
            )}
            {relation.blocked ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => act(peopleApi.unblock(data, person.id))}
              >
                {t(locale, "unblock")}
              </button>
            ) : (
              <button
                type="button"
                className="is-danger"
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
      </div>
    </Sheet>
  );
}
