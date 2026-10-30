import { useEffect, useState } from "react";
import { gamesApi } from "../../api";
import { gameArtOf, useArtTheme } from "../../app/artTheme";
import { useApp } from "../../app/context";
import { openExternal } from "../../app/env";
import type { AchView } from "../../app/layers";
import { useLoad } from "../../app/useLoad";
import { isVeiled, pointsOf, rareLevel, revealed, TIER_NAME } from "../../app/views";
import { tick } from "../../core/haptic";
import { pct, whenLabel } from "../../i18n";
import { isWideArt } from "../../parts/AchRow";
import { GameLink } from "../../parts/GameLink";
import { capital } from "../../parts/Months";
import { Button } from "../../ui/Controls";
import { Face } from "../../ui/Face";
import { Icon } from "../../ui/Icon";
import { Page } from "../../ui/Page";
import { AchPic } from "../../ui/Pic";
import { Hero } from "../../ui/Hero";
import { RichText } from "../../ui/RichText";
import { openImage } from "../../ui/Viewer";
import { GuideVideo } from "../../parts/GuideVideo";
import { LinkCard } from "../../ui/LinkCard";
import "./Game.css";
import { Spark } from "../../parts/AchRow";


function at(url: string, start: number): string {
  if (!start) return url;
  return `${url}${url.includes("?") ? "&" : "?"}t=${start}s`;
}

export function AchievementPage({ ach, onClose, layer }: { ach: AchView; onClose: () => void; layer: string }) {
  const { data, tr, locale, me, open } = useApp();
  const [, setRound] = useState(0);
  const [ask, setAsk] = useState(0);
  const guides = useLoad(`guides:${ach.platform}:${ach.titleId}:${ask}`, () =>
    gamesApi.fetchGameGuides(data, ach.platform, ach.titleId),
  );
  // Steam's guides are read in the background: ask again until they are in.
  useEffect(() => {
    if (!guides.data || guides.data.complete || ask >= 5) return;
    const id = window.setTimeout(() => setAsk((n) => n + 1), 8000);
    return () => window.clearTimeout(id);
  }, [guides.data, ask]);
  const earners: Array<{ id: number | null; name: string; at: string | null }> =
    ach.together && ach.together.length > 0
      ? ach.together
      : ach.unlockedAt
        ? [{ id: ach.person?.id ?? null, name: ach.person?.name ?? "", at: ach.unlockedAt }]
        : [];
  const veiled = isVeiled(ach.secret, ach.key, me.settings.show_secrets);
  const tip = guides.data?.tips[ach.achievementId]?.text;
  const videos = guides.data?.videos?.[ach.achievementId] ?? [];
  const rare = rareLevel(ach.rarity, ach);
  const theme = useArtTheme(gameArtOf(ach.gameId ? `g${ach.gameId}` : null, `${ach.platform}:${ach.titleId}`, ach.game) ?? ach.gameIcon);

  return (
    <Page title={ach.game ?? tr("pageAchievement")} onBack={onClose} hero layer={layer} className="ach-page" style={theme.style}>
      <div className="ap-head">
        <Hero full={isWideArt(ach.platform)} ground={veiled ? null : ach.icon} onOpen={!veiled && ach.icon ? () => openImage(ach.icon!) : undefined}>
          <AchPic src={ach.icon} veiled={veiled} className={isWideArt(ach.platform) ? "hero-ach" : "hero-ach hero-ach-sq"} />
        </Hero>
        <span className={`ap-badge shape-flower6 ap-badge-${rare ?? "plain"}`}>
          <b className="t-num flower-pts">
            <Spark className="flower-spark" />
            {pointsOf(ach.rarity, ach)}
          </b>
        </span>
      </div>

      <div className="detail">
        <div className="detail-meta">
          {/* The tier as a word in its colour, as a post's kicker is. */}
          <span className={`detail-kicker${rare ? ` mark-${rare}` : ""}`}>
            {capital(tr(TIER_NAME[rare ?? "common"]))}
            {ach.rarity != null && ` · ${pct(ach.rarity, locale)}`}
          </span>
          {!ach.unlockedAt && <span>{tr("achNotEarned")}</span>}
        </div>

        <h1 className="detail-title">{veiled ? tr("secretAchievement") : ach.name}</h1>
        {veiled ? (
          <Button
            variant="tonal"
            icon="lock"
            onClick={() => {
              revealed.add(ach.key);
              setRound((n) => n + 1);
            }}
          >
            {tr("reveal")}
          </Button>
        ) : (
          ach.description && <p className="ap-desc">{ach.description}</p>
        )}

        <GameLink
            name={ach.game ?? ""}
            cover={ach.gameIcon}
            onOpen={() => {
              tick();
              open({
                kind: "game",
                ref: {
                  game_id: ach.gameId ?? undefined,
                  platform: ach.platform,
                  title_id: ach.titleId,
                  name: ach.game,
                  icon_url: ach.gameIcon,
                  person: ach.person ? { person_id: ach.person.id, name: ach.person.name } : null,
                },
              });
            }}
          />
        {earners.length > 0 && (
          <div className="link-cards">
            {earners.map((p) => (
              <LinkCard
                key={p.id ?? "me"}
                media={p.id ? <Face personId={p.id} name={p.name} size={48} /> : <span className="link-card-icon"><Icon name="check" size={22} /></span>}
                title={p.id === me.person_id || !p.id ? tr("you") : p.name}
                sub={
                  p.at
                    ? `${tr("achEarned")} · ${whenLabel(p.at, locale)}`
                    : tr("achEarned")
                }
                onOpen={p.id ? () => open({ kind: "person", personId: p.id! }) : undefined}
              />
            ))}
          </div>
        )}

        {(videos.length > 0 || tip || guides.data?.guide) && <h2 className="ap-h2 t-title">{tr("achHowTo")}</h2>}
        {videos.length > 0 && (
          <div className="link-cards">
            {videos.map((v) => (
              <LinkCard
                key={`${v.id}:${v.start}`}
                wide
                media={<img src={`https://i.ytimg.com/vi/${v.id}/mqdefault.jpg`} alt="" loading="lazy" className="link-card-thumb" />}
                title={v.title}
                sub={`${v.channel}${v.part ? ` · ${tr("achVideoPart")} ${v.part}` : ""}`}
                go="play"
                onOpen={() => openExternal(at(v.url, v.start))}
              />
            ))}
          </div>
        )}
        {!videos.length && guides.data?.guide && (
          <GuideVideo guide={guides.data.guide} />
        )}
        {tip && (
          <div className="ap-tip">
            <RichText text={tip} />
            <p className="t-meta">{tr("achTipSource")}</p>
          </div>
        )}
      </div>
    </Page>
  );
}
