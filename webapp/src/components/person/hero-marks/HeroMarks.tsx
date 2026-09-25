export function HeroMarks({
  score,
  rarity,
  compact = false,
}: {
  score: string | null;
  rarity: string | null;
  compact?: boolean;
}) {
  const text = [rarity, score].filter(Boolean).join(" · ");
  if (!text) return null;
  if (compact) {
    return <span className="feed-plat">{text}</span>;
  }
  return (
    <span className="hero-corner">
      <span className="hero-mark">{text}</span>
    </span>
  );
}
