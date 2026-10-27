/** A version's platform as a person reads it: the console, or a PC by its store. */
export function consoleLabel(console: string, store: string): string {
  switch (console) {
    case "series":
      return "Series X|S";
    case "one":
      return "Xbox One";
    case "360":
      return "Xbox 360";
    case "pc":
      return store === "xbox" ? "Xbox PC" : store === "egs" ? "Epic" : store === "gog" ? "GOG" : "PC";
    case "steam":
      return "Steam";
    case "ps5":
      return "PS5";
    case "ps4":
      return "PS4";
    case "ps3":
      return "PS3";
    case "vita":
      return "PS Vita";
    default:
      return console.toUpperCase();
  }
}
