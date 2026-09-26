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

/**
 * The app while it first loads, drawn as the home page it becomes: the header
 * (avatar, greeting, nick), the search field, the big picture, the friends
 * strip and the list of games.
 */
export function AppSkel() {
  return (
    <div className="app-skel" aria-busy="true" aria-live="polite">
      <div className="app-skel-head">
        <span className="skel skel-avatar" />
        <span className="app-skel-who">
          <span className="skel line" style={{ width: 70 }} />
          <span className="skel line" style={{ width: 128, height: 17 }} />
        </span>
      </div>
      <span className="skel app-skel-search" />
      <span className="skel app-skel-hero" />
      <span className="skel line skel-title" />
      <div className="app-skel-friends">
        {[0, 1, 2, 3].map((i) => (
          <span key={i} className="app-skel-friend">
            <span className="skel skel-avatar is-big" />
            <span className="skel line" style={{ width: 64 }} />
          </span>
        ))}
      </div>
      <span className="skel line skel-title" style={{ marginTop: 28 }} />
      {[0, 1, 2].map((i) => (
        <div key={i} className="app-skel-game">
          <span className="skel skel-pic is-big" />
          <span className="skel-copy">
            <span className="skel line" style={{ width: `${60 - i * 8}%` }} />
            <span className="skel line" />
            <span className="skel line is-thin" style={{ width: 84 }} />
          </span>
        </div>
      ))}
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
              <span className="skel-copy">
                <span className="skel line" style={{ width: 96 }} />
                <span className="skel line is-thin" style={{ width: 64 }} />
              </span>
            </div>
            <span className="skel skel-post-pic" />
            <span className="skel-copy skel-post-text">
              <span className="skel line" style={{ width: "58%", height: 16 }} />
              <span className="skel line is-thin" style={{ width: "82%" }} />
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** The stats page: two tiles, a strip of covers, and the leaders. */
export function StatsSkel() {
  return (
    <div aria-busy="true" aria-live="polite">
      <HeadSkel />
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

/** Somebody's profile while it opens: the bar, the picture, their games. */
export function PersonSkel() {
  return (
    <div className="app-skel" aria-busy="true" aria-live="polite">
      <div className="app-skel-head">
        <span className="skel skel-avatar" />
        <span className="app-skel-who">
          <span className="skel line" style={{ width: 120, height: 17 }} />
          <span className="skel line is-thin" style={{ width: 84 }} />
        </span>
      </div>
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
  );
}
