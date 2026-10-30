import { clubApi, type NewsItem } from "../../api";
import { gameArtOf, useArtTheme } from "../../app/artTheme";
import { useApp } from "../../app/context";
import { KindChip } from "../../parts/KindChip";
import { newsShareLink, openExternal, shareLink } from "../../app/env";
import { tick } from "../../core/haptic";
import { useLoad } from "../../app/useLoad";
import { GameLink } from "../../parts/GameLink";
import { whenLabel } from "../../i18n";
import { Button, Empty, IconButton } from "../../ui/Controls";
import { Page } from "../../ui/Page";
import { Cover } from "../../ui/Pic";
import { Hero } from "../../ui/Hero";
import { RichText } from "../../ui/RichText";
import { openImage } from "../../ui/Viewer";
import "./News.css";

/** A picture's address without its query, so a resized copy still counts as the same one. */
const bare = (url: string) => url.trim().split("?")[0].replace(/^https?:\/\//, "");

type Game = { platform: string; title_id: string; name: string | null; icon_url: string | null } | null;

export function NewsPostPage({
  appid,
  gid,
  item,
  game,
  onClose,
  layer,
}: {
  appid: number;
  gid: string;
  item: NewsItem | null;
  game: Game;
  onClose: () => void;
  layer: string;
}) {
  const { data, tr, locale, open, toast } = useApp();
  const fetched = useLoad(item ? null : `post:${appid}:${gid}`, () =>
    clubApi.fetchNewsPost(data, appid, gid, game ? { platform: game.platform, title_id: game.title_id } : undefined),
  );
  const post = item ?? fetched.data ?? null;
  const gameName = item?.game.name ?? fetched.data?.game?.name ?? game?.name ?? null;
  const gameIcon = item?.game.icon_url ?? fetched.data?.game?.icon_url ?? game?.icon_url ?? null;
  // A post with no picture of its own shows its game's wide art, edge to edge.
  const wide = post?.image ?? item?.game.hero ?? fetched.data?.game?.hero ?? null;
  const ref = item?.game ?? game;
  const gameId = item?.game.game_id ?? fetched.data?.game?.game_id ?? undefined;
  const theme = useArtTheme(gameArtOf(gameId ? `g${gameId}` : null, ref ? `${ref.platform}:${ref.title_id}` : null, gameName) ?? gameIcon);
  const text = post?.image
    ? post.text
        .split("\n")
        .filter((l) => bare(l) !== bare(post.image!))
        .join("\n")
    : (post?.text ?? "");

  const openGame =
    ref?.title_id && gameName
      ? () => open({ kind: "game", ref: { game_id: gameId ?? undefined, platform: ref.platform, title_id: ref.title_id, name: gameName, icon_url: gameIcon } })
      : undefined;

  return (
    <Page
      title={gameName ?? tr("newsPost")}
      onBack={onClose}
      hero
      layer={layer}
      style={theme.style}
      actions={
        post ? (
          <IconButton
            icon="share"
            label={tr("share")}
            variant="glass"
            onClick={() => {
              tick();
              const link = newsShareLink(appid, gid, ref?.platform && ref.title_id ? ref : null);
              void shareLink(link).then((how) => how === "copied" && toast(tr("linkCopied")));
            }}
          />
        ) : null
      }
    >
      {!post && fetched.loading && <div className="np-skel skel" />}
      {!post && fetched.error ? <Empty icon="refresh" title={tr("loadFailed")} action={<Button variant="tonal" onClick={fetched.reload}>{tr("retry")}</Button>} /> : null}
      {post && (
        <article className="np-article">
          <Hero full={Boolean(wide)} ground={wide ?? gameIcon} onOpen={wide ? () => openImage(wide) : undefined}>
            {wide ? <img src={wide} alt="" className="hero-pic" /> : <Cover src={gameIcon} className="hero-cover" />}
          </Hero>
          <div className="detail">
            <div className="detail-meta">
              <KindChip kind={post.kind} />
              <span>
                {whenLabel(post.date, locale)}
              </span>
            </div>
            <h1 className="detail-title">{post.title}</h1>
            {gameName && <GameLink name={gameName} cover={gameIcon} onOpen={openGame} />}
            <RichText text={text} className="np-text" />
            <Button variant="tonal" icon="external" wide onClick={() => openExternal(post.url)}>
              {tr("newsOnSteam")}
            </Button>
          </div>
        </article>
      )}
    </Page>
  );
}
