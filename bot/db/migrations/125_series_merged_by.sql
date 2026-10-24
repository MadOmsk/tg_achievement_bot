-- Who merged a series into another (#147; owner, 2026-10-24): `operator`
-- (the viewer's merge) stands over every rebuild; `auto` (the builder joining
-- two series one proposal spans) is undone when the proposals no longer
-- join them — an old chain put LEGO Batman, Marvel and Harry Potter games in
-- Star Wars and every rebuild sent them back through the merged series'
-- anchors. The merges made before this column existed were the builder's.
ALTER TABLE series ADD COLUMN merged_by TEXT;
UPDATE series SET merged_by = 'auto' WHERE merged_into IS NOT NULL;
