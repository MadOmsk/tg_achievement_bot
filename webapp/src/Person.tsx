import { useEffect, useRef, useState, type CSSProperties, type ReactNode, type Ref } from "react";
import type { FeedItem, PersonPayload } from "./api";
import { dayKey, dayLabel, t, timeAgo, type Locale } from "./i18n";
import { Avatar, Icon, PlatformDot, ScoreCup, Sheet, isOnline } from "./ui";

const HOME_SLIDES = 5;

function veiled(
  item: { is_secret: boolean },
  key: string,
  revealed?: Set<string>,
  showSecrets?: boolean,
) {
  return Boolean(item.is_secret && !showSecrets && revealed && !revealed.has(key));
}

export function PersonProfile({
  person,
  locale,
  revealed,
  showSecrets,
  monthChip,
  onBack,
  onReveal,
}: {
  person: PersonPayload;
  locale: Locale;
  revealed: Set<string>;
  showSecrets?: boolean;
  monthChip?: ReactNode;
  onBack: () => void;
  onReveal: (key: string) => void;
}) {
  const feed = person.feed ?? [];
  const scoreLines = (person.platforms ?? []).flatMap((p) => {
    const xbox = p.platform.startsWith("xbox");
    const count = xbox && p.gamerscore != null ? p.gamerscore : p.achievement_count ?? p.trophy_count;
    if (count == null) return [];
    const extra = xbox
      ? null
      : p.trophy_level != null
        ? `${t(locale, "level")} ${p.trophy_level}`
        : p.completed_games
          ? `🏆 ${p.completed_games}`
          : p.platinum_count
            ? `🏆 ${p.platinum_count}`
            : null;
    const key = xbox ? "xbox" : p.platform === "steam" ? "steam" : "psn";
    const tiers =
      key === "psn" && p.bronze != null
        ? `🥉 ${p.bronze} · 🥈 ${p.silver ?? 0} · 🥇 ${p.gold ?? 0} · 🏆 ${p.platinum_count ?? 0}`
        : null;
    return [{
      platform: p.platform,
      count,
      extra,
      unit: xbox && p.gamerscore != null ? "G" : null,
      day: person.today?.[key] ?? 0,
      month: person.month?.[key] ?? 0,
      tiers,
    }];
  });
  const rest = feed.slice(HOME_SLIDES);
  return (
    <>
      <header className="account-bar person-bar">
        <div className="account-top">
          <div className="account-who">
            <button
              type="button"
              className="person-back"
              onClick={onBack}
              aria-label={t(locale, "back")}
            >
              <Icon name="back" size={28} />
            </button>
            <Avatar name={person.name} tgId={person.tg_id} size={48} />
            <span>
              <strong>{person.name}</strong>
            </span>
          </div>
          <ScoreCup locale={locale} lines={scoreLines} />
        </div>
      </header>
      <div className="person-stage">
        {feed.length > 0 ? (
          <UnlockSlider
            items={feed}
            locale={locale}
            revealed={revealed}
            showSecrets={showSecrets}
            onReveal={onReveal}
          />
        ) : (
          <p className="empty">{t(locale, "emptyFeed")}</p>
        )}
      </div>
      <div className="section-head achievements-head">
        <h1 className="kicker" style={{ margin: 0 }}>
          {t(locale, "homeAchievements")}
        </h1>
        {monthChip}
      </div>
      {rest.length > 0 ? (
        <FeedList
          items={rest}
          locale={locale}
          revealed={revealed}
          showSecrets={showSecrets}
          onReveal={onReveal}
        />
      ) : null}
    </>
  );
}

