import { Icon } from "../ui/Icon";

/** The mark of a list earned whole: a flower with a check. */
export function DoneMark({ size = 56, className = "" }: { size?: number; className?: string }) {
  return (
    <span className={`done-mark shape-flower6 ${className}`} style={{ width: size, height: size }} aria-hidden="true">
      <Icon name="check" size={Math.round(size * 0.46)} />
    </span>
  );
}
