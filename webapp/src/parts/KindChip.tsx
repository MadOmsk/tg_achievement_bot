import { useApp } from "../app/context";

/** What a developer's post is — a patch or news — the same mark everywhere
 * a post is shown. */
export function KindChip({ kind }: { kind: "patch" | "news" | string | null | undefined }) {
  const { tr } = useApp();
  const patch = kind === "patch";
  return (
    <span className={`kind ${patch ? "kind-patch" : "kind-news"}`}>
      {patch ? tr("newsPatch") : tr("newsPost")}
    </span>
  );
}
