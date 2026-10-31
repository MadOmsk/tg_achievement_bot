import { Fragment, useEffect, useRef, useState, type CSSProperties } from "react";
import { ApiError } from "../../api";
import { passApi, type PassEditor, type PassEditorItem, type PassReward, type PassState } from "../../api/season-pass/seasonPassApi";
import { useApp } from "../../app/context";
import type { Palette } from "../../app/env";
import { TIER_NAME } from "../../app/views";
import { tick } from "../../core/haptic";
import { formatMonth } from "../../core/people-utils";
import {
  claimReward,
  claimTheme,
  discardPass,
  PALETTE_NAMES,
  passProgress,
  publishPass,
  rewardOpen,
  setEditMonth,
  setSeasonImage,
  setSeasonTitle,
  usePass,
  type Tier,
} from "../../core/season-pass";
import { num, plural } from "../../i18n";
import { Button, Empty, Field, IconButton, Row, Toggle } from "../../ui/Controls";
import { capital } from "../../parts/Months";
import { Icon, type IconName } from "../../ui/Icon";
import { Hero } from "../../ui/Hero";
import { Cropper } from "../../ui/Cropper";
import { Confirm, Page, Sheet } from "../../ui/Page";
import { useArtTheme } from "../../app/artTheme";
import { CodeSheet, ItemEditor, platformName, PrizePlatformMark, shrink, TakersSheet } from "./SeasonPassRewards";
import "../settings/Settings.css";
import "./SeasonPass.css";
import { PointsCoin } from "../../parts/AchRow";

export function RewardArt({ t, size = 56 }: { t: { palette: string }; size?: number }) {
  return (
    <span className={`pass-art swatch-${t.palette}`} style={{ width: size, height: size }}>
      <span className="swatch-dot shape-cookie9" style={{ width: size, height: size }} />
    </span>
  );
}

export function rewardName(t: Tier, tr: ReturnType<typeof useApp>["tr"]): string {
  return `${tr("passTheme")} «${tr(PALETTE_NAMES[t.palette])}»`;
}

/** One reward of the season: a theme of a level, or a prize the super-admin
 * put in (owner, 2026-10-27) — one timeline, by their points. In the editor
 * each carries its draft (`edit`). */
type Item =
  | { key: string; kind: "theme"; points: number; t: Tier; edit?: PassEditorItem }
  | { key: string; kind: "prize"; points: number; r: PassReward; edit?: PassEditorItem };

const SPARKS = 12;

/** The editor's levels as the timeline draws them. */
function draftItems(items: PassEditorItem[]): Item[] {
  return items.map((e) =>
    e.kind === "theme"
      ? {
          key: `theme:${e.id}`,
          kind: "theme",
          points: e.points,
          edit: e,
          t: { id: e.id, level: 0, points: e.points, tier: e.tier ?? "common", palette: (e.palette ?? "graphite") as Palette, claimed: false },
        }
      : {
          key: `prize:${e.id}`,
          kind: "prize",
          points: e.points,
          edit: e,
          r: {
            id: e.id,
            title: e.title ?? "",
            description: e.description,
            points: e.points,
            kind: e.kind,
            tier: e.tier,
            game: e.game,
            platform: e.platform,
            image: e.image,
            total: e.codes.length,
            left: Math.max(0, e.codes.length - e.taken),
            code: null,
            removed: false,
          },
        },
  );
}

