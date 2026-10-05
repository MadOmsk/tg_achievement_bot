export type HltbHit = {
  hltb_id: number;
  name: string;
  release_year: number | null;
  main_hours: number | null;
  extra_hours: number | null;
  completionist_hours: number | null;
  platforms: string[];
  game_url: string | null;
  image_url: string | null;
  genre: string | null;
  description: string | null;
};
