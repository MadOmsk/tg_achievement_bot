import type { Ref } from "react";
import type { FeedItem } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { CoverImg, FitImg, gameRefOf, useOpenGame } from "../../shared/lib";
import { feedKey } from "../utils";
import { HeroGame } from "../hero-game/HeroGame";
import { HeroMarks } from "../hero-marks/HeroMarks";
import { PostLead } from "../post-lead/PostLead";

export function UnlockHero({
  item,
  secret = false,
  locale,
  author = true,
  minimal = false,
  onReveal,
  onOpenPerson,
}: {
  item: FeedItem;
  secret?: boolean;
  author?: boolean;
  minimal?: boolean;
  locale: Locale;
  onReveal?: (key: string) => void;
  onOpenPerson?: (tgId: number) => void;
}) {
  return (
    <UnlockCard
      item={item}
      locale={locale}
      secret={secret}
      author={author}
      minimal={minimal}
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
  minimal = false,
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
  /** Just the picture, the achievement's name and its game — no marks, progress or description. */
  minimal?: boolean;
  onOpen?: (item: FeedItem) => void;
  onOpenPerson?: (tgId: number) => void;
  onReveal?: (key: string) => void;
  artRef?: Ref<HTMLDivElement>;
}) {
  // A secret keeps its game, its score and its rarity on show; only the name
  // and the description are blurred until it is revealed.
  const score = item.gamerscore ? `${item.gamerscore} G` : null;
  const blur = secret ? "secret-blur" : undefined;
  const rarity = item.rarity_percent != null ? `${item.rarity_percent}%` : null;
  const open = onOpen && !secret;
  const openGame = useOpenGame();
  return (
    <div
      className={[
        "unlock-card",
        "has-fit",
        secret ? "is-secret" : open ? "is-open" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      role={open ? "button" : undefined}
      tabIndex={open ? 0 : undefined}
      onClick={open ? () => onOpen(item) : undefined}
    >
      <div ref={artRef} className="unlock-card-art">
        <span className="profile-hero-layers">
          <CoverImg
            src={item.icon_url}
            kind="achievement"
            className="profile-hero-art"
          />
        </span>
        <span className="profile-hero-wash" />
        <div className="unlock-card-head">
          {author ? (
            <PostLead
              item={item}
              locale={locale}
              onOpenPerson={onOpenPerson}
              whoOnly
            />
          ) : (
            <span />
          )}
          {!minimal && (
          <HeroMarks
            score={score}
            rarity={rarity}
            tier={item.tier_badge ? item.trophy_type : null}
          />
          )}
        </div>
      </div>
      <div className="unlock-card-fit">
        <FitImg src={item.icon_url} />
        {secret && (
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
        )}
      </div>
      {!minimal && (
        <div className="unlock-card-stage">
          <HeroGame item={item} locale={locale} link />
        </div>
      )}
      {minimal ? (
        <div className="unlock-card-copy is-minimal">
          <h2>
            <span className={blur}>{item.name}</span>
          </h2>
          {item.game && (
            <p
              className={item.title_id && openGame ? "minimal-game is-link" : "minimal-game"}
              onClick={
                item.title_id && openGame ? () => openGame(gameRefOf(item)) : undefined
              }
            >
              {item.game}
            </p>
          )}
        </div>
      ) : gameInCopy ? (
        <div className="unlock-card-foot">
          <HeroGame item={item} locale={locale} link />
          <div className="unlock-card-copy">
            <h2>
              <span className={blur}>{item.name}</span>
            </h2>
            <p className={blur}>{item.description || " "}</p>
          </div>
        </div>
      ) : (
        <div className="unlock-card-copy">
          <h2>
            <span className={blur}>{item.name}</span>
          </h2>
          <p className={blur}>{item.description || " "}</p>
        </div>
      )}
    </div>
  );
}
