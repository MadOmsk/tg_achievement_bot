import { useEffect, useState } from "react";
import { clubApi, type GameRef } from "../../../api";
import { useOpenGame } from "../../shared/lib";
import type { Locale } from "../../../i18n";
import { NewsPage, type NewsPost } from "./NewsPage";

/** A game's post known only by its Steam app and id — a notice about it, or a
 * push's link (owner, 2026-10-08): read, then opened on its own page. Nothing
 * shows while it loads; one that is gone closes at once. */
export function NewsPostLoader({
  data,
  locale,
  appid,
  gid,
  game,
  gameRef,
  onClose,
}: {
  data: string;
  locale: Locale;
  appid: number;
  gid: string;
  game?: { name: string; icon_url: string | null; onOpen?: () => void };
  /** Without `game`: the game the link names, read with the post and opened
   * from its head. */
  gameRef?: GameRef | null;
  onClose: () => void;
}) {
  const [post, setPost] = useState<NewsPost | null>(null);
  const [found, setFound] = useState<{ name: string; icon_url: string | null } | null>(null);
  const openGame = useOpenGame();

  useEffect(() => {
    let cancelled = false;
    clubApi
      .fetchNewsPost(data, appid, gid, game ? undefined : gameRef?.title_id)
      .then((answer) => {
        if (cancelled) return;
        setPost(answer);
        setFound(answer.game);
      })
      .catch(() => {
        if (!cancelled) onClose();
      });
    return () => {
      cancelled = true;
    };
    // The post is what was asked for once; closing is the parent's.
  }, [data, appid, gid]);

  const head =
    game ??
    (found
      ? {
          ...found,
          onOpen:
            gameRef && openGame
              ? () => {
                  onClose();
                  openGame({ ...gameRef, name: found.name });
                }
              : undefined,
        }
      : undefined);
  return post ? <NewsPage post={post} locale={locale} game={head} onClose={onClose} /> : null;
}
