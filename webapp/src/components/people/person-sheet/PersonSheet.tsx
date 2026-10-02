import { useEffect, useState } from "react";
import { peopleApi, type PersonProfile, type PersonRow, type Relation } from "../../../api/people/peopleApi";
import { t, type Locale } from "../../../i18n";
import { Avatar, CoverImg, PlatformLogo, Sheet, useOpenGame } from "../../shared/lib";
import { FollowButton } from "../follow-button/FollowButton";
import "./PersonSheet.css";

/** A person's card in the People tab (#157): who they are, the follow button beside
 * the name, how many follow them, their accounts and this month's games (when their
 * privacy lets you see them), and quiet remove-follower and block links below. */
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
  const openGame = useOpenGame();
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
  const loading = profile === null;
  const games = activity?.games ?? [];

  return (
    <Sheet onClose={onClose} mid>
      <div className="person-sheet">
        <div className="ps-head">
          <Avatar
            name={person.handle}
            tgId={person.tg_id ?? undefined}
            online={online}
            playing={Boolean(presence?.playing)}
            platform={presence?.platform}
            size={56}
          />
          <div className="ps-head-copy">
            <h2>{person.handle}</h2>
            {loading ? (
              <span className="skel ps-skel-line" aria-hidden />
            ) : (
              (status || tie) && (
                <p className="ps-sub">{[tie, status].filter(Boolean).join(" · ")}</p>
              )
            )}
          </div>
          <FollowButton
            locale={locale}
            data={data}
            personId={person.id}
            relation={relation}
            onChange={onChange}
            onFlash={onFlash}
          />
        </div>

        {loading ? (
          // The card opens at its loaded height and shape; nothing jumps when it fills.
          <>
            <div className="ps-stats" aria-hidden>
              <span className="skel ps-skel-tile" />
              <span className="skel ps-skel-tile" />
            </div>
            <div className="ps-section" aria-hidden>
              <span className="skel ps-skel-label" />
              {[0].map((i) => (
                <div key={i} className="ps-row">
                  <span className="skel ps-skel-icon" />
                  <span className="skel ps-skel-text" />
                </div>
              ))}
            </div>
            <div className="ps-section" aria-hidden>
              <span className="skel ps-skel-label" />
              <div className="ps-games">
                {[0, 1, 2].map((i) => (
                  <span key={i} className="ps-game">
                    <span className="skel ps-skel-cover" />
                    <span className="skel ps-skel-name" />
                    <span className="skel ps-skel-count" />
                  </span>
                ))}
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="ps-stats">
              <div>
                <strong>{profile.followers}</strong>
                <span>{t(locale, "followersCount")}</span>
              </div>
              <div>
                <strong>{profile.following}</strong>
                <span>{t(locale, "followingCount")}</span>
              </div>
            </div>

            {!profile.can_view && <p className="ps-hidden">{t(locale, "activityHidden")}</p>}

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

            {games.length > 0 && (
              <div className="ps-section">
                <p className="ps-label">
                  {t(locale, "personMonthGames")}
                  <span className="ps-count">{games.length}</span>
                </p>
                <div className="ps-games">
                  {games.map((game) => (
                    <button
                      key={`${game.platform}:${game.title_id}`}
                      type="button"
                      className="ps-game"
                      onClick={() =>
                        openGame?.({
                          platform: game.platform,
                          title_id: game.title_id,
                          name: game.name,
                          icon_url: game.cover,
                          person:
                            person.tg_id != null ? { tg_id: person.tg_id, name: person.handle } : null,
                        })
                      }
                    >
                      <CoverImg src={game.cover} className="ps-game-cover" />
                      <strong>{game.name}</strong>
                      <small>+{game.count}</small>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

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
            <button type="button" disabled={busy} onClick={() => act(peopleApi.unblock(data, person.id))}>
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
    </Sheet>
  );
}
