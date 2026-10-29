import { useMemo, useState } from "react";
import type { GameDlc, GameEdition } from "../../api";
import { gameArtOf, useArtTheme } from "../../app/artTheme";
import { useApp } from "../../app/context";
import { num, whenLabel, type TranslationKey } from "../../i18n";
import { Chip, Empty, Field, Section } from "../../ui/Controls";
import { openExternal } from "../../app/env";
import { tick } from "../../core/haptic";
import { GameLink } from "../../parts/GameLink";
import { consoleLabel } from "../../parts/platforms";
import { RichText } from "../../ui/RichText";
import { openImage } from "../../ui/Viewer";
import { Hero } from "../../ui/Hero";
import { Page } from "../../ui/Page";
import { Cover } from "../../ui/Pic";
import { addonName, cleanName } from "./names";
import { ListHead } from "./ListHead";
import { HltbSection } from "./GamePage";
import "./Game.css";

/** A search shows on the page from this many add-ons. */
const SEARCH_FROM = 12;

const KIND: Record<string, TranslationKey> = {
  season_pass: "gpDlcSeasonPass",
  soundtrack: "gpDlcSoundtrack",
};

/** One add-on as a row of its group, the way a news row is: its picture, its
 * kind (and hours) over its own name, its year on the right. */
export function DlcRow({
  dlc,
  game,
  gameNames,
  cover,
}: {
  dlc: GameDlc;
  game: string;
  gameNames: Array<string | null | undefined>;
  cover: string | null;
}) {
  const { tr, locale, open } = useApp();
  const kind = tr(KIND[dlc.kind ?? ""] ?? "gpDlcOne");
  const top = dlc.hours ? `${kind} · ${num(dlc.hours, locale)} ${tr("gpHoursUnit")}` : kind;
  return (
    <button
      type="button"
      className="row row-tap gp-news-row"
      onClick={() => {
        tick();
        open({ kind: "dlc", game, gameNames, cover, dlc });
      }}
    >
      <Cover src={dlc.image} className="gp-news-pic" />
      <span className="row-text">
        <b className={`gp-news-kind ${dlc.kind === "season_pass" ? "gp-news-post" : "gp-news-patch"}`}>{top}</b>
        <span className="gp-dlc-name">{addonName(dlc.name, gameNames)}</span>
      </span>
      {dlc.release_date && <span className="gp-news-day t-meta">{whenLabel(dlc.release_date, locale, true)}</span>}
    </button>
  );
}

/** A game's add-ons whole, on a page of their own (a game may have a
 * thousand), the newest first as on the game page, with a search. */
export function DlcPage({
  game,
  gameNames,
  cover,
  dlcs,
  onClose,
  layer,
}: {
  game: string;
  gameNames: Array<string | null | undefined>;
  cover: string | null;
  dlcs: GameDlc[];
  onClose: () => void;
  layer: string;
}) {
  const { tr, locale } = useApp();
  const [query, setQuery] = useState("");
  const theme = useArtTheme(gameArtOf(game) ?? cover);
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? dlcs.filter((d) => d.name.toLowerCase().includes(q)) : dlcs;
  }, [dlcs, query]);
  return (
    <Page title={game} onBack={onClose} hero layer={layer} className="list-page" style={theme.style}>
      <ListHead game={game} cover={cover} label={`${tr("gpDlc")} · ${num(dlcs.length, locale)}`} />
      {dlcs.length >= SEARCH_FROM && (
        <div className="list-filter">
          <Field icon="search" type="search" value={query} placeholder={tr("gpDlcSearch")} onChange={(e) => setQuery(e.target.value)} />
        </div>
      )}
      {shown.length > 0 ? (
        <div className="group gp-dlc-list">
          <div className="group-items">
            {shown.map((d, i) => (
              <DlcRow key={`${d.name}:${i}`} dlc={d} game={game} gameNames={gameNames} cover={cover} />
            ))}
          </div>
        </div>
      ) : (
        <Empty icon="search" title={tr("gpDlcNone")} />
      )}
    </Page>
  );
}

/** One add-on on a page of its own, as a post is: its picture, its kind and
 * day, its name, its game a tap away, what its store says, its hours and
 * where it is sold. */
export function DlcDetailPage({
  game,
  gameNames,
  cover,
  dlc,
  onClose,
  layer,
}: {
  game: string;
  gameNames: Array<string | null | undefined>;
  cover: string | null;
  dlc: GameDlc;
  onClose: () => void;
  layer: string;
}) {
  const { tr, locale } = useApp();
  const theme = useArtTheme(gameArtOf(game) ?? cover);
  const picture = dlc.image ?? cover;
  const stores = (dlc.stores ?? []).filter((s) => s.url);
  return (
    <Page title={game} onBack={onClose} hero layer={layer} style={theme.style}>
      <article className="np-article">
        <Hero full={Boolean(dlc.image)} ground={picture} onOpen={picture ? () => openImage(picture) : undefined}>
          {dlc.image ? <img src={dlc.image} alt="" className="hero-pic" /> : <Cover src={cover} className="hero-cover" />}
        </Hero>
        <div className="detail">
          <div className="detail-meta">
            <span className="chip chip-secondary">{tr(KIND[dlc.kind ?? ""] ?? "gpDlcOne")}</span>
            {dlc.release_date && <span>{whenLabel(dlc.release_date, locale)}</span>}
          </div>
          <h1 className="detail-title">{addonName(dlc.name, gameNames)}</h1>
          <GameLink name={game} cover={cover} onOpen={onClose} />
          {dlc.description && <RichText text={dlc.description} className="np-text" />}
          {stores.length > 0 && (
            <div className="gp-chips gp-dlc-stores">
              {stores.map((s) => (
                <Chip key={`${s.store}:${s.console}`} tone="tonal" icon="external" onClick={() => openExternal(s.url!)}>
                  {consoleLabel(s.console, s.store)}
                </Chip>
              ))}
            </div>
          )}
        </div>
        {dlc.hltb && <HltbSection hltb={dlc.hltb} />}
      </article>
    </Page>
  );
}

