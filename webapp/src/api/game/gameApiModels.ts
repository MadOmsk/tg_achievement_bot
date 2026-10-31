/** A game as a small card: a series, a relation, a search hit, a favorite. */
export type GameCard = {
  game_id: number;
  name: string;
  name_ru: string | null;
  year: number | null;
  poster: string | null;
  hero: string | null;
  /** How many people here played it (search only). */
  players?: number;
};

export type GamePlatform = {
  /** series / one / 360 / pc / ps5 / ps4 / ps3 / vita / steam */
  console: string;
  /** Whose PC it is: xbox / steam / egs / gog. */
  store: string;
  release_date: string | null;
  on_sale: number | null;
  url: string | null;
  list: { platform: string; title_id: string } | null;
  enhanced: boolean;
};

export type GamePlayer = {
  person_id: number;
  name: string;
  count: number;
  last: string | null;
  platform: string;
  title_id: string;
  total: number | null;
  /** Every list the person played, the most earned first (one game on Xbox
   * and Steam is two lists, never summed). */
  lists?: GameListPlayed[];
};

export type GameListPlayed = {
  count: number;
  last: string | null;
  platform: string;
  title_id: string;
  total: number | null;
  /** Which version the list is (Xbox One, Xbox PC): two lists of one platform tell apart. */
  console?: string | null;
  store?: string | null;
};

export type GameNews = {
  appid: number;
  gid: string;
  title: string;
  date: string;
  kind: "patch" | "news";
  image: string | null;
  text: string;
  url: string;
};

/** What HowLongToBeat's players took, its score and its age rating. */
export type GameHltb = {
  hltb_id: number;
  main: number | null;
  extra: number | null;
  completionist: number | null;
  score: number | null;
  rating: string | null;
  url: string;
  /** It is played together / against others (HLTB keeps times for it). */
  coop?: boolean;
  multi?: boolean;
};

export type GameDlc = {
  name: string;
  image: string | null;
  release_date: string | null;
  kind: string | null;
  hours: number | null;
  consoles: string[];
  /** What its store says of it, in English. */
  description?: string | null;
  /** Where it is sold: a console each, its own store page. */
  stores?: { console: string; store: string; url: string | null; on_sale: number | null }[];
  hltb?: GameHltb | null;
};

export type GameEdition = {
  name: string;
  kind: string | null;
  store: string;
  on_sale: number | null;
  cover: string | null;
  /** The store's wide art, mostly with no title on it. */
  hero?: string | null;
  /** Each store that sells it, its own page. */
  stores?: { store: string; url: string | null; on_sale: number | null }[];
  /** What it holds, the games first. */
  items?: { name: string; kind: string | null }[];
};

export type GamePage = {
  ok: boolean;
  /** The description is on its way: it shows blurred. */
  translating?: boolean;
  game: {
    game_id: number;
    name: string;
    name_ru: string | null;
    year: number | null;
    last_year: number | null;
    developer: string | null;
    publisher: string | null;
    more_developers: boolean;
    more_publishers: boolean;
    kind: string;
  };
  art: { poster: string | null; hero: string | null; header: string | null };
  description: { text: string; lang: string } | null;
  genres: string[];
  platforms: GamePlatform[];
  screenshots: string[];
  /** The stores' trailers: a file or an HLS stream, with a picture. */
  videos?: { name: string | null; mp4: string | null; hls: string | null; poster: string | null }[];
  hltb: GameHltb | null;
  lists: { platform: string; title_id: string; name: string; total: number | null; icon_url: string | null }[];
  /** Whether the progress below is the viewer's own. */
  viewed_is_me: boolean;
  progress: GamePlayer | null;
  players: GamePlayer[];
  favorite: boolean;
  favorites: number;
  news: GameNews[];
  dlcs: GameDlc[];
  editions: GameEdition[];
  series: { series_id: number; name: string; games: GameCard[] }[];
  related: { kind: string; forward: boolean; game: GameCard }[];
};
