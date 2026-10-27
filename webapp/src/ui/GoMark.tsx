import { Icon, type IconName } from "./Icon";

/** Where a tap goes — on, or play — as one round mark everywhere: a row, a
 * link card, a card that is itself the way in. */
export function GoMark({ icon = "forward" }: { icon?: IconName }) {
  return (
    <span className="go-mark shape-cookie9" aria-hidden="true">
      <Icon name={icon} size={18} />
    </span>
  );
}
