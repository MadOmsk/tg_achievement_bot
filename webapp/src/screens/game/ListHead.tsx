import { gameArtOf } from "../../app/artTheme";
import { Hero } from "../../ui/Hero";
import { Cover } from "../../ui/Pic";

/** The head of a page about a part of a game (its gallery, its add-ons): the
 * game's wide art edge to edge with nothing written on it, the words below —
 * or, with no wide art, the cover on its blurred ground with the words. */
export function ListHead({ game, cover, label }: { game: string; cover: string | null; label: string }) {
  const art = gameArtOf(game);
  if (art) {
    return (
      <div className="np-article">
        <Hero full ground={art}>
          <img src={art} alt="" className="hero-pic" />
        </Hero>
        <div className="detail list-head-text">
          <span className="chip chip-secondary">{label}</span>
          <h1 className="detail-title">{game}</h1>
        </div>
      </div>
    );
  }
  return (
    <Hero ground={cover}>
      <Cover src={cover} className="gallery-cover" />
      <p className="list-name t-title clamp-2">{game}</p>
      <p className="gallery-sub">{label}</p>
    </Hero>
  );
}