export function SeasonPassPage({ onClose, layer }: { onClose: () => void; layer: string }) {
  const { data, tr, locale, toast, open } = useApp();
  const current = usePass(data);
  useEffect(() => {
    void passApi.markSeen(data).catch(() => undefined);
  }, [data]);
  // An earlier month's pass, looked back on: its codes, what was claimed.
  const [viewMonth, setViewMonth] = useState<string | null>(null);
  const [past, setPast] = useState<PassState | null>(null);
  useEffect(() => {
    if (!viewMonth) {
      setPast(null);
      return;
    }
    let live = true;
    passApi
      .fetchPass(data, { month: viewMonth })
      .then((s) => live && setPast(s))
      .catch(() => live && toast(tr("somethingWrong"), "error"));
    return () => {
      live = false;
    };
  }, [data, viewMonth, toast, tr]);
  // The super-admin goes on into the months ahead that have a pass being
  // built: each as anybody will see it on its 1st — nothing got, no points,
  // its draft as if published (the editor's month is set to it).
  const [futureMonth, setFutureMonth] = useState<string | null>(null);
  const preview = futureMonth && current?.editor?.month === futureMonth ? previewOf(current.editor) : null;
  const state = preview ?? (viewMonth ? past : current);
  const lookingBack = Boolean(state && !state.current);
  const ahead = (current?.editor?.months ?? [])
    .filter((m) => m.month > (current?.month ?? "") && (m.levels > 0 || m.dirty > 0))
    .map((m) => m.month)
    .reverse();
  const months = [...ahead, ...(current?.months ?? [])];
  const at = months.indexOf(futureMonth ?? state?.month ?? "");
  const goMonth = (m: string | undefined) => {
    if (!m || !current) return;
    tick();
    if (m > current.month) {
      setViewMonth(null);
      setFutureMonth(m);
      void setEditMonth(data, m).catch(() => toast(tr("somethingWrong"), "error"));
      return;
    }
    if (futureMonth) {
      setFutureMonth(null);
      void setEditMonth(data, null).catch(() => undefined);
    }
    setViewMonth(m === current.month ? null : m);
  };
  // The month's cover heads the page, and the page takes its colours from
  // it, as a game's page does from its art.
  const cover = state?.image ?? null;
  const art = useArtTheme(cover);
  const p = passProgress(state);
  const { tiers, points } = p;
  // The super-admin's editor: the draft on the timeline, a tap opens a level.
  const [editing, setEditing] = useState(false);
  const editor = state?.admin ? state.editor : undefined;
  const live: Item[] = [
    ...tiers.map((t) => ({ key: `theme:${t.id}`, kind: "theme" as const, points: t.points, t })),
    ...p.rewards.map((r) => ({ key: `prize:${r.id}`, kind: "prize" as const, points: r.points, r })),
  ].sort((a, b) => a.points - b.points || (a.kind === b.kind ? 0 : a.kind === "theme" ? -1 : 1));
  const items = editing && editor ? draftItems(editor.items) : live;
  const ready = (i: Item) => !editing && !lookingBack && !preview && (i.kind === "theme" ? !i.t.claimed && points >= i.points : rewardOpen(i.r, points));
  const have = (i: Item) => !editing && (i.kind === "theme" ? i.t.claimed : Boolean(i.r.code));
  // Where "you are" sits on the timeline: after the last reward the points reach.
  const nowAt = items.filter((i) => points >= i.points).length;
  const next = live[live.filter((i) => points >= i.points).length] ?? null;
  const got = live.filter(have).length;
  const nameOf = (i: Item) => (i.kind === "theme" ? tr(PALETTE_NAMES[i.t.palette]) : i.r.title);
  const [popped, setPopped] = useState<{ keys: string[]; round: number }>({ keys: [], round: 0 });
  const [busy, setBusy] = useState<string | null>(null);
  const [code, setCode] = useState<number | null>(null);
  const [takers, setTakers] = useState<PassReward | null>(null);
  const [editingItem, setEditingItem] = useState<PassEditorItem | "new" | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [pickingMonth, setPickingMonth] = useState(false);
  const [naming, setNaming] = useState(false);
  const [covering, setCovering] = useState(false);
  const [coverCrop, setCoverCrop] = useState<string | null>(null);

  // Once, when the pass first comes: the timeline scrolled to "you are here".
  const scrolled = useRef(false);
  useEffect(() => {
    if (!state || scrolled.current) return;
    scrolled.current = true;
    // Everything got: the page stays at its head, nothing below to go to.
    if (nowAt <= 1 || got >= live.length) return;
    // Straight there as the page opens, before it is seen to move.
    requestAnimationFrame(() => {
      const row = document.getElementById("pass-now");
      const scroller = row?.closest<HTMLElement>("[data-scroll]");
      if (!row || !scroller) return;
      const top = row.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop;
      scroller.scrollTo({ top: Math.max(0, top - scroller.clientHeight / 2 + row.offsetHeight / 2) });
    });
  });

  const pop = (keys: string[]) => {
    tick();
    setPopped((x) => ({ keys, round: x.round + 1 }));
  };

  const take = async (i: Item) => {
    setBusy(i.key);
    try {
      if (i.kind === "theme") {
        await claimTheme(data, i.t.palette);
        pop([i.key]);
        window.setTimeout(() => toast(tr("passClaimed").replace("{name}", tr(PALETTE_NAMES[i.t.palette]))), 650);
      } else {
        await claimReward(data, i.r.id);
        pop([i.key]);
        window.setTimeout(() => setCode(i.r.id), 700);
      }
    } catch (err) {
      const gone = err instanceof ApiError && err.code === "gone";
      toast(tr(gone ? "passRewardGone" : "somethingWrong"), "error");
    } finally {
      setBusy(null);
    }
  };

  // Every theme waiting, one claim after another; each one bursts. A prize is
  // taken on its own: each opens its code.
  const claimAll = async () => {
    const all = p.waiting;
    if (!all.length) return;
    setBusy("all");
    try {
      for (const t of all) await claimTheme(data, t.palette);
      pop(all.map((t) => `theme:${t.id}`));
      window.setTimeout(() => toast(tr("passClaimedAll").replace("{n}", String(all.length))), 650);
    } catch {
      toast(tr("somethingWrong"), "error");
    } finally {
      setBusy(null);
    }
  };

  if (!state) {
    return (
      <Page title={tr("passTitle")} onBack={onClose} layer={layer} hero>
        <div className="pass-wait" aria-hidden="true">
          <span className="pass-wait-cover skel" />
          <span className="pass-wait-badge skel shape-flower6" />
          <div className="detail">
            <span className="pass-wait-chip skel" />
            <span className="pass-wait-title skel" />
          </div>
        </div>
        <div className="pass-tl pass-tl-wait">
          {[0, 1, 2].map((i) => (
            <span key={i} className="pass-tl-wait-row">
              <span className="pass-tl-wait-node skel shape-cookie9" />
              <span className="pass-tl-ghost skel" />
            </span>
          ))}
        </div>
      </Page>
    );
  }

  const shownCode = p.rewards.find((r) => r.id === code && r.code);
  const dirty = editor?.dirty ?? 0;

  const nowRow = (
    <li className="pass-tl-row pass-tl-now" id="pass-now" key="now">
      <span className="pass-tl-rail">
        <span className="pass-tl-me shape-burst12" />
      </span>
      <div className="pass-tl-here">
        {next ? (
          <span className="clamp-2">
            {tr("passNextShort")} <PointsCoin points={next.points - points} />{" "}
            {tr("passNextTo")} «{nameOf(next)}»
          </span>
        ) : (
          <span className="pass-tl-here-done">
            <Icon name="check" size={18} />
            {tr("passComplete")}
          </span>
        )}
      </div>
    </li>
  );

  // What a level is in the draft: new, changed, to go, or locked by a claim.
  const status = (e: PassEditorItem) =>
    e.taken > 0
      ? { cls: "lock", text: tr("passEditTaken").replace("{n}", String(e.taken)) }
      : e.remove
        ? { cls: "remove", text: tr("passEditRemove") }
        : e.draft
          ? { cls: "draft", text: tr("passEditDraft") }
          : e.changed
            ? { cls: "changed", text: tr("passEditChanged") }
            : null;

  const actions = preview ? (
    <button
      type="button"
      className="link-btn"
      onClick={() => {
        setFutureMonth(null);
        setEditing(true);
      }}
    >
      {tr("passEdit")}
    </button>
  ) : editing ? (
    <button type="button" className="link-btn" onClick={() => setEditing(false)}>
      {tr("passEditDone")}
    </button>
  ) : lookingBack ? null : p.waiting.length > 0 || state.admin ? (
    <>
      {p.waiting.length > 0 && (
        <button type="button" className="link-btn" disabled={busy != null} onClick={() => void claimAll()}>
          {tr("passClaimAll")}
        </button>
      )}
      {state.admin && (
        <button type="button" className="link-btn" onClick={() => setEditing(true)}>
          {tr("passEdit")}
        </button>
      )}
    </>
  ) : null;

  return (
    <Page
      title={editing ? tr("passEditTitle") : tr("passTitle")}
      onBack={futureMonth ? () => goMonth(current?.month) : onClose}
      layer={layer}
      hero={!editing}
      style={cover && !editing && art.settled ? art.style : undefined}
      className={`pass-page${editing ? " pass-editing" : ""}`}
      actions={actions}
    >
      {/* The season's head is an achievement's (owner, 2026-10-28): the
          month's cover on its own blurred ground, the days left where an
          achievement wears its rarity, then the season and its name. */}
      {!editing && (
        <>
          <div className="pass-ap-head">
            <Hero ground={cover} full>
              <span className="pass-ap-stage">
                {cover ? (
                  <img src={cover} alt="" className="hero-pic pass-ap-pic" />
                ) : (
                  <span className="pass-ap-pic pass-ap-month t-num">{formatMonth(state.month, locale, "sheet").split(" ")[0].toUpperCase()}</span>
                )}
              </span>
            </Hero>
            <span className="pass-ap-badge shape-flower6">
              {lookingBack ? (
                <Icon name="check" size={28} />
              ) : (
                <>
                  <b className="t-num">{state.days_left}</b>
                  <span>{tr("passDaysUnit")}</span>
                </>
              )}
            </span>
          </div>
          <div className="detail">
            <div className="detail-meta pass-ap-meta">
              <span className="chip chip-secondary">
                {tr("passSeason")} · {capital(formatMonth(state.month, locale, "sheet"))}
              </span>
              {/* A month ahead, seen only by the super-admin, as it will be. */}
              {preview && <span className="chip chip-outline">{tr("passPreview")}</span>}
            </div>
            {/* The season's name, the months either side of it on its right. */}
            <div className="pass-ap-title">
              <h1 className="detail-title">{state.title || capital(formatMonth(state.month, locale, "sheet").split(" ")[0])}</h1>
              {months.length > 1 && (
                <span className="pass-ap-nav">
                  <IconButton icon="back" label={tr("passMonthBefore")} disabled={at < 0 || at >= months.length - 1} onClick={() => goMonth(months[at + 1])} />
                  <IconButton icon="forward" label={tr("passMonthAfter")} disabled={at <= 0} onClick={() => goMonth(months[at - 1])} />
                </span>
              )}
            </div>
          </div>
        </>
      )}

      {editing && editor && (
        <div className="group pass-edit-months">
          <div className="group-items">
            <Row
              lead={<Lead icon="calendar" />}
              title={capital(formatMonth(editor.month, locale, "sheet"))}
              sub={tr("passEditMonth")}
              chevron
              onClick={() => {
                tick();
                setPickingMonth(true);
              }}
            />
            <Row
              lead={<Lead icon="sparkle" />}
              title={editor.title || tr("passEditNameNone")}
              sub={editor.title_changed ? `${tr("passEditName")} · ${tr("passEditChanged")}` : tr("passEditName")}
              chevron
              onClick={() => {
                tick();
                setNaming(true);
              }}
            />
            <Row
              lead={editor.image ? <img src={editor.image} alt="" className="pass-cover-thumb" /> : <Lead icon="image" />}
              title={editor.image ? tr("passCoverSet") : tr("passCoverNone")}
              sub={tr("passCover")}
              chevron
              onClick={() => {
                tick();
                setCovering(true);
              }}
            />
          </div>
        </div>
      )}
      {covering && editor && (
        <Sheet title={tr("passCover")} onClose={() => setCovering(false)} layer="pass-cover">
          <div className="pass-name-form">
            <p className="pass-cover-hint">{tr("passCoverHint")}</p>
            <label className="btn btn-filled btn-wide pass-cover-pick">
              <Icon name="image" size={20} />
              {editor.image ? tr("passCoverChange") : tr("passCoverPick")}
              <input
                type="file"
                accept="image/*"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (!file) return;
                  setCovering(false);
                  // Placed and zoomed first, as a face or a prize's picture is.
                  void shrink(file).then((blob) => setCoverCrop(URL.createObjectURL(blob)));
                }}
              />
            </label>
            {editor.image && (
              <Button
                variant="tonal"
                wide
                onClick={() => {
                  setCovering(false);
                  void setSeasonImage(data, null).catch(() => toast(tr("somethingWrong"), "error"));
                }}
              >
                {tr("passCoverRemove")}
              </Button>
            )}
          </div>
        </Sheet>
      )}
      {coverCrop && (
        <Cropper
          src={coverCrop}
          title={tr("passRewardPicPlace")}
          size={1600}
          aspect={16 / 9}
          onCancel={() => {
            URL.revokeObjectURL(coverCrop);
            setCoverCrop(null);
          }}
          onDone={(blob) => {
            URL.revokeObjectURL(coverCrop);
            setCoverCrop(null);
            void setSeasonImage(data, blob).catch(() => toast(tr("somethingWrong"), "error"));
          }}
        />
      )}
      {naming && editor && (
        <NameSheet
          value={editor.title ?? ""}
          onSave={(title) => {
            setNaming(false);
            void setSeasonTitle(data, title).catch(() => toast(tr("somethingWrong"), "error"));
          }}
          onClose={() => setNaming(false)}
        />
      )}
      {pickingMonth && editor && (
        <Sheet title={tr("passEditMonth")} onClose={() => setPickingMonth(false)} layer="pass-month">
          <div className="group">
            <div className="group-items">
              {editor.months.map((m, k) => (
                <Row
                  key={m.month}
                  lead={<Lead icon="calendar" />}
                  // The season's name first, when it has one; its month and rewards under it.
                  title={m.title || capital(formatMonth(m.month, locale, "sheet"))}
                  sub={[
                    m.title ? capital(formatMonth(m.month, locale, "sheet")) : null,
                    m.levels === 0 ? tr("passEditMonthEmpty") : plural(locale, m.levels, ["passRewardsOne", "passRewardsFew", "passRewardsMany"]).replace("{n}", String(m.levels)),
                    m.dirty ? tr("passEditMonthDirty").replace("{n}", String(m.dirty)) : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                  trail={m.month === editor.month ? <Icon name="check" size={20} /> : undefined}
                  onClick={() => {
                    tick();
                    setPickingMonth(false);
                    void setEditMonth(data, k === 0 ? null : m.month).catch(() => toast(tr("somethingWrong"), "error"));
                  }}
                />
              ))}
            </div>
          </div>
        </Sheet>
      )}
      {editing && (
        <div className="pass-edit-head">
          <p>{tr("passEditHint")}</p>
          <Button variant="tonal" icon="plus" onClick={() => setEditingItem("new")}>
            {tr("passEditAdd")}
          </Button>
        </div>
      )}

      {!editing && items.length === 0 && <Empty icon="calendar" title={tr("passEmpty")} />}
      <ol className="pass-tl">
        {!editing && !lookingBack && items.length > 0 && nowAt === 0 && nowRow}
        {items.map((i, index) => {
          const own = have(i);
          const can = ready(i);
          const reached = !editing && points >= i.points;
          const burst = popped.keys.includes(i.key) && own;
          const order = popped.keys.indexOf(i.key);
          const tone = `pass-tier-${i.kind === "theme" ? i.t.tier : (i.r.tier ?? "common")}`;
          const picture = i.kind === "prize" ? i.r.image || i.r.game?.hero || i.r.game?.poster : null;
          const mark = i.edit ? status(i.edit) : null;
          return (
            <Fragment key={i.key}>
              <li
                className={`pass-tl-row ${tone}${reached ? " pass-tl-reached" : ""}${own ? " pass-tl-have" : can ? " pass-tl-due" : ""}${burst ? " pass-tl-burst" : ""}${mark ? ` pass-tl-${mark.cls}` : ""}`}
                style={burst ? ({ "--delay": `${order * 140}ms` } as CSSProperties) : undefined}
                key={burst ? `${i.key}:${popped.round}` : i.key}
              >
                <span className="pass-tl-rail">
                  <span className={`pass-tl-node ${can ? "shape-sunny8" : i.kind === "prize" ? "shape-gem" : "shape-cookie9"}`}>
                    <Icon name={editing ? (i.kind === "theme" ? "palette" : "gift") : own ? "check" : can ? "gift" : reached ? "check" : "lock"} size={16} />
                  </span>
                  <span className="pass-tl-pts t-num">{num(i.points, locale)}</span>
                </span>
                <article
                  className={`pass-tl-card${editing ? " pass-tl-editable" : ""}`}
                  onClick={
                    editing && i.edit
                      ? () => {
                          tick();
                          if (i.edit!.taken > 0) toast(tr("passEditLocked"), "error");
                          else setEditingItem(i.edit!);
                        }
                      : undefined
                  }
                >
                  <span className="pass-tl-thumb">
                    {i.kind === "theme" ? (
                      <>
                        <span className={`pass-tl-wash swatch-${i.t.palette}`} aria-hidden="true">
                          <span className="swatch-dot" />
                        </span>
                        <RewardArt t={i.t} size={46} />
                      </>
                    ) : picture ? (
                      <img src={picture} alt="" loading="lazy" />
                    ) : (
                      <span className="pass-tl-gift">
                        <Icon name="gift" size={26} />
                      </span>
                    )}
                    {burst && (
                      <span className="pass-sparks" aria-hidden="true">
                        {Array.from({ length: SPARKS }, (_, k) => (
                          <i key={k} style={{ "--a": `${(360 / SPARKS) * k}deg`, "--d": `${44 + (k % 3) * 14}px` } as CSSProperties} />
                        ))}
                      </span>
                    )}
                  </span>
                  <span className="pass-tl-text">
                    <span className="pass-tl-kind">
                      {i.kind === "theme"
                        ? `${tr("passTheme")} · ${tr(TIER_NAME[i.t.tier])}`
                        : `${i.r.kind === "game" ? tr("passPrizeGame") : tr("passPrizeCode")} · ${tr(TIER_NAME[i.r.tier ?? "common"])}`}
                      {i.kind === "prize" && i.r.platform && (
                        <span className="pass-tl-platform">
                          <PrizePlatformMark name={i.r.platform} size={16} />
                          {platformName(i.r.platform)}
                        </span>
                      )}
                    </span>
                    <span className="pass-tl-name">{nameOf(i)}</span>
                    {i.kind === "prize" && i.r.description && <span className="pass-tl-desc clamp-2">{i.r.description}</span>}
                    {mark && <span className={`pass-tl-mark pass-tl-mark-${mark.cls}`}>{mark.text}</span>}
                    <span className="pass-tl-meta t-num">
                      {!editing && !reached && !own && (
                        <span>
                          {tr("passNextShort")} {num(i.points - points, locale)}
                        </span>
                      )}
                      {!editing && i.kind === "prize" && i.r.game && (
                        <button
                          type="button"
                          className="pass-tl-link"
                          onClick={() => {
                            tick();
                            open({ kind: "game", ref: { game_id: i.r.game!.game_id, platform: "", title_id: "", name: i.r.game!.name } });
                          }}
                        >
                          {tr("passPrizeGameOpen")} ›
                        </button>
                      )}
                    </span>
                    {own && i.kind === "prize" ? (
                      <Button variant="tonal" className="pass-tl-btn" icon="key" onClick={() => setCode(i.r.id)}>
                        {tr("passRewardMine")}
                      </Button>
                    ) : can ? (
                      <Button
                        variant="filled"
                        className="pass-tl-btn pass-claim"
                        icon="gift"
                        busy={busy === i.key}
                        disabled={busy != null && busy !== i.key}
                        onClick={() => void take(i)}
                      >
                        {tr("passClaim")}
                      </Button>
                    ) : null}
                  </span>
                  {own && i.kind === "theme" && (
                    <span className="pass-tl-done">
                      <Icon name="check" size={26} />
                    </span>
                  )}
                  {i.kind === "prize" && !editing && i.r.total > 0 && (
                    <Stock left={i.r.left} total={i.r.total} onOpen={i.r.left < i.r.total ? () => setTakers(i.r) : undefined} />
                  )}
                  {editing && i.edit && (
                    <span className="pass-tl-pencil">
                      <Icon name={i.edit.taken > 0 ? "lock" : "forward"} size={16} />
                    </span>
                  )}
                </article>
              </li>
              {!editing && !lookingBack && index === nowAt - 1 && nowRow}
            </Fragment>
          );
        })}
      </ol>

      {!editing && <p className="pass-how">{tr("passHow")}</p>}

      {editing && dirty > 0 && (
        <div className="dock">
          <div className="bar pass-publish">
            <Button variant="text" onClick={() => setDiscarding(true)}>
              {tr("passEditDiscard")}
            </Button>
            <Button variant="filled" icon="check" onClick={() => setPublishing(true)}>
              {tr("passEditPublish").replace("{n}", String(dirty))}
            </Button>
          </div>
        </div>
      )}

      {shownCode && <CodeSheet reward={shownCode} onClose={() => setCode(null)} />}
      {takers && <TakersSheet reward={takers} onClose={() => setTakers(null)} />}
      {editingItem && editor && (
        <ItemEditor item={editingItem === "new" ? null : editingItem} editor={editor} onClose={() => setEditingItem(null)} />
      )}
      {publishing && <PublishSheet dirty={dirty} onClose={() => setPublishing(false)} />}
      {discarding && (
        <Confirm
          text={tr("passEditDiscardAsk")}
          yes={tr("passEditDiscard")}
          no={tr("cancel")}
          danger
          onNo={() => setDiscarding(false)}
          onYes={() => {
            setDiscarding(false);
            discardPass(data).catch(() => toast(tr("somethingWrong"), "error"));
          }}
        />
      )}
    </Page>
  );
}

