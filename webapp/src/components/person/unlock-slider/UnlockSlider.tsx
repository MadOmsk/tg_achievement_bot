import { memo, useEffect, useRef, useState } from "react";
import { EffectCreative } from "swiper/modules";
import { Swiper, SwiperSlide } from "swiper/react";
import type { CreativeEffectOptions, Swiper as SwiperInstance } from "swiper/types";
import "swiper/css";
import "swiper/css/effect-creative";
import type { FeedItem } from "../../../api";
import type { Locale } from "../../../i18n";
import { UI_CONFIG } from "../../shared/constants";
import { feedKey, gameKey, veiled } from "../utils";
import { GameCard } from "../game-card/GameCard";
import { UnlockCard, UnlockHero } from "../unlock-card/UnlockCard";

const HOME_SLIDES = UI_CONFIG.HOME.MAX_CAROUSEL_SLIDES;

// Swiper's stock "creative" effect: the slide that leaves slips out at a third
// of the speed underneath the next one, shrinking and fading, while the next
// one slides in over it.
const CREATIVE_EFFECT: CreativeEffectOptions = {
  limitProgress: 2,
  prev: { translate: ["-34%", 0, -1], opacity: 0, scale: 0.94 },
  next: { translate: ["100%", 0, 0] },
};

/**
 * The dots under a carousel. They keep their own state and listen to the
 * Swiper themselves: if the carousel component held it, every slide change
 * would re-render the Swiper (and, looping, rebuild its cloned slides), which
 * showed up as flicker in the feed. The gallery's dots fade out once nobody
 * is swiping; the feed's stay.
 */
function SliderDots({
  swiper,
  slides,
  slideKey,
  stay,
}: {
  swiper: SwiperInstance;
  slides: FeedItem[];
  slideKey: (item: FeedItem) => string;
  stay: boolean;
}) {
  const n = slides.length;
  const hideRef = useRef(0);
  const [active, setActive] = useState(swiper.realIndex);
  const [using, setUsing] = useState(!stay);

  useEffect(() => {
    const markUse = () => {
      setUsing(true);
      window.clearTimeout(hideRef.current);
      hideRef.current = window.setTimeout(() => setUsing(false), 1400);
    };
    const onChange = () => {
      setActive(swiper.realIndex);
      markUse();
    };
    swiper.on("slideChange", onChange);
    swiper.on("touchStart", markUse);
    if (!stay) markUse();
    return () => {
      swiper.off("slideChange", onChange);
      swiper.off("touchStart", markUse);
      window.clearTimeout(hideRef.current);
    };
  }, [swiper, stay]);

  return (
    <div
      className={stay || using ? "unlock-dots is-live" : "unlock-dots"}
      role="tablist"
      aria-label={`${active + 1} / ${n}`}
    >
      {slides.map((item, i) => (
        <button
          key={slideKey(item)}
          type="button"
          className={i === active ? "is-on" : undefined}
          aria-label={`${i + 1} / ${n}`}
          onClick={() => swiper.slideToLoop(i)}
        />
      ))}
    </div>
  );
}

/**
 * Swiper with the creative effect and endless looping, plus the dots. In the
 * feed a swipe does not drag the card along: once it is clearly a swipe the
 * whole slide change plays out; the gallery in a profile follows the finger.
 */
function UnlockSliderBase({
  items,
  locale,
  revealed,
  showSecrets,
  onReveal,
  onOpenPerson,
  variant = "hero",
  author = true,
  minimal = false,
}: {
  items: FeedItem[];
  locale: Locale;
  revealed?: Set<string>;
  showSecrets?: boolean;
  onReveal?: (key: string) => void;
  onOpenPerson?: (tgId: number) => void;
  variant?: "hero" | "feed" | "game";
  /** Whose achievement it is, in the card's corner (off on a person's own page). */
  author?: boolean;
  /** Gallery form: picture, name and game only. */
  minimal?: boolean;
}) {
  const slides = variant === "feed" ? items : items.slice(0, HOME_SLIDES);
  const slideKey = variant === "game" ? gameKey : feedKey;
  const n = slides.length;
  const feedDots = variant === "feed";
  // Set once, when Swiper mounts: the only state this component has.
  const [swiper, setSwiper] = useState<SwiperInstance | null>(null);

  return (
    <div className={feedDots ? "unlock-slider is-feed" : "unlock-slider"}>
      <Swiper
        className="unlock-swiper"
        modules={[EffectCreative]}
        effect="creative"
        creativeEffect={CREATIVE_EFFECT}
        speed={480}
        followFinger={!feedDots}
        threshold={feedDots ? 12 : 3}
        // A profile gallery turns over on a short drag (12% of the width, not
        // half of it, which is Swiper's default).
        longSwipesRatio={feedDots ? 0.5 : 0.12}
        loop={n > 2}
        onSwiper={setSwiper}
      >
        {slides.map((item) => {
          const secret = veiled(item, feedKey(item), revealed, showSecrets);
          return (
            <SwiperSlide key={slideKey(item)} className="unlock-slide">
              {variant === "game" ? (
                <GameCard item={item} />
              ) : feedDots ? (
                <UnlockCard
                  item={item}
                  locale={locale}
                  secret={secret}
                  author={author}
                  gameInCopy
                  onOpenPerson={onOpenPerson}
                  onReveal={onReveal}
                />
              ) : (
                <UnlockHero
                  item={item}
                  secret={secret}
                  locale={locale}
                  author={author}
                  minimal={minimal}
                  onReveal={onReveal}
                  onOpenPerson={onOpenPerson}
                />
              )}
            </SwiperSlide>
          );
        })}
      </Swiper>
      {n > 1 && swiper && (
        <SliderDots
          swiper={swiper}
          slides={slides}
          slideKey={slideKey}
          stay={feedDots}
        />
      )}
    </div>
  );
}

export const UnlockSlider = memo(UnlockSliderBase);
