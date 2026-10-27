import { useApp } from "../app/context";
import { Icon } from "../ui/Icon";

/** What a developer's post is — a patch or news — the same mark everywhere
 * a post is shown. */
export function KindChip({ kind }: { kind: "patch" | "news" | string | null | undefined }) {
  const { tr } = useApp();
  const patch = kind === "patch";
  return (
    <span className={`kind ${patch ? "kind-patch" : "kind-news"}`}>
      <Icon name={patch ? "patch" : "news"} size={14} />
      {patch ? tr("newsPatch") : tr("newsPost")}
    </span>
  );
}
