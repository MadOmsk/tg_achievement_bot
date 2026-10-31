import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { GameCard } from "../../api";
import { passApi, type StoreGameHit } from "../../api/season-pass/seasonPassApi";
import { useApp } from "../../app/context";
import { useLoad } from "../../app/useLoad";
import { tick } from "../../core/haptic";
import { Empty, Field, Spinner } from "../../ui/Controls";
import { Page } from "../../ui/Page";
import { Cover } from "../../ui/Pic";
import "../people/People.css";

function useDebounced(value: string, ms = 350): string {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return v;
}

/** The super-admin's way to put a game the catalog lacks into it (owner,
 * 2026-10-30), laid out as the app's search: Steam's and Xbox's own catalogs
 * are searched, and what ours already has is not offered. A pick is added,
 * the stores fill it in later, and its page opens — or, from the pass's prize
 * editor, it is handed back there (`onAdded`). */
export function AddGamePage({ onClose, layer, onAdded }: {
  onClose: () => void;
  layer: string;
  onAdded?: (game: GameCard) => void;
}) {
  const { data, tr, toast, open } = useApp();
  const [q, setQ] = useState("");
  const query = useDebounced(q.trim());
  const input = useRef<HTMLInputElement>(null);
  const [adding, setAdding] = useState(false);
  useEffect(() => {
    window.setTimeout(() => input.current?.focus(), 250);
  }, []);
  const found = useLoad(query.length >= 2 ? `store-games:${query}` : null, () => passApi.searchStoreGames(data, query));
  const hits = query.length >= 2 ? (found.data?.games ?? []) : [];

  const add = async (hit: StoreGameHit) => {
    if (adding) return;
    tick();
    setAdding(true);
    try {
      const res = await passApi.addGame(data, hit);
      if (res.made) toast(tr("addGameDone"));
      if (onAdded) {
        onAdded(res.game);
        onClose();
        return;
      }
      open({ kind: "game", ref: { game_id: res.game.game_id, platform: "", title_id: "", name: res.game.name } });
    } catch {
      toast(tr("somethingWrong"), "error");
    } finally {
      setAdding(false);
    }
  };

  return (
    <Page title={tr("addGameTitle")} onBack={onClose} layer={layer}>
      <div className="fl-search sp-field">
        <Field
          icon="search"
          placeholder={tr("addGameFind")}
          value={q}
          enterKeyHint="search"
          autoCorrect="off"
          autoCapitalize="off"
          onChange={(e) => setQ(e.target.value)}
          inputRef={input}
        />
        {(found.loading || adding) && (
          <span className="sp-busy">
            <Spinner size={20} />
          </span>
        )}
      </div>

      {query.length < 2 && <Empty icon="search" title={tr("addGameTitle")} text={tr("addGameHint")} />}

      {hits.length > 0 && (
        <section className="sec">
          <div className="group">
            <div className="group-items">
              {hits.map((hit) => (
                <button
                  key={hit.stores.map((s) => `${s.store}:${s.id}`).join("|")}
                  type="button"
                  className="row row-tap"
                  disabled={adding}
                  onClick={() => void add(hit)}
                >
                  <Cover src={hit.image} className="gp-rel-cover" />
                  <span className="row-text">
                    <span className="row-title clamp-2">{hit.name}</span>
                    <span className="row-sub">{hit.stores.map((s) => (s.store === "steam" ? "Steam" : "Xbox")).join(" · ")}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        </section>
      )}

      {query.length >= 2 && !found.loading && found.data && hits.length === 0 && (
        <Empty icon="search" title={tr("addGameNone")} text={tr("addGameHint")} />
      )}
    </Page>
  );
}

/** The same page over a sheet (the prize editor): a page renders in place,
 * under every sheet, so this one goes to the body above them. */
export function AddGameOver(props: {
  onClose: () => void;
  layer: string;
  onAdded: (game: GameCard) => void;
}) {
  return createPortal(<div className="page-over">{<AddGamePage {...props} />}</div>, document.body);
}
