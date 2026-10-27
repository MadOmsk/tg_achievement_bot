import { clubApi, type NewsItem } from "../../api";
import { useApp } from "../../app/context";
import { openExternal } from "../../app/env";
import { useLoad } from "../../app/useLoad";
import { GameLink } from "../../parts/GameLink";
import { clockOf } from "../../core/post-text";
import { dayLabel } from "../../i18n";
import { Button, Empty } from "../../ui/Controls";
import { Page } from "../../ui/Page";
import { Cover } from "../../ui/Pic";
import { Hero } from "../../ui/Hero";
import { RichText } from "../../ui/RichText";
import { openImage } from "../../ui/Viewer";
import { KindChip } from "../../parts/KindChip";
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
  const { data, tr, locale, open } = useApp();
  const fetched = useLoad(item ? null : `post:${appid}:${gid}`, () =>
    clubApi.fetchNewsPost(data, appid, gid, game ? { platform: game.platform, title_id: game.title_id } : undefined),
  );
  const post = item ?? fetched.data ?? null;
  const gameName = item?.game.name ?? fetched.data?.game?.name ?? game?.name ?? null;
  const gameIcon = item?.game.icon_url ?? fetched.data?.game?.icon_url ?? game?.icon_url ?? null;
  const ref = item?.game ?? game;
  const text = post?.image
    ? post.text
        .split("\n")
        .filter((l) => bare(l) !== bare(post.image!))
        .join("\n")
    : (post?.text ?? "");

  const openGame =
    ref?.title_id && gameName
      ? () => open({ kind: "game", ref: { platform: ref.platform, title_id: ref.title_id, name: gameName, icon_url: gameIcon } })
      : undefined;

  return (
    <Page title={gameName ?? tr("newsPost")} onBack={onClose} hero layer={layer}>
      {!post && fetched.loading && <div className="np-skel skel" />}
      {!post && fetched.error ? <Empty icon="refresh" title={tr("loadFailed")} action={<Button variant="tonal" onClick={fetched.reload}>{tr("retry")}</Button>} /> : null}
      {post && (
        <article>
          <Hero full={Boolean(post.image)} ground={post.image ?? gameIcon} onOpen={post.image ? () => openImage(post.image!) : undefined}>
            {post.image ? <img src={post.image} alt="" className="hero-pic" /> : <Cover src={gameIcon} className="hero-cover" />}
          </Hero>
          <div className="detail">
            <div className="detail-meta">
              <KindChip kind={post.kind} />
              <span>
                {dayLabel(post.date, locale)}
                {clockOf(post.date, locale) && `, ${clockOf(post.date, locale)}`}
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
