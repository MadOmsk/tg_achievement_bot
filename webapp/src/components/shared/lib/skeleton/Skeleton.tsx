import "./Skeleton.css";

/**
 * A list of rows drawn as the app's own achievement rows: the same glass card,
 * the same 56px picture and two lines of text, so what loads in replaces it
 * without anything moving.
 */
export function RowsSkel({ count = 5 }: { count?: number }) {
  return (
    <div className="skel-rows" aria-busy="true" aria-live="polite">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="feed-row skel-feed-row">
          <span className="skel skel-pic" />
          <span className="skel-copy">
            <span className="skel line" style={{ width: `${62 - (i % 3) * 9}%` }} />
            <span className="skel line is-thin" style={{ width: `${84 - (i % 2) * 22}%` }} />
          </span>
        </div>
      ))}
    </div>
  );
}

/** A page that is still loading: a heading and the rows that will fill it. */
export function PageSkel() {
  return (
    <div aria-busy="true" aria-live="polite">
      <span className="skel line skel-title" />
      <RowsSkel count={5} />
    </div>
  );
}

export function HomeSkel() {
  return (
    <div className="profile-hero home-skel" aria-busy="true">
      <span className="skel home-skel-fill" />
    </div>
  );
}

/** The app opened straight on a game: its page, not the home page. */
export function GameSkel() {
  return (
    <div className="app-skel" aria-busy="true" aria-live="polite">
      <div className="app-skel-head">
        <span className="skel line" style={{ width: "58%", height: 20 }} />
      </div>
      <span className="skel app-skel-hero" />
      <div className="game-skel-tabs">
        <span className="skel line" style={{ width: 118, height: 15 }} />
        <span className="skel line" style={{ width: 84, height: 15 }} />
      </div>
      <RowsSkel count={6} />
    </div>
  );
}

/**
 * The home page under its header while its first data loads, drawn with the
 * page's own blocks — the gallery, the friends, the games — so the real ones
 * land where their placeholders stood and nothing moves.
 */
export function HomeBodySkel() {
  return (
    <div aria-busy="true" aria-live="polite">
      <HomeSkel />
      <div className="section-head">
        <span className="skel line" style={{ width: 92, height: 18 }} />
      </div>
      <div className="friends">
        {[0, 1, 2, 3].map((i) => (
          <span key={i} className="friend">
            <span className="skel skel-avatar is-friend" />
            <span className="skel line" style={{ width: 58, marginTop: 8 }} />
            <span className="skel line is-thin" style={{ width: 44, marginTop: 6 }} />
          </span>
        ))}
      </div>
      <div className="section-head achievements-head">
        <span className="skel line" style={{ width: 70, height: 18 }} />
      </div>
      <div className="played-games">
        {[0, 1, 2].map((i) => (
          <div key={i} className="played-game skel-played-game">
            <span className="skel skel-game-cover" />
            <span className="played-game-body skel-copy">
              <span className="skel line" style={{ width: `${62 - i * 9}%` }} />
              <span className="skel line" style={{ height: 6 }} />
              <span className="skel line is-thin" style={{ width: 70 }} />
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * The app while it first loads: the home page's own header, in its own
 * classes, over the same body the page shows until its data arrives — one
 * skeleton from the first frame to the content.
 */
export function AppSkel() {
  return (
    <div className="is-home" aria-busy="true" aria-live="polite">
      <div className="home-chrome">
        <div className="home-top">
          <div className="home-top-main">
            <span className="skel skel-avatar" />
            <span className="home-hello-row app-skel-who">
              <span className="skel line" style={{ width: 70 }} />
              <span className="skel line" style={{ width: 128, height: 17 }} />
            </span>
            <span className="skel month-chip-skel" />
          </div>
          <span className="skel app-skel-search" />
        </div>
      </div>
      <HomeBodySkel />
    </div>
  );
}

/** A page's own heading: the title on the left, the month chip on the right. */
function HeadSkel() {
  return (
    <div className="page-skel-head">
      <span className="skel line skel-title" />
      <span className="skel page-skel-chip" />
    </div>
  );
}

/** The feed: a heading and posts — a head, a picture, two lines. */
export function FeedSkel({
  posts = 2,
  head = true,
}: {
  posts?: number;
  /** False when the page's own heading is already on screen. */
  head?: boolean;
}) {
  return (
    <div aria-busy="true" aria-live="polite">
      {head && <HeadSkel />}
      <div className="feed-skel">
        {Array.from({ length: posts }, (_, i) => (
          <div key={i} className="skel-post">
            <div className="skel-post-head">
              <span className="skel skel-avatar" />
              <span className="skel line" style={{ width: 110 }} />
            </div>
            <span className="skel skel-post-pic" />
            <span className="skel line skel-post-text" style={{ width: "56%" }} />
          </div>
        ))}
      </div>
    </div>
  );
}

/** The stats page: two tiles, a strip of covers, and the leaders. */
export function StatsSkel({ head = true }: { head?: boolean }) {
  return (
    <div aria-busy="true" aria-live="polite">
      {head && <HeadSkel />}
      <div className="stats-skel-tiles">
        <span className="skel stats-skel-tile" />
        <span className="skel stats-skel-tile" />
      </div>
      <span className="skel line skel-title is-small" />
      <div className="stats-skel-strip">
        {[0, 1, 2].map((i) => (
          <span key={i} className="stats-skel-cover">
            <span className="skel stats-skel-art" />
            <span className="skel line" style={{ width: "80%" }} />
            <span className="skel line is-thin" style={{ width: 22 }} />
          </span>
        ))}
      </div>
      <span className="skel line skel-title is-small" style={{ marginTop: 28 }} />
      {[0, 1, 2].map((i) => (
        <div key={i} className="stats-skel-row">
          <span className="skel skel-avatar is-row" />
          <span className="skel line" style={{ width: `${44 - i * 8}%` }} />
          <span className="skel line stats-skel-count" />
        </div>
      ))}
    </div>
  );
}

/**
 * Somebody's profile while it opens: the picture and their games, under the
 * real header bar's own classes (not a stand-in copy) — so its size and
 * position are the real ones, and nothing jumps once it is the real bar.
 */
export function PersonSkel() {
  return (
    <div aria-busy="true" aria-live="polite">
      <div className="account-bar person-bar">
        <div className="account-top">
          <span className="skel skel-avatar" style={{ width: 36, height: 36, flex: "0 0 auto" }} />
          <span style={{ display: "flex", alignItems: "center", gap: 12, flex: "1 1 auto", minWidth: 0 }}>
            <span className="skel skel-avatar" />
            <span className="app-skel-who">
              <span className="skel line" style={{ width: 120, height: 17 }} />
              <span className="skel line is-thin" style={{ width: 84 }} />
            </span>
          </span>
        </div>
      </div>
      <div className="app-skel is-nested">
        <span className="skel app-skel-hero" />
        <span className="skel line skel-title is-small" />
        {[0, 1, 2].map((i) => (
          <div key={i} className="app-skel-game">
            <span className="skel skel-pic is-big" />
            <span className="skel-copy">
              <span className="skel line" style={{ width: `${62 - i * 9}%` }} />
              <span className="skel line" />
              <span className="skel line is-thin" style={{ width: 84 }} />
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
