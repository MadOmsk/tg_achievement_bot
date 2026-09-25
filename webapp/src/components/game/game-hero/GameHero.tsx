import { CoverImg, FitImg } from "../../shared/lib";

/**
 * The game's picture across the top of its page: full width, square edges,
 * nothing written on it. The picture is shown whole over a blurred, stretched
 * copy of itself.
 */
export function GameHero({ cover }: { cover: string | null }) {
  return (
    <div className="game-cover">
      <CoverImg src={cover} kind="game" className="game-cover-back" />
      <FitImg src={cover} kind="game" />
    </div>
  );
}
