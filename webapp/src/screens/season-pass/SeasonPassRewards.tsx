import { useEffect, useState } from "react";
import { ApiError, gameApi, type GameCard } from "../../api";
import { passApi, type Look, type PassEditor, type PassEditorItem, type PassItemInput, type PassReward, type PassTaker } from "../../api/season-pass/seasonPassApi";
import { PlatformMark } from "../../parts/AccountCard";
import { useApp } from "../../app/context";
import { capital } from "../../parts/Months";
import type { Palette } from "../../app/env";
import { TIER_NAME } from "../../app/views";
import { tick } from "../../core/haptic";
import { PALETTE_NAMES, removeItem, revertItem, saveItem } from "../../core/season-pass";
import { formatWhen, num, type TranslationKey } from "../../i18n";
import { Button, Field, Row, Spinner } from "../../ui/Controls";
import { AddGameOver } from "../home/AddGame";
import { Face } from "../../ui/Face";
import { Cover } from "../../ui/Pic";
import { Icon, type IconName } from "../../ui/Icon";
import { Cropper } from "../../ui/Cropper";
import { Confirm, Sheet } from "../../ui/Page";

/** A prize's code, the viewer's own, to copy. */
export function CodeSheet({ reward, onClose }: { reward: PassReward; onClose: () => void }) {
  const { tr, toast } = useApp();
  // The button itself says it is copied: a toast would cover it.
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const id = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(id);
  }, [copied]);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(reward.code ?? "");
      tick();
      setCopied(true);
    } catch {
      toast(tr("somethingWrong"), "error");
    }
  };
  return (
    <Sheet title={reward.title} onClose={onClose} layer={`reward:${reward.id}`}>
      <div className="pass-code">
        {reward.platform && (
          <span className="pass-code-platform">
            <PrizePlatformMark name={reward.platform} size={22} />
            {platformName(reward.platform)}
          </span>
        )}
        {reward.description && <p className="pass-code-desc">{reward.description}</p>}
        <code className="pass-code-text">{reward.code}</code>
        <Button variant="filled" icon={copied ? "check" : "copy"} wide onClick={() => void copy()}>
          {tr(copied ? "passRewardCopied" : "passRewardCopy")}
        </Button>
        <p className="pass-code-note">{tr("passRewardNote")}</p>
      </div>
    </Sheet>
  );
}

const LOOKS: Look[] = ["common", "rare", "legendary", "mythic"];

type Kind = PassItemInput["kind"];

/** What a level may give, in the order the drawer lists them; a new kind is
 * one more line here (and its form below). */
const KINDS: { kind: Kind; icon: IconName; name: TranslationKey; about: TranslationKey }[] = [
  { kind: "theme", icon: "palette", name: "passTheme", about: "passKindThemeAbout" },
  { kind: "game", icon: "gift", name: "passPrizeGame", about: "passKindGameAbout" },
  { kind: "code", icon: "key", name: "passPrizeCode", about: "passKindCodeAbout" },
];

/** The super-admin's editor of one level (owner, 2026-10-28): a theme, a game
 * or a code, its points. A change waits in the draft for the publish. */
