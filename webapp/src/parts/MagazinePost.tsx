import type { NewsItem } from "../api";
import { useApp } from "../app/context";
import { achOfFeed, isVeiled, pointsOf, rareLevel, TIER_NAME } from "../app/views";
import { clockOf } from "../core/post-text";
import { tick } from "../core/haptic";
import { dayKey, pct, plural, t, timeAgo, type Locale } from "../i18n";
import { isWideArt } from "./AchRow";
import { capital } from "./Months";
import { type Post as PostData, type UnlockEvent } from "./posts";
import { Face } from "../ui/Face";
import "./magazine.css";
import { Icon } from "../ui/Icon";
import { AchPic, Cover } from "../ui/Pic";
import { Spark } from "./AchRow";

/** Today and yesterday as how long ago — minutes, then hours (yesterday's
 * too, never "1 day") —; an older day by its clock, the day being its heading. */
function when(at: string | null, locale: Locale): string {
  if (!at) return "";
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const day = dayKey(at);
  if (day !== dayKey(new Date().toISOString()) && day !== dayKey(yesterday.toISOString())) return clockOf(at, locale);
  const hours = Math.round((Date.now() - new Date(at).getTime()) / 3600000);
  return hours < 24 ? timeAgo(at, locale) : `${hours} ${t(locale, "hoursAgo")}`;
}

function useOpenEvent() {
  const { open } = useApp();
  return (event: UnlockEvent) => {
    tick();
    const ach = achOfFeed(event.items[0]);
    if (event.items.length > 1) ach.together = event.items.map((i) => ({ id: i.person_id, name: i.person, at: i.unlocked_at }));
    open({ kind: "achievement", ach });
  };
}

/** A post of the feed, by what matters to whoever reads it: who, and in
 * which game, first; then what they got, large, with how rare it is — the one
 * thing that makes an achievement worth a look, drawn in its tier's colour —;
 * how far they are in the game at the foot. Points and time stay small. */
