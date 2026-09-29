import { Icon } from "../icon/Icon";

export function BackHead({
  title,
  onBack,
  backLabel,
}: {
  title: string;
  onBack: () => void;
  backLabel: string;
}) {
  return (
    <header className="page-head">
      <button type="button" className="icon-btn" onClick={onBack} aria-label={backLabel}>
        <Icon name="back" size={26} />
      </button>
      <h1>{title}</h1>
    </header>
  );
}