export function UnlockSlider({
  items,
  locale,
  revealed,
  showSecrets,
  onReveal,
  onOpenPerson,
}: {
  items: FeedItem[];
  locale: Locale;
  revealed?: Set<string>;
  showSecrets?: boolean;
  onReveal?: (key: string) => void;
  onOpenPerson?: (tgId: number) => void;
}) {
  const slides = items.slice(0, HOME_SLIDES);
  const loopable = slides.length > 1;
  // Clone of the first after the last: swipe forward lands on a twin, then
  // we teleport scroll to the real first with no reverse animation.
  const trackSlides = loopable ? [...slides, slides[0]] : slides;
  const trackRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef(0);
  const hideRef = useRef(0);
  const settleRef = useRef(0);
  const wrappingRef = useRef(false);
  const [progress, setProgress] = useState(0);
  const [using, setUsing] = useState(false);

  const readProgress = () => {
    const track = trackRef.current;
    if (!track || !track.clientWidth) return 0;
    return track.scrollLeft / track.clientWidth;
  };

  const markUse = () => {
    if (slides.length < 2) return;
    setUsing(true);
    window.clearTimeout(hideRef.current);
    hideRef.current = window.setTimeout(() => setUsing(false), 1400);
  };

  const wrapIfNeeded = () => {
    const track = trackRef.current;
    if (!track || !loopable || !track.clientWidth || wrappingRef.current) return;
    const width = track.clientWidth;
    const idx = Math.round(track.scrollLeft / width);
    if (idx < slides.length) return;
    // Same picture as slide 0 — jump without smooth scroll so it feels like
    // the strip continues forward instead of rewinding.
    wrappingRef.current = true;
    window.clearTimeout(settleRef.current);
    cancelAnimationFrame(frameRef.current);
    const snap = track.style.scrollSnapType;
    const behavior = track.style.scrollBehavior;
    track.style.scrollSnapType = "none";
    track.style.scrollBehavior = "auto";
    track.scrollTo({ left: 0, behavior: "instant" });
    setProgress(0);
    requestAnimationFrame(() => {
      track.scrollLeft = 0;
      requestAnimationFrame(() => {
        track.style.scrollSnapType = snap;
        track.style.scrollBehavior = behavior;
        setProgress(0);
        // Keep ignoring scroll until the browser finishes settling the jump —
        // restoring snap too early can still animate backwards on WebKit.
        window.setTimeout(() => {
          if (track.scrollLeft > width * 0.25) {
            track.style.scrollSnapType = "none";
            track.style.scrollBehavior = "auto";
            track.scrollLeft = 0;
            track.style.scrollSnapType = snap;
            track.style.scrollBehavior = behavior;
          }
          wrappingRef.current = false;
          setProgress(0);
        }, 80);
      });
    });
  };

  useEffect(
    () => () => {
      window.clearTimeout(hideRef.current);
      window.clearTimeout(settleRef.current);
    },
    [],
  );

  const go = (next: number) => {
    const track = trackRef.current;
    if (!track) return;
    markUse();
    const target = ((next % slides.length) + slides.length) % slides.length;
    track.scrollTo({ left: target * track.clientWidth, behavior: "smooth" });
  };

  const active = ((Math.round(progress) % slides.length) + slides.length) % slides.length;

  return (
    <div className="unlock-slider">
      <div
        ref={trackRef}
        className="unlock-slider-track"
        onScroll={() => {
          if (wrappingRef.current) return;
          markUse();
          cancelAnimationFrame(frameRef.current);
          frameRef.current = requestAnimationFrame(() => {
            if (wrappingRef.current) return;
            setProgress(readProgress());
          });
          window.clearTimeout(settleRef.current);
          settleRef.current = window.setTimeout(wrapIfNeeded, 120);
        }}
        onScrollEnd={wrapIfNeeded}
      >
        {trackSlides.map((item, i) => {
          const offset = i - progress;
          const away = Math.min(1, Math.abs(offset));
          const ease = away * away * (3 - 2 * away);
          return (
            <div
              key={`${feedKey(item)}:${i}`}
              className="unlock-slide"
              style={
                {
                  "--slide-x": `${offset * -12}%`,
                  "--slide-copy": `${offset * 28}px`,
                  "--slide-scale": `${1.04 - ease * 0.06}`,
                  "--slide-fade": `${1 - ease * 0.55}`,
                } as CSSProperties
              }
            >
              <UnlockHero
                item={item}
                secret={veiled(item, feedKey(item), revealed, showSecrets)}
                locale={locale}
                onReveal={onReveal}
                onOpenPerson={onOpenPerson}
              />
            </div>
          );
        })}
      </div>
      {slides.length > 1 ? (
        <div className={using ? "unlock-dots is-live" : "unlock-dots"} role="tablist">
          {slides.map((item, i) => (
            <button
              key={feedKey(item)}
              type="button"
              className={i === active ? "is-on" : undefined}
              aria-label={`${i + 1}`}
              onClick={() => go(i)}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function UnlockHero({
  item,
  secret = false,
  locale,
  onReveal,
  onOpenPerson,
}: {
  item: FeedItem;
  secret?: boolean;
  locale: Locale;
  onReveal?: (key: string) => void;
  onOpenPerson?: (tgId: number) => void;
}) {
  const heroRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (secret) return;
    const node = heroRef.current;
    if (!node) return;
    let frame = 0;
    const update = () => {
      const y = Math.max(0, window.scrollY || document.documentElement.scrollTop || 0);
      node.style.setProperty("--parallax", `${Math.min(y, 180) * 0.16}px`);
    };
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
    };
  }, [secret]);
  return (
    <UnlockCard
      artRef={heroRef}
      item={item}
      locale={locale}
      secret={secret}
      author
      onReveal={onReveal}
      onOpenPerson={onOpenPerson}
    />
  );
}

export function UnlockCard({
  item,
  locale,
  secret = false,
  author = false,
  gameInCopy = false,
  onOpen,
  onOpenPerson,
  onReveal,
  artRef,
}: {
  item: FeedItem;
  locale: Locale;
  secret?: boolean;
  author?: boolean;
  gameInCopy?: boolean;
  onOpen?: (item: FeedItem) => void;
  onOpenPerson?: (tgId: number) => void;
  onReveal?: (key: string) => void;
  artRef?: Ref<HTMLDivElement>;
}) {
  const score = item.tier_badge || (item.gamerscore ? `${item.gamerscore} G` : null);
  const rarity = item.rarity_percent != null ? `${item.rarity_percent}%` : null;
  const open = onOpen && !secret;
  return (
    <div
      className={secret ? "unlock-card is-secret" : open ? "unlock-card is-open" : "unlock-card"}
      role={open ? "button" : undefined}
      tabIndex={open ? 0 : undefined}
      onClick={open ? () => onOpen(item) : undefined}
    >
      <div ref={artRef} className="unlock-card-art">
        <span className="profile-hero-layers">
          {item.icon_url ? (
            <img src={item.icon_url} alt="" draggable={false} className="profile-hero-art" />
          ) : (
            <span className="profile-hero-art home-banner-fallback" />
          )}
        </span>
        <span className="profile-hero-wash" />
        <div className="unlock-card-head">
          {author ? <PostLead item={item} locale={locale} onOpenPerson={onOpenPerson} whoOnly /> : <span />}
          <HeroMarks score={score} rarity={rarity} />
        </div>
      </div>
      <div className="unlock-card-stage">
        <HeroGame item={item} />
        {secret ? (
          <span className="sheet-secret-veil">
            <button
              type="button"
              className="btn"
              onClick={(e) => {
                e.stopPropagation();
                onReveal?.(feedKey(item));
              }}
            >
              {t(locale, "reveal")}
            </button>
          </span>
        ) : null}
      </div>
      {gameInCopy ? (
        <div className="unlock-card-foot">
          <HeroGame item={item} />
          <div className="unlock-card-copy">
            {!secret && item.icon_url ? (
              <img src={item.icon_url} alt="" className="unlock-card-copy-blur" draggable={false} />
            ) : !secret ? (
              <span className="unlock-card-copy-blur home-banner-fallback" />
            ) : null}
            <h2>
              <span>{secret ? t(locale, "secret") : item.name}</span>
              <PlatformDot platform={item.platform} locale={locale} />
            </h2>
            <p>{secret ? "\u00a0" : item.description || "\u00a0"}</p>
          </div>
        </div>
      ) : (
        <div className="unlock-card-copy">
          {!secret && item.icon_url ? (
            <img src={item.icon_url} alt="" className="unlock-card-copy-blur" draggable={false} />
          ) : !secret ? (
            <span className="unlock-card-copy-blur home-banner-fallback" />
          ) : null}
          <h2>
            <span>{secret ? t(locale, "secret") : item.name}</span>
            <PlatformDot platform={item.platform} locale={locale} />
          </h2>
          <p>{secret ? "\u00a0" : item.description || "\u00a0"}</p>
        </div>
      )}
    </div>
  );
}

export function FeedList({
  items,
  locale,
  revealed,
  showSecrets,
  onReveal,
  onOpenPerson,
}: {
  items: FeedItem[];
  locale: Locale;
  revealed: Set<string>;
  showSecrets?: boolean;
  onReveal: (key: string) => void;
  onOpenPerson?: (tgId: number) => void;
}) {
  const [item, setItem] = useState<FeedItem | null>(null);
  const groups: Array<{ key: string; label: string; items: FeedItem[] }> = [];
  for (const row of items) {
    const key = dayKey(row.unlocked_at) || "unknown";
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.items.push(row);
    else groups.push({ key, label: dayLabel(row.unlocked_at, locale), items: [row] });
  }
  return (
    <div className="feed">
      {groups.map((group, i) => (
        <section key={`${group.key}-${i}`} className="feed-day">
          {group.label ? <p className="feed-day-label">{group.label}</p> : null}
          {group.items.map((row) => {
            const key = feedKey(row);
            const secret = veiled(row, key, revealed, showSecrets);
            const done =
              Boolean(row.progress) &&
              (row.progress?.total ?? 0) > 0 &&
              (row.progress?.unlocked ?? 0) >= (row.progress?.total ?? 0);
            return (
              <button
                key={key}
                type="button"
                className={[
                  "feed-row",
                  secret ? "is-secret" : "",
                  done ? "is-done" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                onClick={() => setItem(row)}
              >
                {row.icon_url ? (
                  <span className="feed-cover">
                    <img src={row.icon_url} alt="" className="cover" />
                    {secret ? (
                      <span className="feed-lock">
                        <Icon name="lock" size={18} />
                      </span>
                    ) : null}
                  </span>
                ) : (
                  <span className="feed-icon">
                    {secret ? <Icon name="lock" size={18} /> : null}
                  </span>
                )}
                <span className="feed-copy">
                  <p className="unlock-title">
                    <span>{secret ? t(locale, "secret") : row.name}</span>
                    <PlatformDot platform={row.platform} locale={locale} />
                  </p>
                  {row.game ? <p className="unlock-game">{row.game}</p> : null}
                  {row.progress && row.progress.total > 0 ? (
                    <span className="feed-row-progress" aria-hidden="true">
                      <span className="hero-game-bar">
                        <span
                          className="hero-game-bar-fill"
                          style={{
                            width: `${Math.min(
                              100,
                              (100 * row.progress.unlocked) / row.progress.total,
                            )}%`,
                          }}
                        />
                      </span>
                      <span className="hero-game-count">
                        {row.progress.unlocked}/{row.progress.total}
                      </span>
                    </span>
                  ) : null}
                </span>
                <HeroMarks
                  compact
                  score={row.tier_badge || (row.gamerscore ? `${row.gamerscore} G` : null)}
                  rarity={row.rarity_percent != null ? `${row.rarity_percent}%` : null}
                />
              </button>
            );
          })}
        </section>
      ))}
      {item ? (
        <Sheet mid onClose={() => setItem(null)} closeLabel={t(locale, "close")} noClose>
          <div className="sheet-unlock">
            <UnlockCard
              item={item}
              locale={locale}
              secret={veiled(item, feedKey(item), revealed, showSecrets)}
              author
              gameInCopy
              onOpenPerson={onOpenPerson}
              onReveal={onReveal}
            />
          </div>
        </Sheet>
      ) : null}
    </div>
  );
}

export function FeedPosts({
  items,
  locale,
  revealed,
  showSecrets,
  onReveal,
  onOpenPerson,
}: {
  items: FeedItem[];
  locale: Locale;
  revealed: Set<string>;
  showSecrets?: boolean;
  onReveal: (key: string) => void;
  onOpenPerson: (tgId: number) => void;
}) {
  return (
    <div className="feed-posts">
      {items.map((row) => {
        const key = feedKey(row);
        const secret = veiled(row, key, revealed, showSecrets);
        return (
          <UnlockCard
            key={key}
            item={row}
            locale={locale}
            secret={secret}
            author
            gameInCopy
            onOpenPerson={onOpenPerson}
            onReveal={onReveal}
          />
        );
      })}
    </div>
  );
}

export function PostLead({
  item,
  locale,
  onOpenPerson,
  whoOnly = false,
}: {
  item: FeedItem;
  locale: Locale;
  onOpenPerson?: (tgId: number) => void;
  whoOnly?: boolean;
}) {
  return (
    <span className="feed-post-lead">
      <button
        type="button"
        className="feed-post-who"
        onClick={(e) => {
          e.stopPropagation();
          onOpenPerson?.(item.tg_id);
        }}
      >
        <Avatar name={item.person} tgId={item.tg_id} size={32} />
        <span>
          <strong>{item.person}</strong>
          <p>{timeAgo(item.unlocked_at, locale)}</p>
        </span>
      </button>
      {whoOnly ? null : <HeroGame item={item} />}
    </span>
  );
}

export function HeroGame({ item }: { item: FeedItem }) {
  if (!item.game && !item.platform) return null;
  const progress = item.progress;
  const showBar = Boolean(progress && progress.total > 0);
  const pct =
    showBar && progress
      ? Math.min(100, (100 * progress.unlocked) / progress.total)
      : 0;
  return (
    <span className="hero-game">
      {item.game_icon_url ? (
        <img src={item.game_icon_url} alt="" />
      ) : item.game ? (
        <span className="hero-game-fallback" />
      ) : null}
      <span className="hero-game-text">
        {item.game ? <strong className="hero-game-title">{item.game}</strong> : null}
        {progress?.group ? (
          <span className="hero-game-group">
            {progress.group.name} · {progress.group.unlocked}/{progress.group.total}
          </span>
        ) : null}
        {showBar && progress ? (
          <span className="hero-game-bar-row">
            <span className="hero-game-bar" aria-hidden="true">
              <span className="hero-game-bar-fill" style={{ width: `${pct}%` }} />
            </span>
            <span className="hero-game-count">
              {progress.unlocked}/{progress.total}
            </span>
          </span>
        ) : null}
      </span>
    </span>
  );
}

export function HeroMarks({
  score,
  rarity,
  compact = false,
}: {
  score: string | null;
  rarity: string | null;
  compact?: boolean;
}) {
  if (!score && !rarity) return null;
  if (compact) {
    return (
      <span className="feed-plat">
                    {[rarity, score].filter(Boolean).join(" · ")}
      </span>
    );
  }
  return (
    <span className="hero-corner">
      <span className="hero-mark">{[rarity, score].filter(Boolean).join(" · ")}</span>
    </span>
  );
}

export function feedKey(row: FeedItem): string {
  return `${row.platform}:${row.title_id}:${row.achievement_id}:${row.tg_id}`;
}

export function PeopleHits({
  members,
  locale,
  onOpen,
}: {
  members: Array<{
    tg_id: number;
    name: string;
    playing?: boolean;
    state?: string | null;
    title_name?: string | null;
    status?: string;
    platform?: string | null;
  }>;
  locale: Locale;
  onOpen: (tgId: number) => void;
}) {
  if (members.length === 0) return null;
  return (
    <>
      <p className="kicker">{t(locale, "people")}</p>
      <div className="friends wrap">
        {members.map((m) => (
          <button key={m.tg_id} type="button" className="friend" onClick={() => onOpen(m.tg_id)}>
            <Avatar
              name={m.name}
              tgId={m.tg_id}
              online={isOnline(m)}
              platform={m.platform}
              size={72}
            />
            <strong>{m.name}</strong>
            <p>{m.playing ? m.title_name : m.status}</p>
          </button>
        ))}
      </div>
    </>
  );
}

export function matchQuery(haystack: string, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return false;
  return haystack.toLowerCase().includes(q);
}
