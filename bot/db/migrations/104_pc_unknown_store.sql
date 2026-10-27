-- A PC version is told apart by its store (#147; owner, 2026-10-12):
-- Microsoft's, Steam's, later the Epic Games Store's or GOG's. An Xbox
-- achievement list played on `Win32` alone, with no Microsoft Store product
-- (a stand-in), is the Xbox app seeing a PC game launched from another
-- store — Heavy Rain on Steam was never on Xbox. Its stand-in was filed
-- under the Xbox store; it is a PC version of an unknown store.
UPDATE versions SET store = 'unknown'
WHERE stand_in = 1 AND store = 'xbox' AND console = 'pc' AND platform = 'xbox_modern'
  AND EXISTS (
    SELECT 1 FROM titles t
    WHERE t.platform = versions.platform AND t.title_id = versions.title_id
      AND json_valid(t.platforms) AND json_array_length(t.platforms) = 1
      AND json_extract(t.platforms, '$[0]') = 'Win32'
  )
  AND NOT EXISTS (
    SELECT 1 FROM versions o
    WHERE o.store = 'unknown' AND o.product_id = versions.product_id AND o.console = 'pc'
  );
