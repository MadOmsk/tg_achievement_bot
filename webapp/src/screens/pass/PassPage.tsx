import { useState, type CSSProperties } from "react";
import { useApp } from "../../app/context";
import { TIER_NAME } from "../../app/views";
import { tick } from "../../core/haptic";
import { claimTheme, PALETTE_NAMES, passProgress, usePass, type Tier } from "../../core/pass";
import { num, plural } from "../../i18n";
import { Button } from "../../ui/Controls";
import { Icon } from "../../ui/Icon";
import { Page } from "../../ui/Page";
import "../settings/Settings.css";
import "./Pass.css";

export function RewardArt({ t, size = 56 }: { t: Tier; size?: number }) {
  return (
    <span className={`pass-art swatch-${t.palette}`} style={{ width: size, height: size }}>
      <span className="swatch-dot shape-cookie9" style={{ width: size, height: size }} />
    </span>
  );
}

export function rewardName(t: Tier, tr: ReturnType<typeof useApp>["tr"]): string {
  return `${tr("passTheme")} «${tr(PALETTE_NAMES[t.palette])}»`;
}

const SPARKS = 14;

/** How far along the line the month's points reach, in levels from the first stop. */
function reachX(points: number, tiers: Tier[]): number {
  const level = tiers.filter((t) => points >= t.points).length;
  if (level === 0) return 0;
  const next = tiers[level];
  if (!next) return tiers.length - 1;
  const from = tiers[level - 1].points;
  return level - 1 + (points - from) / (next.points - from);
}

export function PassPage({ onClose, layer }: { onClose: () => void; layer: string }) {
  const { data, tr, locale, toast } = useApp();
  const state = usePass(data);
  const p = passProgress(state);
  const { tiers, points } = p;
  // The showcase: what the person picked on the track, else what is waiting
  // to be claimed, else what opens next.
  const [picked, setPicked] = useState<number | null>(null);
  const spot = tiers.find((t) => t.level === picked) ?? p.waiting[0] ?? p.next ?? tiers[tiers.length - 1];
  const [burst, setBurst] = useState(0);
  const [busy, setBusy] = useState(false);
  const pts = (n: number) => `${num(n, locale)} ${plural(locale, n, ["ptsOne", "ptsFew", "ptsMany"])}`;

  const celebrate = (level: number, message: string) => {
    tick();
    setPicked(level);
    setBurst((n) => n + 1);
    window.setTimeout(() => toast(message), 650);
  };

  const claim = async (t: Tier) => {
    setBusy(true);
    try {
      await claimTheme(data, t.palette);
      celebrate(t.level, tr("passClaimed").replace("{name}", tr(PALETTE_NAMES[t.palette])));
    } catch {
      toast(tr("somethingWrong"), "error");
    } finally {
      setBusy(false);
    }
  };

  // Every reward waiting, one claim after another; the burst plays on the last.
  const claimAll = async () => {
    const all = p.waiting;
    if (!all.length) return;
    setBusy(true);
    try {
      for (const t of all) await claimTheme(data, t.palette);
      celebrate(all[all.length - 1].level, tr("passClaimedAll").replace("{n}", String(all.length)));
    } catch {
      toast(tr("somethingWrong"), "error");
    } finally {
      setBusy(false);
    }
  };

  if (!state || !spot) {
    return (
      <Page title={tr("passTitle")} onBack={onClose} layer={layer}>
        <div className="pass-spot pass-spot-wait skel" />
      </Page>
    );
  }

  const have = spot.claimed;
  const ready = !have && points >= spot.points;
  const n = tiers.length;

  return (
    <Page
      title={tr("passTitle")}
      onBack={onClose}
      layer={layer}
      className="pass-page"
      actions={
        p.waiting.length > 0 ? (
          <button type="button" className="link-btn" disabled={busy} onClick={() => void claimAll()}>
            {tr("passClaimAll")}
          </button>
        ) : null
      }
    >
      <section key={`${spot.level}:${burst}`} className={`pass-spot pass-tier-${spot.tier}${burst && have ? " pass-spot-burst" : ""}`}>
        <span className="pass-spot-glow" aria-hidden="true" />
        <span className="pass-spot-rays" aria-hidden="true" />
        <span className="pass-spot-art">
          <RewardArt t={spot} size={132} />
          {!have && !ready && (
            <span className="pass-spot-lock">
              <Icon name="lock" size={18} />
            </span>
          )}
          {burst > 0 && have && (
            <span className="pass-sparks" aria-hidden="true">
              {Array.from({ length: SPARKS }, (_, i) => (
                <i key={i} style={{ "--a": `${(360 / SPARKS) * i}deg`, "--d": `${70 + (i % 3) * 22}px` } as CSSProperties} />
              ))}
            </span>
          )}
        </span>
        <span className="pass-tier-word">{tr(TIER_NAME[spot.tier])}</span>
        <h2 className="pass-spot-name">{tr(PALETTE_NAMES[spot.palette])}</h2>
        {have ? (
          <span className="pass-have">
            <Icon name="check" size={16} />
            {tr("passHave")}
          </span>
        ) : ready ? (
          <Button variant="filled" className="pass-claim" icon="gift" busy={busy} onClick={() => claim(spot)}>
            {tr("passClaim")}
          </Button>
        ) : (
          <span className="pass-spot-left">
            <Icon name="lock" size={14} />
            {tr("passNextShort")} {pts(Math.max(0, spot.points - points))}
          </span>
        )}
      </section>

      <div className="pass-stats">
        <span>
          <b className="t-num">{num(points, locale)}</b> {plural(locale, points, ["ptsOne", "ptsFew", "ptsMany"])}
        </span>
        <span className="pass-days">
          <Icon name="clock" size={14} />
          {tr("passDaysShort").replace("{n}", String(state.days_left))}
        </span>
      </div>

      <div className="pass-track">
        <div className="pass-line" style={{ left: `${50 / n}%`, width: `${((n - 1) / n) * 100}%` }}>
          <span className="pass-line-fill" style={{ width: `${(reachX(points, tiers) / Math.max(1, n - 1)) * 100}%` }} />
        </div>
        <ol className="pass-stops">
          {tiers.map((t) => {
            const open = points >= t.points;
            return (
              <li key={t.level}>
                <button
                  type="button"
                  aria-label={tr(PALETTE_NAMES[t.palette])}
                  className={`pass-stop pass-tier-${t.tier}${t.claimed ? " pass-stop-have" : open ? " pass-stop-due" : ""}${spot.level === t.level ? " pass-stop-on" : ""}`}
                  onClick={() => {
                    tick();
                    setPicked(t.level);
                  }}
                >
                  <span className="pass-stop-art">
                    <RewardArt t={t} size={48} />
                    <span className={`pass-stop-mark${t.claimed ? " pass-stop-mark-have" : open ? " pass-stop-mark-due" : ""}`}>
                      <Icon name={t.claimed ? "check" : open ? "gift" : "lock"} size={11} />
                    </span>
                  </span>
                  <span className="pass-stop-pts t-num">{num(t.points, locale)}</span>
                </button>
              </li>
            );
          })}
        </ol>
      </div>

      <p className="pass-how">{tr("passHow")}</p>
    </Page>
  );
}
