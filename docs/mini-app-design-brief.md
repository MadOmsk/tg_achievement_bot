# Unlocked Mini App — design brief

The task for whoever designs the Mini App's new interface (owner, 2026-10-26).
What the app does is `docs/mini-app-spec.md`; this file is how to go about
making it look and feel new.

## The goal

**A beautiful app for 2026**, designed from nothing. The old interface is
deliberately forgotten: do not look at it for layout or style
(`git show f49fa3b:webapp/src/…` only to check how some behaviour worked).
Organic UI is one direction worth considering, not a requirement. What counts is
that the result looks current and confident next to the best apps of 2026,
and that it is ours — not a template.

Anything may change: the tabs, what Home is, whether there is a list of games
on it at all, how a post looks, the type, colour, shapes, motion. Follow
design's own rules (hierarchy, rhythm, contrast, restraint) rather than
habits of this codebase.

## Fixed

- The name **Unlocked** and its logo and wordmark (`webapp/public/logo.svg`,
  the icons, `public/fonts/nunito-800-wordmark.woff2`).
- **A glass bottom bar**: floating over the content, the content showing
  through it blurred.
- Everything `docs/mini-app-spec.md` says the app does, and its privacy and
  naming rules.
- All copy through `webapp/src/i18n/locales/ru.ts` / `en.ts` (Russian first),
  both complete; keys may be added and reworded.

## Who and where

- 20–30 friends who hunt achievements on Xbox, PlayStation and Steam, mostly
  Russian-speaking. It is a club: what friends earned, what they play, which
  games they love.
- **Phone first**, a narrow screen, one thumb; inside Telegram (its header and
  back button), in a mobile browser, and installed as an app. Telegram's
  safe areas and `--safe-top` / `--safe-bottom` matter.
- Mostly in the evening, in a dark room: a dark theme first. A light theme is
  welcome if it is as good, not required.
- Content is pictures: achievement icons (often small, 64 px), game box art,
  wide hero art, screenshots, faces. The design must make small icons look
  good, not stretched (the spec's small-picture rule).

## How to work

1. **Research first.** What makes an app look 2026: current iOS/Android
   design language, the best game and social apps (Xbox, PlayStation App,
   Steam, Backloggd, Letterboxd, Spotify, Apple Music, Arc, Things…), design
   showcases. Write down what is worth taking and why.
2. **A design system before screens**: tokens (colour, type scale, spacing,
   radii, elevation, blur), motion rules, and the few components everything is
   made of (a row, a card, a sheet or page, a button, a field, a toggle, a
   picker, an avatar, a cover, a progress mark, the bottom bar). Write them in
   the code as the one source, never styled ad hoc per screen.
3. **Mockups before code.** Show the owner the direction on real-looking
   content — Home, the Feed, the game page, an achievement — as screenshots
   (the dev server and the screenshot tool) or an HTML mockup, two or three
   different directions at first. Build only after the owner picks one.
4. **Build screen by screen**, each complete and working before the next, on
   the API that exists (`webapp/src/api`) and the behaviour kept in
   `webapp/src/core`. Order: shell and bottom bar → Home → Feed → game page and
   achievements → achievement / post pages → search and people → profile and
   card → notifications → settings → sign-in and first run → admin.
5. **Show each screen** as a screenshot from the running dev server before
   moving on; the owner judges on a phone-sized frame.

## Quality bar

- Typography with a real scale and hierarchy; numbers in tabular figures.
- Motion that explains (a page sliding in from where it was tapped, a heart
  that pops), never decoration for its own sake; respects reduced motion.
- Touch targets of 44 px or more; nothing depends on hover.
- Loading states that hold the layout (no jumping), empty states that say
  what to do next, errors worded in the app's language.
- Fast on a mid-range phone: no huge DOM, long lists built as one scrolls,
  pictures lazy.
- Accessible contrast in both the dark and any light theme.

## Out of scope

- The server and the API, unless a screen truly needs something new — then
  say so and add it the usual way (with tests).
- The bot's Telegram messages.
