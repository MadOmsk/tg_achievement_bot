import { useState } from "react";
import { EffectCreative } from "swiper/modules";
import { Swiper, SwiperSlide } from "swiper/react";
import type { CreativeEffectOptions } from "swiper/types";
import "swiper/css";
import "swiper/css/effect-creative";
import type { FeedItem } from "../../../api";
import { t, timeAgo, type Locale } from "../../../i18n";
import { Avatar, CoverImg, FitImg, TierDisc, asTier, gameRefOf, useOpenGame, FEED_RATIO_MAX, isWide, useImageRatio } from "../../shared/lib";
import { HandleName } from "../../shared/lib/handle-name/HandleName";
import { feedKey, veiled } from "../utils";
import "./FeedPost.css";

// The same turn as Home's gallery: the leaving picture slips out at a third of
// the speed under the next one, shrinking and fading, as the next slides in.
const CREATIVE_EFFECT: CreativeEffectOptions = {
  limitProgress: 2,
  prev: { translate: ["-34%", 0, -1], opacity: 0, scale: 0.94 },
  next: { translate: ["100%", 0, 0] },
};

/**
 * One post in the Feed: the achievement's picture, with who and when over its
 * top, and on frosted glass over its foot the achievement's name, its worth and
 * its description, then the game. A tap anywhere on the post opens that game on
 * this person's progress. Several achievements of one person in one game
 * make one post whose pictures and text swipe; the author, the game and the
 * dots stay put.
 */
export function FeedPost({
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
  onOpenPerson: (personId: number) => void;
}) {
  const head = items[0];
  const openGame = useOpenGame();
  const many = items.length > 1;
  const [active, setActive] = useState(0);
  const canOpenGame = Boolean(openGame && head.title_id);
  // The frame takes the first picture's proportions, and every slide shares
  // it: a post does not change height as it is swiped. A wide one has its
  // text under the picture rather than over it.
  const ratio = useImageRatio(head.icon_url, { max: FEED_RATIO_MAX });
  const wide = isWide(ratio);

  return (
    <article
      className={["post", canOpenGame ? "is-link" : "", wide ? "is-wide" : "", many ? "has-dots" : ""].filter(Boolean).join(" ")}
      // The whole post opens the game on this person's progress; the author, the
      // game line and "Открыть" keep their own taps.
      onClick={
        canOpenGame
          ? (e) => {
              if ((e.target as HTMLElement).closest("button")) return;
              const open = items[active] ?? head;
              if (!veiled(open, feedKey(open), revealed, showSecrets)) openGame?.(gameRefOf(open));
            }
          : undefined
      }
    >
      <div className="post-stage">
        {/* Who and when, and in which game: over the picture's top. */}
        <header className="post-head">
          <button type="button" className="post-avatar" onClick={() => onOpenPerson(head.person_id)}>
            <Avatar name={head.person} personId={head.person_id} size={42} />
          </button>
          <span className="post-head-copy">
            <button type="button" className="post-name" onClick={() => onOpenPerson(head.person_id)}>
              <HandleName text={head.person} />
            </button>
            <span className="post-time">{timeAgo(head.unlocked_at, locale)}</span>
          </span>
        </header>
        <Swiper
          className="post-track"
          modules={[EffectCreative]}
          effect="creative"
          creativeEffect={CREATIVE_EFFECT}
          speed={420}
          followFinger
          threshold={3}
          longSwipesRatio={0.12}
          allowTouchMove={many}
          loop={many}
          onSlideChange={(swiper) => setActive(swiper.realIndex)}
        >
          {items.map((item) => {
            const key = feedKey(item);
            const secret = veiled(item, key, revealed, showSecrets);
            const blur = secret ? "secret-blur" : undefined;
            const tier = item.tier_badge ? asTier(item.trophy_type) : null;
            const marks = [
              item.rarity_percent != null ? `${item.rarity_percent}%` : null,
              item.gamerscore && !tier ? `${item.gamerscore} G` : null,
            ].filter(Boolean);
            return (
              <SwiperSlide key={key} className="post-slide">
                <div className="post-media" style={{ aspectRatio: ratio }}>
                  <CoverImg src={item.icon_url} kind="achievement" className="post-media-back" />
                  {/* All of the picture; the frame is its shape, within reason. */}
                  {/* A wide one fills its frame, its sides trimmed if it is wider still;
                      a square or tall one is all seen, against the top. */}
                  <FitImg src={item.icon_url} mode={wide ? "height" : "contain"} top />
                  {secret && (
                    <span className="post-veil">
                      <button type="button" className="btn post-veil-open" onClick={() => onReveal(key)}>
                        {t(locale, "reveal")}
                      </button>
                    </span>
                  )}
                </div>
                <div className="post-copy">
                  <div className="post-title">
                    <h2>
                      <span className={blur}>{item.name}</span>
                    </h2>
                    {(marks.length > 0 || tier) && (
                      <span className="post-marks">
                        {/* Rarity first, then the trophy's tier — as on every card. */}
                        {marks.join(" · ")}
                        {tier && marks.length > 0 && " · "}
                        {tier && <TierDisc tier={tier} size={14} />}
                      </span>
                    )}
                  </div>
                  {item.description && <p className={blur}>{item.description}</p>}
                  {head.game && (
                    <button
                      type="button"
                      className="post-game"
                      onClick={canOpenGame ? () => openGame?.(gameRefOf(head)) : undefined}
                      disabled={!canOpenGame}
                    >
                      <span className="post-game-name">{head.game}</span>
                    </button>
                  )}
                </div>
              </SwiperSlide>
            );
          })}
        </Swiper>
        {/* Inside the text's block, at its foot: the row stays while the slides move. */}
        {many && (
          <span className="post-dots" aria-hidden>
            {items.map((item, i) => (
              <span key={feedKey(item)} className={i === active ? "is-on" : undefined} />
            ))}
          </span>
        )}
      </div>
    </article>
  );
}