/** One tap makes the draft the pass; «Оповестить всех» tells of its new levels. */
function PublishSheet({ dirty, onClose }: { dirty: number; onClose: () => void }) {
  const { data, tr, toast } = useApp();
  const [notify, setNotify] = useState(true);
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    try {
      const done = await publishPass(data, notify);
      tick();
      toast(
        done.skipped
          ? tr("passEditPublishedSkipped").replace("{n}", String(done.skipped))
          : tr("passEditPublished"),
      );
      onClose();
    } catch {
      toast(tr("somethingWrong"), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet title={tr("passEditPublishTitle")} onClose={onClose} layer="pass-publish">
      <div className="pass-add">
        <p className="pass-publish-text">{tr("passEditPublishText").replace("{n}", String(dirty))}</p>
        <label className="pass-add-toggle">
          <span>
            <b>{tr("passRewardNotify")}</b>
            <small>{tr("passRewardNotifyHint")}</small>
          </span>
          <Toggle checked={notify} label={tr("passRewardNotify")} onChange={setNotify} />
        </label>
        <Button variant="filled" icon="check" wide busy={busy} onClick={() => void go()}>
          {tr("passEditPublishGo")}
        </Button>
      </div>
    </Sheet>
  );
}

/** How many of a prize's codes are left, as a badge on the card's right:
 * loud when few are, so people race for them. A tap shows who took them. */
function Stock({ left, total, onOpen }: { left: number; total: number; onOpen?: () => void }) {
  const { tr } = useApp();
  const hurry = left > 0 && left <= Math.max(1, Math.ceil(total * 0.25));
  const state = left === 0 ? "gone" : hurry ? "hurry" : "ok";
  const said =
    left === 0
      ? tr("passStockGone")
      : tr(hurry ? "passStockHurry" : "passStockLeft").replace("{n}", String(left)).replace("{total}", String(total));
  const shape = state === "hurry" ? "shape-sunny8" : state === "ok" ? "shape-cookie9" : "";
  const body = (
    <>
      <span className={`pass-stock-badge ${shape}`}>
        <b className="t-num">{left}</b>
      </span>
      <span className="pass-stock-label">{tr(state === "gone" ? "passStockGoneShort" : hurry ? "passStockHurryShort" : "passStockLeftShort")}</span>
    </>
  );
  // Nobody took one yet: nothing to show, so nothing to tap.
  if (!onOpen) {
    return (
      <span className={`pass-stock pass-stock-${state}`} role="img" aria-label={said}>
        {body}
      </span>
    );
  }
  return (
    <button
      type="button"
      className={`pass-stock pass-stock-${state}`}
      aria-label={`${said}. ${tr("passTakers")}`}
      onClick={(e) => {
        e.stopPropagation();
        tick();
        onOpen();
      }}
    >
      {body}
    </button>
  );
}

/** The month's pass's name, its theme: a draft until the month's publish. */
function NameSheet({ value, onSave, onClose }: { value: string; onSave: (title: string) => void; onClose: () => void }) {
  const { tr } = useApp();
  const [title, setTitle] = useState(value);
  return (
    <Sheet title={tr("passEditName")} onClose={onClose} layer="pass-name">
      <form
        className="pass-name-form"
        onSubmit={(e) => {
          e.preventDefault();
          onSave(title.trim());
        }}
      >
        <Field placeholder={tr("passEditNamePlaceholder")} hint={tr("passEditNameHint")} value={title} maxLength={40} autoFocus onChange={(e) => setTitle(e.target.value)} />
        <Button variant="filled" type="submit" wide disabled={title.trim() === value}>
          {tr("passEditNameSave")}
        </Button>
        {value && (
          <Button variant="tonal" type="button" wide onClick={() => onSave("")}>
            {tr("passEditNameClear")}
          </Button>
        )}
      </form>
    </Sheet>
  );
}

/** A settings row's leading icon, as Settings draws it: a cookie of the
 * secondary container. */
function Lead({ icon }: { icon: IconName }) {
  return (
    <span className="set-lead set-lead-secondary shape-cookie9">
      <Icon name={icon} size={20} />
    </span>
  );
}

/** The edited month's pass as a person will see it on its 1st: its levels
 * with their drafts laid in (what is to go left out), nothing got, no points. */
function previewOf(editor: PassEditor): PassState {
  const levels = editor.items.filter((e) => !e.remove);
  const [year, month] = editor.month.split("-").map(Number);
  return {
    ok: true,
    month: editor.month,
    points: 0,
    days_left: new Date(year, month, 0).getDate(),
    tiers: levels
      .filter((e) => e.kind === "theme")
      .map((e, n) => ({ id: e.id, level: n + 1, points: e.points, tier: e.tier ?? "common", palette: e.palette ?? "graphite", claimed: false })),
    rewards: levels
      .filter((e) => e.kind !== "theme")
      .map((e) => ({
        id: e.id,
        title: e.title ?? "",
        description: e.description,
        points: e.points,
        kind: e.kind as "game" | "code",
        tier: e.tier,
        game: e.game,
        platform: e.platform,
        image: e.image,
        total: e.codes.length,
        left: e.codes.length,
        code: null,
        removed: false,
      })),
    admin: false,
    current: true,
    months: [editor.month],
    title: editor.title,
    image: editor.image,
  };
}