export function MagazinePost({ post }: { post: PostData }) {
  const { tr, locale, open, me } = useApp();
  const openEvent = useOpenEvent();
  const lead = post.events[0];
  const item = lead.items[0];
  const ach = achOfFeed(item);
  const veiled = isVeiled(item.is_secret, ach.key, me.settings.show_secrets);
  const tier = rareLevel(item.rarity_percent, { trophy: item.trophy_type, mythic: item.mythic });
  const rest = post.events.slice(1);
  const together = post.people.length > 1;
  const openGame = () => {
    tick();
    open({
      kind: "game",
      ref: {
        game_id: post.gameId ?? undefined,
        platform: post.platform,
        title_id: post.titleId,
        name: post.game,
        icon_url: post.gameIcon,
        person: { person_id: post.people[0].id, name: post.people[0].name },
      },
    });
  };
  return (
    <article className={`mag${tier ? ` mag-${tier}` : ""}`}>
      <header className="mag-by">
        <span className={`mag-faces${together ? " mag-faces-duo" : ""}`}>
          {post.people.slice(0, 2).map((p) => (
            <button key={p.id} type="button" aria-label={p.name} onClick={() => open({ kind: "person", personId: p.id })}>
              <Face personId={p.id} name={p.name} size={together ? 34 : 40} />
            </button>
          ))}
        </span>
        <span className="mag-who">
          <span className="mag-names-row">
            <span className="mag-names t-label clamp-1">{post.people.map((p) => p.name).join(` ${tr("and")} `)}</span>
            {/* When, on the name's own line. */}
            <span className="mag-time">{when(item.unlocked_at, locale)}</span>
          </span>
          <button type="button" className="mag-sub clamp-1" onClick={openGame}>
            {post.game}
          </button>
        </span>
      </header>

      <button type="button" className="mag-art" onClick={() => openEvent(lead)}>
        <AchPic src={item.icon_url} veiled={veiled} className={isWideArt(item.platform) ? "mag-pic" : "mag-pic mag-pic-sq"} />
        {together && (
          <span className={`mag-together-badge shape-cookie9${item.rarity_percent != null || tier ? "" : " mag-together-alone"}`} aria-label={tr("together")}>
            <Icon name="handshake" size={22} />
          </span>
        )}
        <span className={`mag-badge shape-flower6 tile-badge-${tier ?? "plain"}`}>
            <b className="t-num flower-pts">
              <Spark className="flower-spark" />
              {pointsOf(item.rarity_percent, { trophy: item.trophy_type, mythic: item.mythic })}</b>
          </span>
      </button>

      <button type="button" className="mag-body" onClick={() => openEvent(lead)}>
        <span className="mag-kicker">
          <span className={`mag-tier${tier ? ` mark-${tier}` : ""}`}>
            {capital(tr(TIER_NAME[tier ?? "common"]))}
            {item.rarity_percent != null && ` · ${pct(item.rarity_percent, locale)}`}
          </span>
        </span>
        <span className="mag-name t-card clamp-2">{veiled ? tr("secretAchievement") : item.name}</span>
        {!veiled && item.description && <span className="mag-desc clamp-2">{item.description}</span>}
      </button>

      {rest.length > 0 && (
        <>
          <p className="mag-more">
            {tr("magAlso")} {rest.length} {plural(locale, rest.length, ["achOne", "achFew", "achMany"])}
          </p>
          <div className="mag-strip rail">
            {rest.map((e) => {
              const x = e.items[0];
              const hidden = isVeiled(x.is_secret, achOfFeed(x).key, me.settings.show_secrets);
              const t = rareLevel(x.rarity_percent, { trophy: x.trophy_type, mythic: x.mythic });
              return (
                <button
                  key={`${x.achievement_id}:${e.at}`}
                  type="button"
                  className={`mag-thumb${isWideArt(x.platform) ? "" : " mag-thumb-sq"}`}
                  onClick={() => openEvent(e)}
                >
                  <AchPic src={x.icon_url} veiled={hidden} className="mag-thumb-pic" />
                  <span className="mag-thumb-name clamp-2">{hidden ? tr("secretAchievement") : x.name}</span>
                  {x.rarity_percent != null && (
                    <span className="mag-thumb-rarity">
                      <span className={t ? `mark-${t}` : ""}>{pct(x.rarity_percent, locale)}</span>
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </>
      )}
    </article>
  );
}

/** A favorite game's news as the same card: the game in a person's place. */
export function MagazineNews({ item }: { item: NewsItem }) {
  const { tr, locale, open } = useApp();
  const patch = item.kind === "patch";
  const openPost = () => {
    tick();
    open({ kind: "news", appid: item.appid, gid: item.gid, item, game: item.game });
  };
  const openGame = () => {
    tick();
    open({ kind: "game", ref: { game_id: item.game.game_id ?? undefined, platform: item.game.platform, title_id: item.game.title_id, name: item.game.name, icon_url: item.game.icon_url } });
  };
  return (
    <article className="mag">
      <header className="mag-by">
        <button type="button" aria-label={item.game.name} onClick={openGame}>
          <Cover src={item.game.icon_url} className="mag-by-cover" />
        </button>
        <span className="mag-who">
          <span className="mag-names-row">
            <button type="button" className="mag-names t-label clamp-1" onClick={openGame}>
              {item.game.name}
            </button>
            <span className="mag-time">{when(item.date, locale)}</span>
          </span>
          <span className="mag-sub clamp-1">{tr("magFromDevs")}</span>
        </span>
      </header>
      <button type="button" className="mag-art" onClick={openPost}>
        {item.image ? (
          <Cover src={item.image} className="mag-pic" />
        ) : (
          <span className="mag-pic mag-pic-game">
            <img src={item.game.icon_url ?? ""} alt="" className="mag-pic-ground" />
            <Cover src={item.game.icon_url} className="mag-pic-cover" />
          </span>
        )}
        <span className={`mag-badge shape-flower6 mag-kind-${patch ? "patch" : "news"}`}>
          <Icon name={patch ? "patch" : "news"} size={24} />
        </span>
      </button>
      <button type="button" className="mag-body" onClick={openPost}>
        <span className="mag-kicker">
          <span className="mag-kind-word">{patch ? tr("newsPatch") : tr("newsPost")}</span>
        </span>
        <span className="mag-name t-card clamp-3">{item.title}</span>
        {item.excerpt && <span className="mag-desc clamp-2">{item.excerpt}</span>}
      </button>
    </article>
  );
}

/** A card while the feed is on its way: its very shape. */
export function MagazineSkel() {
  return (
    <div className="mag mag-skel" aria-hidden="true">
      <div className="mag-by">
        <span className="skel skel-face" style={{ width: 36, height: 36 }} />
        <span className="mag-who">
          <span className="skel skel-line" style={{ width: "40%" }} />
          <span className="skel skel-line" style={{ width: "22%", marginTop: 6 }} />
        </span>
      </div>
      <span className="skel mag-pic" />
      <div className="mag-body">
        <span className="skel skel-line" style={{ width: "70%", height: 18 }} />
        <span className="skel skel-line" style={{ width: "90%" }} />
      </div>
    </div>
  );
}