export function ItemEditor({ item, editor, onClose }: { item: PassEditorItem | null; editor: PassEditor; onClose: () => void }) {
  const { data, tr, toast, locale } = useApp();
  const [kind, setKind] = useState<Kind>(item?.kind ?? "game");
  const [picking, setPicking] = useState(false);
  const kindOf = KINDS.find((k) => k.kind === kind) ?? KINDS[0];
  // A palette is one level's: the others' are left out.
  const used = new Set(editor.items.filter((e) => e.kind === "theme" && !e.remove && e.id !== item?.id).map((e) => e.palette));
  const free = editor.palettes.filter((p) => !used.has(p));
  const [palette, setPalette] = useState<string>(item?.palette ?? free[0] ?? "");
  const [tier, setTier] = useState<Look>(item?.tier ?? "common");
  const [prizeTier, setPrizeTier] = useState<Look>((item && item.kind !== "theme" ? item.tier : null) ?? "common");
  const [game, setGame] = useState<GameCard | null>(item?.game ?? null);
  const [platform, setPlatform] = useState<string | null>(item?.platform ? platformName(item.platform) : null);
  const [choosingPlatform, setChoosingPlatform] = useState(false);
  const [query, setQuery] = useState("");
  const [catalogHits, setCatalogHits] = useState<GameCard[]>([]);
  const [searching, setSearching] = useState(false);
  const [addingGame, setAddingGame] = useState(false);
  useEffect(() => {
    const q = query.trim();
    if (kind !== "game" || game || q.length < 2) {
      setCatalogHits([]);
      return;
    }
    let live = true;
    // Our catalog only; a game it lacks is added on a page of its own («Добавить игру»).
    const id = window.setTimeout(() => {
      setSearching(true);
      gameApi
        .searchGames(data, q)
        .then((res) => live && setCatalogHits(res.games.slice(0, 6)))
        .catch(() => undefined)
        .finally(() => live && setSearching(false));
    }, 350);
    return () => {
      live = false;
      window.clearTimeout(id);
    };
  }, [data, kind, game, query]);
  const gameName = (g: GameCard) => (locale === "ru" && g.name_ru ? g.name_ru : g.name);
  const [title, setTitle] = useState(item?.title ?? "");
  const [description, setDescription] = useState(item?.description ?? "");
  const [points, setPoints] = useState(String(item?.points ?? 0));
  const [codes, setCodes] = useState((item?.codes ?? []).join("\n"));
  const [codesTouched, setCodesTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(false);
  const [image, setImage] = useState<Blob | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  // A picture is placed and zoomed before it is kept, as a face is.
  const [cropping, setCropping] = useState<string | null>(null);
  const pick = async (file: File | undefined) => {
    if (!file) return;
    setCropping(URL.createObjectURL(await shrink(file)));
  };
  const cropped = (blob: Blob) => {
    if (cropping) URL.revokeObjectURL(cropping);
    setCropping(null);
    setImage(blob);
    setPreview((old) => {
      if (old) URL.revokeObjectURL(old);
      return URL.createObjectURL(blob);
    });
  };
  const list = codes
    .split(/\r?\n/)
    .map((c) => c.trim())
    .filter(Boolean);
  const theme = kind === "theme";
  const ready =
    /^\d+$/.test(points.trim()) &&
    (theme ? Boolean(palette) : title.trim().length > 0 && list.length > 0);
  const shown = preview || (item?.kind !== "theme" ? item?.image : null) || (game ? game.hero || game.poster : null);

  const save = async () => {
    setBusy(true);
    try {
      const input: PassItemInput = theme
        ? { kind, points: Number(points), palette, tier }
        : {
            kind,
            points: Number(points),
            title: title.trim(),
            description: description.trim(),
            game_id: kind === "game" ? (game?.game_id ?? null) : null,
            platform: platform?.trim() || null,
            tier: prizeTier,
            ...(item == null || codesTouched || item.kind === "theme" ? { codes: list } : {}),
          };
      await saveItem(data, item?.id ?? null, input, theme ? null : image);
      tick();
      toast(tr("passEditSaved"));
      onClose();
    } catch (err) {
      const code = err instanceof ApiError ? err.code : null;
      toast(tr(code === "palette_taken" ? "passEditPaletteTaken" : code === "taken" ? "passEditLocked" : "passRewardInvalid"), "error");
    } finally {
      setBusy(false);
    }
  };

  const run = async (what: () => Promise<void>) => {
    setBusy(true);
    try {
      await what();
      tick();
      onClose();
    } catch (err) {
      const locked = err instanceof ApiError && err.code === "taken";
      toast(tr(locked ? "passEditLocked" : "somethingWrong"), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet title={item ? tr("passEditLevel") : tr("passEditAdd")} onClose={onClose} layer={`pass-item:${item?.id ?? "new"}`}>
      <div className="pass-add">
        <div className="group">
          <div className="group-items">
            <Row
              lead={
                <span className="set-lead set-lead-secondary shape-cookie9">
                  <Icon name={kindOf.icon} size={20} />
                </span>
              }
              title={tr(kindOf.name)}
              sub={tr("passKind")}
              chevron
              onClick={() => {
                tick();
                setPicking(true);
              }}
            />
            {!theme && (
              <Row
                lead={<PrizePlatformMark name={platform} size={40} />}
                title={platform || tr("passPrizePlatformNone")}
                sub={tr("passPrizePlatform")}
                chevron
                onClick={() => {
                  tick();
                  setChoosingPlatform(true);
                }}
              />
            )}
          </div>
        </div>
        {theme ? (
          <>
            <div className="pass-edit-palettes">
              {editor.palettes.map((p) => (
                <button
                  key={p}
                  type="button"
                  className={`pass-edit-palette swatch-${p}${p === palette ? " is-on" : ""}`}
                  disabled={used.has(p)}
                  aria-pressed={p === palette}
                  onClick={() => {
                    tick();
                    setPalette(p);
                  }}
                >
                  <span className="swatch-dot shape-cookie9" />
                  <span>{tr(PALETTE_NAMES[p as Palette])}</span>
                </button>
              ))}
            </div>
            {!free.length && <p className="pass-edit-note">{tr("passEditNoPalette")}</p>}
            <LookPicker value={tier} onChange={setTier} />
          </>
        ) : (
          <>
            {kind === "game" &&
              (game ? (
                <button
                  type="button"
                  className="pass-add-game"
                  onClick={() => {
                    setGame(null);
                    setQuery("");
                  }}
                >
                  <Cover src={game.poster || game.hero} className="gp-rel-cover" />
                  <span className="pass-add-game-name">{gameName(game)}</span>
                  <span className="link-btn">{tr("passPrizeGameChange")}</span>
                </button>
              ) : (
                <div className="pass-add-search">
                  <Field
                    icon="search"
                    placeholder={tr("passPrizeGameFind")}
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    trail={
                      <button type="button" className="link-btn" onClick={() => setAddingGame(true)}>
                        {tr("addGameButton")}
                      </button>
                    }
                  />
                  {catalogHits.length > 0 && (
                    <div className="group">
                      <div className="group-items">
                        {catalogHits.map((g) => (
                          <Row
                            key={g.game_id}
                            lead={<Cover src={g.poster || g.hero} className="gp-rel-cover" />}
                            title={gameName(g)}
                            sub={g.year ? String(g.year) : tr("passPrizeGameInCatalog")}
                            onClick={() => {
                              setGame(g);
                              if (!title.trim()) setTitle(gameName(g));
                            }}
                          />
                        ))}
                      </div>
                    </div>
                  )}
                  {!searching && catalogHits.length === 0 && query.trim().length >= 2 && (
                    <p className="pass-edit-note">{tr("passPrizeGameNone")}</p>
                  )}
                </div>
              ))}
            <label className={`pass-add-pic${shown ? " pass-add-pic-on" : ""}`}>
              {shown ? <img src={shown} alt="" /> : <Icon name="image" size={24} />}
              <span>{shown ? tr("passRewardPicChange") : tr("passRewardPic")}</span>
              <input
                type="file"
                accept="image/*"
                onChange={(e) => {
                  void pick(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
            </label>
            <LookPicker value={prizeTier} onChange={setPrizeTier} />
            <Field label={tr("passRewardName")} value={title} maxLength={80} onChange={(e) => setTitle(e.target.value)} />
            <Field label={tr("passRewardAbout")} value={description} maxLength={500} onChange={(e) => setDescription(e.target.value)} />
          </>
        )}
        <Field
          label={tr("passRewardPoints")}
          inputMode="numeric"
          value={points}
          onChange={(e) => setPoints(e.target.value.replace(/\D/g, ""))}
        />
        <p className="pass-edit-scores">
          {tr("passEditScores")
            .replace("{top}", num(editor.scores.top, locale))
            .replace("{lastTop}", num(editor.scores.last_top, locale))
            .replace("{lastMedian}", num(editor.scores.last_median, locale))}
        </p>
        {!theme && (
          <label className="field">
            <span className="field-label">{tr("passRewardCodes")}</span>
            <span className="field-box pass-add-codes">
              <textarea
                rows={5}
                value={codes}
                placeholder={tr("passRewardCodesPlaceholder")}
                onChange={(e) => {
                  setCodes(e.target.value);
                  setCodesTouched(true);
                }}
                spellCheck={false}
              />
            </span>
            <span className="field-hint">{tr("passRewardCodesHint").replace("{n}", String(list.length))}</span>
          </label>
        )}
        <Button variant="filled" icon="check" wide busy={busy} disabled={!ready || busy} onClick={() => void save()}>
          {item ? tr("passEditSave") : tr("passRewardSave")}
        </Button>
        {item && (item.changed || item.remove) && (
          <Button variant="tonal" wide disabled={busy} onClick={() => void run(() => revertItem(data, item.id))}>
            {item.remove ? tr("passEditKeep") : tr("passEditRevert")}
          </Button>
        )}
        {item && !item.remove && (
          <Button variant="text" icon="trash" wide className="pass-edit-delete" disabled={busy} onClick={() => setAsking(true)}>
            {tr("passEditDelete")}
          </Button>
        )}
      </div>
      {choosingPlatform && (
        <PlatformSheet
          value={platform}
          onPick={(p) => {
            setPlatform(p);
            setChoosingPlatform(false);
          }}
          onClose={() => setChoosingPlatform(false)}
        />
      )}
      {picking && (
        <Sheet title={tr("passKind")} onClose={() => setPicking(false)} layer="pass-kind">
          <div className="group">
            <div className="group-items">
              {KINDS.map((k) => (
                <Row
                  key={k.kind}
                  lead={
                    <span className="set-lead set-lead-secondary shape-cookie9">
                      <Icon name={k.icon} size={22} />
                    </span>
                  }
                  title={tr(k.name)}
                  sub={tr(k.about)}
                  trail={k.kind === kind ? <Icon name="check" size={20} /> : undefined}
                  onClick={() => {
                    tick();
                    setPicking(false);
                    setKind(k.kind);
                  }}
                />
              ))}
            </div>
          </div>
        </Sheet>
      )}
      {asking && item && (
        <Confirm
          text={tr(item.draft ? "passEditDeleteDraftAsk" : "passEditDeleteAsk")}
          yes={tr("passEditDelete")}
          no={tr("cancel")}
          danger
          onNo={() => setAsking(false)}
          onYes={() => {
            setAsking(false);
            void run(() => removeItem(data, item.id));
          }}
        />
      )}
      {cropping && (
        <Cropper
          src={cropping}
          title={tr("passRewardPicPlace")}
          size={1024}
          onCancel={() => {
            URL.revokeObjectURL(cropping);
            setCropping(null);
          }}
          onDone={cropped}
        />
      )}
      {addingGame && (
        <AddGameOver
          layer="pass-add-game"
          onClose={() => setAddingGame(false)}
          onAdded={(g) => {
            setGame(g);
            if (!title.trim()) setTitle(gameName(g));
          }}
        />
      )}
    </Sheet>
  );
}

/** A phone's photo made small enough to send: at most 1600 px on its longer
 * side, a JPEG. The server saves it again whatever it gets. */
export async function shrink(file: File): Promise<Blob> {
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((done) => canvas.toBlob(done, "image/jpeg", 0.88));
    return blob ?? file;
  } catch {
    return file;
  }
}

// The platforms offered first; anything else is typed.
const PRESETS = ["Xbox", "PlayStation", "Steam"];
const OLD_KEYS: Record<string, string> = { xbox: "Xbox", psn: "PlayStation", steam: "Steam" };

/** A prize's platform as written; the keys an early draft kept read as names. */
export function platformName(text: string): string {
  return OLD_KEYS[text] ?? text;
}

function platformKey(text: string | null): string | null {
  const t = (text ?? "").trim().toLowerCase();
  if (t.startsWith("xbox")) return "xbox";
  if (t.startsWith("playstation") || t === "psn" || /^ps(\s?\d| vita)?$/.test(t)) return "psn";
  if (t.startsWith("steam")) return "steam";
  return null;
}

/** The platform's own mark when it is one we know, else a gamepad. */
export function PrizePlatformMark({ name, size }: { name: string | null; size: number }) {
  const key = platformKey(name);
  return key ? (
    <PlatformMark platform={key} size={size} />
  ) : (
    <span className="set-lead set-lead-secondary shape-cookie9" style={{ width: size, height: size }}>
      <Icon name="gamepad" size={Math.round(size * 0.55)} />
    </span>
  );
}

function PlatformSheet({ value, onPick, onClose }: { value: string | null; onPick: (p: string | null) => void; onClose: () => void }) {
  const { tr } = useApp();
  const [own, setOwn] = useState(value && !PRESETS.includes(value) ? value : "");
  return (
    <Sheet title={tr("passPrizePlatform")} onClose={onClose} layer="pass-platform">
      <div className="pass-platforms">
        <div className="group">
          <div className="group-items">
            {PRESETS.map((p) => (
              <Row
                key={p}
                lead={<PrizePlatformMark name={p} size={36} />}
                title={p}
                trail={p === value ? <Icon name="check" size={20} /> : undefined}
                onClick={() => {
                  tick();
                  onPick(p);
                }}
              />
            ))}
            <Row
              lead={<PrizePlatformMark name={null} size={36} />}
              title={tr("passPrizePlatformNone")}
              trail={value == null ? <Icon name="check" size={20} /> : undefined}
              onClick={() => {
                tick();
                onPick(null);
              }}
            />
          </div>
        </div>
        <form
          className="pass-platform-own"
          onSubmit={(e) => {
            e.preventDefault();
            if (own.trim()) onPick(own.trim());
          }}
        >
          <Field
            label={tr("passPrizePlatformOwn")}
            placeholder={tr("passPrizePlatformOwnHint")}
            value={own}
            maxLength={40}
            onChange={(e) => setOwn(e.target.value)}
          />
          <Button variant="tonal" type="submit" disabled={!own.trim()}>
            {tr("passPrizePlatformUse")}
          </Button>
        </form>
      </div>
    </Sheet>
  );
}

/** Who took a prize's codes, the latest first; a face opens its person. */
export function TakersSheet({ reward, onClose }: { reward: PassReward; onClose: () => void }) {
  const { data, tr, locale, open } = useApp();
  const [takers, setTakers] = useState<PassTaker[] | null>(null);
  useEffect(() => {
    let live = true;
    passApi
      .takers(data, reward.id)
      .then((res) => live && setTakers(res.takers))
      .catch(() => live && setTakers([]));
    return () => {
      live = false;
    };
  }, [data, reward.id]);
  return (
    <Sheet title={tr("passTakers")} onClose={onClose} layer={`takers:${reward.id}`}>
      <div className="pass-takers">
        <p className="pass-takers-sum t-num">
          {tr("passTakersSum")
            .replace("{taken}", String(reward.total - reward.left))
            .replace("{total}", String(reward.total))}
        </p>
        {takers == null ? (
          <Spinner />
        ) : takers.length === 0 ? (
          <p className="pass-takers-none">{tr("passTakersNone")}</p>
        ) : (
          <div className="group">
            <div className="group-items">
              {takers.map((t) => (
                <Row
                  key={`${t.person_id}:${t.claimed_at}`}
                  lead={<Face personId={t.person_id} name={t.name} size={40} />}
                  title={t.name}
                  sub={formatWhen(t.claimed_at, locale)}
                  chevron
                  onClick={() => {
                    tick();
                    onClose();
                    open({ kind: "person", personId: t.person_id });
                  }}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </Sheet>
  );
}

/** A level's look: its tier, the same for a theme, a game or a code. */
function LookPicker({ value, onChange }: { value: Look; onChange: (look: Look) => void }) {
  const { tr } = useApp();
  return (
    <div className="field">
      <span className="field-label">{tr("passEditLook")}</span>
      <div className="pass-edit-looks">
        {LOOKS.map((l) => (
          <button
            key={l}
            type="button"
            className={`pass-edit-look pass-tier-${l}${l === value ? " is-on" : ""}`}
            aria-pressed={l === value}
            onClick={() => {
              tick();
              onChange(l);
            }}
          >
            <span className="pass-edit-look-dot shape-cookie9" />
            {capital(tr(TIER_NAME[l]))}
          </button>
        ))}
      </div>
    </div>
  );
}
