import { useEffect, useRef, useState } from "react";
import { clubApi, gameApi } from "../../api";
import { currentMonth } from "../../core/people-utils";
import { peopleApi } from "../../api/people/peopleApi";
import { useApp } from "../../app/context";
import { useLoad } from "../../app/useLoad";
import { tick } from "../../core/haptic";
import { Empty, Field, Group, Row, Section, Spinner } from "../../ui/Controls";
import { Icon } from "../../ui/Icon";
import { Page } from "../../ui/Page";
import { Cover } from "../../ui/Pic";
import { PersonLine } from "./FollowsPage";
import { GameTile } from "../../parts/GameTile";
import { TrendMark } from "../../parts/TrendMark";
import "../game/Game.css";
import "./People.css";

function useDebounced(value: string, ms = 260): string {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return v;
}

export function SearchPage({ onClose, layer }: { onClose: () => void; layer: string }) {
  const { data, tr, locale, open } = useApp();
  const [q, setQ] = useState("");
  const query = useDebounced(q.trim());
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    window.setTimeout(() => input.current?.focus(), 250);
  }, []);
  const games = useLoad(query.length >= 2 ? `gs:${query}` : null, () => gameApi.searchGames(data, query));
  const people = useLoad(query.length >= 3 ? `ps:${query}` : null, () => peopleApi.search(data, query));
  const mayKnow = useLoad("mayknow", () => peopleApi.mayKnow(data));
  const suggested = useLoad("suggested", () => peopleApi.suggestions(data));
  const summary = useLoad(`summary:${currentMonth()}:search`, () => clubApi.fetchSummary(data, "following", { month: currentMonth() }));
  const trending = (summary.data?.games ?? []).slice(0, 6);

  const searching = query.length >= 2;
  const gameHits = searching ? (games.data?.games ?? []) : [];
  const peopleHits = query.length >= 3 ? (people.data?.people ?? []) : [];
  const busy = (searching && games.loading) || (query.length >= 3 && people.loading);

  return (
    <Page title={tr("searchTitle")} onBack={onClose} layer={layer}>
      <div className="fl-search sp-field">
        <Field
          icon="search"
          placeholder={tr("searchHint")}
          value={q}
          enterKeyHint="search"
          autoCorrect="off"
          autoCapitalize="off"
          onChange={(e) => setQ(e.target.value)}
          inputRef={input}
        />
        {busy && (
          <span className="sp-busy">
            <Spinner size={20} />
          </span>
        )}
      </div>

      {!searching && (
        <>
          <Group>
            <Row lead={<Icon name="people" />} title={tr("peopleFollowing")} chevron onClick={() => open({ kind: "follows", personId: null, which: "following" })} />
            <Row lead={<Icon name="user" />} title={tr("peopleFollowers")} chevron onClick={() => open({ kind: "follows", personId: null, which: "followers" })} />
          </Group>
          {!summary.data && summary.loading && (
            <Section title={tr("trending")}>
              <div className="rail favs" aria-hidden="true">
                {[0, 1, 2].map((i) => (
                  <span key={i} className="game-tile game-tile-skel skel" />
                ))}
              </div>
            </Section>
          )}
          {trending.length > 0 && (
            <Section title={tr("trending")}>
              <div className="rail favs">
                {trending.map((g) => (
                  <GameTile
                    key={g.game_id ?? `${g.platform}:${g.title_id}`}
                    cover={g.icon_url}
                    name={g.name ?? ""}
                    mark={<TrendMark count={g.count} />}
                    onOpen={() => open({ kind: "game", ref: { game_id: g.game_id ?? undefined, platform: g.platform, title_id: g.title_id, name: g.name, icon_url: g.icon_url } })}
                  />
                ))}
              </div>
            </Section>
          )}
          {(mayKnow.data?.people.length ?? 0) > 0 && (
            <Section title={tr("peopleMayKnow")}>
              <div className="group">
                <div className="group-items">
                  {mayKnow.data!.people.map((p) => (
                    <PersonLine key={p.id} person={p} sub={`${tr("mutualCount")} ${p.mutual}`} />
                  ))}
                </div>
              </div>
            </Section>
          )}
          {(suggested.data?.people.length ?? 0) > 0 && (
            <Section title={tr("peopleSuggested")}>
              <div className="group">
                <div className="group-items">
                  {suggested.data!.people.map((p) => (
                    <PersonLine key={p.id} person={p} />
                  ))}
                </div>
              </div>
            </Section>
          )}
        </>
      )}

      {searching && gameHits.length > 0 && (
        <Section title={tr("games")}>
          <div className="group">
            <div className="group-items">
              {gameHits.map((g) => (
                <button
                  key={g.game_id}
                  type="button"
                  className="row row-tap"
                  onClick={() => {
                    tick();
                    open({ kind: "game", ref: { game_id: g.game_id, platform: "", title_id: "", name: g.name } });
                  }}
                >
                  <Cover src={g.poster || g.hero} className="gp-rel-cover" />
                  <span className="row-text">
                    <span className="row-title clamp-2">{locale === "ru" && g.name_ru ? g.name_ru : g.name}</span>
                    <span className="row-sub">
                      {[g.year, g.players ? `${tr("gpPlayed")}: ${g.players}` : null].filter(Boolean).join(" · ")}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        </Section>
      )}

      {query.length >= 3 && peopleHits.length > 0 && (
        <Section title={tr("people")}>
          <div className="group">
            <div className="group-items">
              {peopleHits.map((p) => (
                <PersonLine key={p.id} person={p} />
              ))}
            </div>
          </div>
        </Section>
      )}

      {searching && !busy && games.data && gameHits.length === 0 && peopleHits.length === 0 && (
        <Empty icon="search" title={tr("gpSearchEmpty")} text={query.length < 3 ? tr("searchMin") : tr("noResults")} />
      )}
    </Page>
  );
}
