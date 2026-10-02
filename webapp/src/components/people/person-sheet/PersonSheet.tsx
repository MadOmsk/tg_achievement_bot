import { useEffect, useState } from "react";
import { peopleApi, type PersonProfile, type Relation } from "../../../api/people/peopleApi";
import { t, type Locale } from "../../../i18n";
import { Avatar, CoverImg, Dropdown, PlatformLogo, Sheet, useOpenGame } from "../../shared/lib";
import { FollowButton } from "../follow-button/FollowButton";
import "./PersonSheet.css";

/** A person's card in the People tab (#157): who they are, the follow button beside
 * the name, how many follow them, their accounts and this month's games (when their
 * privacy lets you see them), and quiet remove-follower and block links below. */
const EMPTY: Relation = { following: false, followed_by: false, friends: false, blocked: false };

export type SheetPerson = {
  id?: number | null;
  tg_id: number | null;
  handle: string;
  relation?: Relation;
};

export function PersonSheet({
  locale,
  data,
  person,
  onClose,
  onChange,
  onFlash,
  onOpenProfile,
}: {
  locale: Locale;
  data: string;
  /** Who: a row from the People lists, or just the author of a feed post. */
  person: SheetPerson;
  onClose: () => void;
  onChange?: (relation: Relation) => void;
  onFlash: (message: string) => void;
  /** Tapping the avatar or the nickname opens the full profile. */
  onOpenProfile?: (tgId: number) => void;
}) {
  const [profile, setProfile] = useState<PersonProfile | null>(null);
  const [busy, setBusy] = useState(false);
  const [own, setOwn] = useState<Relation | null>(person.relation ?? null);
  const openGame = useOpenGame();
  const relation = own ?? profile?.relation ?? EMPTY;
  const personId = person.id ?? profile?.id ?? null;
  const tgId = person.tg_id ?? profile?.tg_id ?? null;
  const handle = profile?.handle ?? person.handle;

  useEffect(() => {
    let cancelled = false;
    const call =
      person.id != null
        ? peopleApi.profile(data, person.id)
        : person.tg_id != null
          ? peopleApi.profileByTg(data, person.tg_id)
          : null;
    call
      ?.then((res) => {
        if (!cancelled) setProfile(res);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [data, person.id, person.tg_id, own?.following, own?.blocked, own?.followed_by]);

  const changed = (next: Relation) => {
    setOwn(next);
    onChange?.(next);
  };

  const act = (call: Promise<{ relation: Relation }>) => {
    if (busy) return;
    setBusy(true);
    void call
      .then((res) => changed(res.relation))
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
  // "Friends" already reads on the button; only a one-way follower is said here.
  const tie = relation.followed_by && !relation.following ? t(locale, "followsYou") : "";
  const loading = profile === null;
  const games = activity?.games ?? [];

  const toProfile = tgId != null && onOpenProfile ? () => onOpenProfile(tgId) : undefined;

  return (
    <Sheet onClose={onClose} mid>
      <div className="person-sheet">
        <div className="ps-head">
          <button type="button" className="ps-avatar" onClick={toProfile} disabled={!toProfile}>
          <Avatar
            name={handle}
            tgId={tgId ?? undefined}
            online={online}
            playing={Boolean(presence?.playing)}
            platform={presence?.platform}
            size={56}
          />
          </button>
          <div className="ps-head-copy">
            <h2>
              {toProfile ? (
                <button type="button" className="ps-name" onClick={toProfile}>
                  {handle}
                </button>
              ) : (
                handle
              )}
            </h2>
            {loading ? (
              <span className="skel ps-skel-line" aria-hidden />
            ) : (
              (status || tie) && (
                <p className="ps-sub">{[tie, status].filter(Boolean).join(" · ")}</p>
              )
            )}
          </div>
          {personId != null && (
            <>
              <FollowButton
                locale={locale}
                data={data}
                personId={personId}
                relation={relation}
                onChange={changed}
                onFlash={onFlash}
              />
              {!relation.following && !relation.blocked && (
                // Not following yet: blocking waits behind "⋯".
                <Dropdown
                  className="dd-trigger ps-more"
                  label={t(locale, "more")}
                  value=""
                  options={[{ value: "block", label: t(locale, "block"), danger: true }]}
                  onChange={() => {
                    if (busy || !window.confirm(t(locale, "confirmBlock"))) return;
                    act(peopleApi.block(data, personId));
                  }}
                  trigger={<span aria-hidden>⋯</span>}
                />
              )}
            </>
          )}
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
                            tgId != null ? { tg_id: tgId, name: handle } : null,
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

      </div>
    </Sheet>
  );
}
