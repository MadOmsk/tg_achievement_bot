import { useApp } from "../app/context";
import { LinkCard } from "../ui/LinkCard";
import { Cover } from "../ui/Pic";

/** The game a post or an achievement belongs to, a tap away. */
export function GameLink({ name, cover, onOpen }: { name: string; cover: string | null | undefined; onOpen?: () => void }) {
  const { tr } = useApp();
  return <LinkCard media={<Cover src={cover} className="link-card-cover" />} title={name} sub={tr("openGame")} onOpen={onOpen} />;
}
