---
name: mini-app-design
description: The Mini App's design system (design E, "Expressive"). Use before ANY change to how the Mini App looks — a screen, a component, a card, colours, spacing, an icon, a shape, a sheet, text styles — anything under webapp/src (screens/, parts/, ui/, styles/, *.css, *.tsx that renders). Also use when asked to make a screen "prettier", "nicer", "in our style", or to fix how something looks.
---

# The Mini App's design system

The look of the Mini App has one source: **`docs/design-system.md`**, the
tokens in `webapp/src/styles/tokens.css` and the components in
`webapp/src/ui/`. Nothing is styled outside them.

## Before writing anything

1. **Read `docs/design-system.md` in full** — every time, not from memory. It
   says which surface a block sits on, which colour role a thing takes, the
   type classes, spacing and radii, connected groups, what each shape means,
   the rarity tiers and the components.
2. Look at the screen as it is now (see "Look at it" below) and at a screen
   that already does something similar; copy its classes, do not invent.

## The rules that are broken most

- **Colours are tokens only** (`var(--surface-1)`, `var(--primary)`,
  `var(--tier-legendary)`…). No hex in a screen's CSS; no new colour. Every
  palette (seven, dark and light) must still work — a hard-coded colour breaks
  the others.
- **Surfaces**: page `--surface`; a card `--surface-1`; a field or quiet
  button 2–3; what is selected or a hero `--primary-container`; a state
  `--secondary-container`. Do not tint cards with gradients "to look nicer" —
  the owner rejected it (2026-10-28): cards stay `--surface-1`.
- **Shapes carry meaning** (`shape-<name>`): `cookie12` a person, `cookie9` an
  icon button or a mark, `flower6` rarity/place/done, `sunny8` something to
  take now, `gem` an organiser's prize, `burst12` where one is now, `puffy`
  nothing here, `clover4` decoration behind hero cards only. Never use a shape
  for its looks.
- **Type**: the `.t-*` classes; numbers narrow (`.t-num`), headlines wide.
  One hero number per screen.
- **Connected groups**: items 3 apart, inner corners 6–8, outer `--r-l`
  (`Group` + `Row`, the profile's counts). No hairlines between items.
- **Components, not look-alikes**: `Button`, `IconButton`, `Row`/`Group`,
  `Sheet`, `Confirm`, `Field`, `Segmented`, `Toggle`, `Empty`, `Face`, `Wave`
  from `src/ui/`. A choice among options opens a `Sheet` of `Row`s, the way
  «Тип» does in the pass editor.
- **Progress is a `Wave`**; full is all wave, in `--tertiary`.
- **Spacing**: the 4-point scale, side margin `--gutter` (16); a `Group` sits
  12 from the edge, so text meant to line up with it sits 16.
- **Text** comes from `webapp/src/i18n/locales/ru.ts` and `en.ts`, both, same
  keys. No example values in hints the owner did not ask for.
- **No comments on simple CSS.** Comment *why*, only where it is not obvious.

## Look at it

A layout is judged on the screen, not in the code. The dev server
(`manage.ps1 start -Test -Web`, Vite on :5173) can be screenshotted as a real,
signed-in person:

```bash
# once: a browser session for a person of the dev database (token kept in data/, gitignored)
.venv/Scripts/python .claude/skills/mini-app-design/make_session.py RideTheSun
# a phone-sized screenshot; path, output, scroll (1 = top), 1 for the full page
node .claude/skills/mini-app-design/shot.mjs "/?t=pass" shot.png 1
```

Read the PNG, fix what looks wrong, shoot again. Write screenshots to the
scratchpad, never into the repo. Then show the owner.

The owner uses the same dev server at the same time. Data made only to look
at a screen goes in a month or place nobody uses, and is removed **by the ids
it was given** — never "every draft of the month", never a whole row of a
table that may hold the owner's own work (2026-10-28: a clean-up by month
took the owner's published November cover and name with it).

## When the design system says nothing

Ask the owner instead of inventing a new pattern; when it is decided, add it
to `docs/design-system.md` in the same change.