const EDITION: Record<string, TranslationKey> = {
  standard: "edStandard",
  deluxe: "edDeluxe",
  complete: "edComplete",
  ultimate: "edUltimate",
  gold: "edGold",
  goty: "edGoty",
  definitive: "edDefinitive",
  premium: "edPremium",
  anniversary: "edAnniversary",
  legendary: "edLegendary",
  collection: "edCollection",
  preorder: "edPreorder",
  bundle: "edBundle",
  addon_pack: "edAddonPack",
};

/** What a store says an edition's item is: a game, an add-on, in-game
 * currency; anything else is a bonus sold only inside the edition. */
const ITEM_KIND: Record<string, TranslationKey> = {
  game: "edItemGame",
  dlc: "gpDlcOne",
  consumable: "edItemCurrency",
};

const STORE: Record<string, string> = { xbox: "Xbox", steam: "Steam", psn: "PlayStation" };

/** One edition on a page of its own: its cover, its kind, its name, its game
 * a tap away, what it holds and where it is sold. */
export function EditionPage({
  game,
  cover,
  edition,
  gameNames,
  dlcs,
  onClose,
  layer,
}: {
  game: string;
  cover: string | null;
  edition: GameEdition;
  gameNames: Array<string | null | undefined>;
  dlcs: GameDlc[];
  onClose: () => void;
  layer: string;
}) {
  const { tr, open } = useApp();
  // An item is the game itself, or one of its add-ons by its own name.
  const dlcOf = (name: string) => {
    const own = addonName(name, gameNames).toLowerCase();
    return dlcs.find((d) => addonName(d.name, gameNames).toLowerCase() === own) ?? null;
  };
  const theme = useArtTheme(gameArtOf(game) ?? cover);
  const picture = edition.cover ?? cover;
  const stores = (edition.stores ?? []).filter((s) => s.url);
  const items = edition.items ?? [];
  return (
    <Page title={game} onBack={onClose} hero layer={layer} style={theme.style}>
      <article className="np-article">
        {edition.hero ? (
          <Hero full ground={edition.hero} onOpen={() => openImage(edition.hero!)}>
            <img src={edition.hero} alt="" className="hero-pic" />
          </Hero>
        ) : (
          <Hero ground={picture} onOpen={picture ? () => openImage(picture) : undefined}>
            <Cover src={picture} className="gallery-cover gp-ed-cover" />
          </Hero>
        )}
        <div className="detail">
          <div className="detail-meta">
            <span className="chip chip-secondary">{tr(EDITION[edition.kind ?? ""] ?? "edEdition")}</span>
          </div>
          <h1 className="detail-title">{cleanName(edition.name)}</h1>
          <GameLink name={game} cover={cover} onOpen={onClose} />
          {stores.length > 0 && (
            <div className="gp-chips gp-dlc-stores">
              {stores.map((s) => (
                <Chip key={s.store} tone="tonal" icon="external" onClick={() => openExternal(s.url!)}>
                  {STORE[s.store] ?? s.store}
                </Chip>
              ))}
            </div>
          )}
        </div>
        {items.length > 0 && (
          <Section title={tr("edInside")}>
            <div className="group gp-ed-items">
              <div className="group-items">
                {items.map((item) => {
                  const dlc = item.kind === "game" ? null : dlcOf(item.name);
                  const go =
                    item.kind === "game"
                      ? onClose
                      : dlc
                        ? () => open({ kind: "dlc", game, gameNames, cover, dlc })
                        : undefined;
                  const body = (
                    <>
                      <Cover src={item.kind === "game" ? cover : (dlc?.image ?? null)} className="gp-news-pic" />
                      <span className="row-text">
                        <span className="row-sub">{tr(ITEM_KIND[item.kind ?? ""] ?? "edItemBonus")}</span>
                        <span className="row-title">{cleanName(item.name)}</span>
                      </span>
                    </>
                  );
                  return go ? (
                    <button
                      key={item.name}
                      type="button"
                      className="row row-tap gp-news-row"
                      onClick={() => {
                        tick();
                        go();
                      }}
                    >
                      {body}
                    </button>
                  ) : (
                    <div key={item.name} className="row gp-news-row">
                      {body}
                    </div>
                  );
                })}
              </div>
            </div>
          </Section>
        )}
      </article>
    </Page>
  );
}
