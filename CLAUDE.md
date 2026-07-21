# ScoreAnim — CLAUDE.md

Desktop app (Python/PySide6) that animates an already-formatted music score
(Dorico-exported MusicXML) in sync with a recorded audio performance
(wav/mp3), for overlay on performance video.

Read `docs/ARCHITECTURE.md` before making design decisions.
Read `docs/PHASES.md` to see what is in scope right now. Do not build ahead
of the current phase.

## Non-negotiable rules (the load-bearing walls)

1. **Core is pure Python. Nothing under `scoreanim/core/` may import
   PySide6/PyQt/Qt.** Qt lives only in `scoreanim/render/` and
   `scoreanim/ui/`. There is a test (`tests/test_no_qt_in_core.py`) that
   enforces this; it must always pass.

2. **Time is never accumulated.** No `t += dt` anywhere. Animation state is
   a pure function `state(t)`. `t` comes from an injected `Clock`:
   `AudioClock` (audio playhead position) for live playback, `FrameClock`
   (`t = n / fps`) for deterministic export, `WallClock` (perf_counter
   since play-anchor, no-audio playback — FIX 2). The animation layer
   never reads a timer itself.

3. **The audio playhead is the master clock during live playback.** The
   animation reads it; never the reverse. Amendment (FIX 2, 2026-07-20):
   when NO recording is loaded the score still plays, driven by
   `WallClock` (`ui/wall_clock.py`) — a wall-anchored, re-anchored-on-
   seek/pause pure function (rule 2 holds; no `t += dt`), paced by the
   tempo map with offset 0. AudioClock remains master whenever audio IS
   loaded; the controller picks the clock by `transport.has_media()`.

4. **Engraving is behind the `EngravingProvider` interface.** Verovio types,
   Verovio element IDs, and Verovio SVG never leak past the adapter in
   `core/engraving/verovio_adapter.py`. Everything downstream uses our own
   `ElementId` and neutral `Layout` types. The adapter always sets a fixed
   `xmlIdSeed` so Verovio IDs are deterministic across loads — overrides,
   style rules, and tests depend on stable `ElementId`s.
   Amendment, Phase 11 (2026-07-15 ruling): an unknown drawable SVG
   class no longer fails the load in the app path — it degrades to a
   warned static OTHER element (`LoadWarning "unknown-class"`; the
   status bar counts it, stderr names the class). Tests stay strict:
   `load_detailed(..., strict=True)` (the default, and the
   score-doctor's `--strict`) still raises, so coverage gaps surface
   loudly in development. The doctor (`python -m
   scoreanim.tools.check_score`) is the triage engine for new exports.

5. **The project document stores user intent only, never derived data.**
   Layouts, timemaps, and decomposed elements are always re-derived from
   (score file + engraving params + overrides). Layout overrides are
   dx/dy deltas keyed by musical `ElementId`, never absolute pixels.

6. **Effects are data, not code.** An effect is a named bundle of
   `(property, Envelope)` tracks evaluated at `t_rel` to onset. Adding a
   new effect means adding data/preset definitions, not branching in the
   evaluator. **Animation is a DENYLIST** (user-ruled 2026-07-20):
   every object on the page animates with the appear/effect system
   EXCEPT the true scaffold — staff lines, barlines, group
   symbols/brackets, system dividers (`schedule.STATIC_KINDS`) — plus
   page furniture (part labels, header/footer, measure numbers, minted
   onset-less). A new `ElementKind` animates by default; the adapter
   resolves an onset for it (10R.2 attach mechanism, else measure
   start). This ruling changes ANIMATION scope only — color scope
   (`TINTED_KINDS`) is unchanged, so clefs and key signatures animate
   but stay black. See ARCHITECTURE.md §3 "Animated-ink taxonomy".

7. **The user owns page layout.** We honor the MusicXML's encoded
   SYSTEM breaks always (Verovio break-respect mode). We never reflow
   to fit the window. Paged presentation; mismatched aspect is
   letterboxed. Three amendments (Phase 10R 2026-07-13; (c) Phase 12.5
   2026-07-21):
   (a) encoded PAGE breaks are honored unless a system would overflow
   its page (Dorico breaks are computed assuming hidden staves) — then
   the adapter keeps the system breaks, re-derives page breaks at the
   prep seam, and re-engraves once (`LoadWarning "repaginated"`;
   page-scoped ids shift). **Ink is never clipped.** (b) staves empty
   for a whole system may be hidden via the per-score **Hide Empty
   Staves** option (Verovio `optimize` over an MEI round-trip; the
   MusicXML itself carries no hidden-staff info) — default ON for new
   documents, OFF for pre-v4 projects, undoable, an engraving input
   like staff groups. Slash regions win over hiding (rule 10;
   `LoadWarning "hide-unavailable"`). (c) When a single system is still
   taller than its page after (a)/(b) and condensing — pagination cannot
   split one system — the adapter **scales the whole engraving down
   uniformly so the tallest system fits** (`LoadWarning "scaled-to-fit"`;
   a rastral-size reduction, derived every load, not window reflow). This
   completes never-clip: any orchestral score renders without clipped
   ink. Condensing (rule 11) is the readability lever; scale-to-fit is
   the guarantee.
   (Built in Phase 9: part-label edits re-engrave via the prep seam so
   the score shifts to fit — a re-engrave with changed inputs is not
   window reflow; title/tempo texts edit as stage overlay and never
   re-engrave. See docs/BACKLOG.md item 5, resolved as split.)

8. **Every document mutation is an undoable command** (command pattern)
   from the first mutation implemented onward.

9. **ScoreAnim always animates concert pitch.** Verovio's
   `transposeToSoundingPitch: True` is a fixed part of `EngravingParams`,
   not a user option in v1. Exception: parts whose MusicXML `<transpose>`
   is octave-only (`octave-change` with no chromatic shift — e.g. guitar,
   bass guitar) keep their conventional written octave; chromatic
   transpositions are rendered at concert pitch. All fidelity comparisons
   and test expectations are against concert-pitch renders.

10. **Slash AND bar-repeat regions are first-class.** Dorico exports
    slash regions as `<measure-style><slash/>` and measure repeats as
    `<measure-repeat>`, both with no notes; Verovio draws NOTHING for
    either (they import as empty `<space>` — verified Phase 12). The
    adapter synthesizes them: slash elements one per beat
    (`kind = SLASH`), and one `%` bar-repeat symbol per repeated measure
    (`kind = BAR_REPEAT`, onset on the downbeat — Phase 12.2), so both
    render and animate like notes. See docs/ARCHITECTURE.md §3.

11. **Condensing is a prep-seam engraving input; the document stores
    condense groups only.** Dorico's condensing is layout-time and does
    NOT export, so a condensed look is reconstructed in-app: contiguous
    like parts merge onto one staff (one voice per source player,
    combined label) by rewriting the part-list BEFORE Verovio (Phase
    12.3, the Phase 8/9 prep-seam pattern). The doc stores `condense_
    groups` (user intent, schema v5); the merged part-list, geometry, and
    shifted ElementIds all re-derive (rule 5). v1 is naive (Marcus,
    2026-07-21): shared staff, one voice per player, NO a2 unison
    collapse and NO divisi logic (BACKLOG). Load-time layout choices
    (condense, bracket, hide) are gathered in the **Score Setup dialog**
    and applied as ONE undoable step. When a single system is still
    taller than its page after these choices (and repagination), the
    adapter **scales the engraving down uniformly to fit** — the
    never-clip completion (rule 7 amendment c).

## Stack (do not substitute without discussion)

- Python 3.11+, PySide6 (LGPL — not PyQt), `verovio` (pip package),
  `music21` for score parsing, `pytest` for tests.
- Audio playback: `QMediaPlayer`/`QAudioSink` via a thin wrapper in
  `render/` or `ui/` that exposes only "current position in seconds" to
  core through the `Clock` interface.
- Do not hand-roll MusicXML parsing, engraving, or a timemap — Verovio and
  music21 provide these.

## Package layout

```
scoreanim/
  core/                    # pure Python, no Qt
    score/                 # music21 parsing → ScoreModel, ElementIdentity
    engraving/             # EngravingProvider ABC, Layout, verovio_adapter
    timing/                # TempoMap (BPM events, taps, swing), beat↔seconds
    animation/             # properties, Envelope, Effect, RevealMode, state(t)
    project/               # Project document, commands/undo, serialization
  render/                  # Qt only: Layout → QGraphicsItems, property application
  ui/                      # windows, stage view, tempo lane, waveform, transport
  app.py
tests/                     # headless: core logic tested without any GUI
testdata/                  # testscore.musicxml (Dorico export) + companion
                           # PDF — primary fixture for spikes and tests;
                           # video_test.musicxml — production score with
                           # a multi-staff piano (Phase 10 fixture);
                           # complex1.musicxml — 14-part Dorico robustness
                           # fixture (Phase 11: tremolo, mRest ledger,
                           # grace-join gap); complex2.musicxml — orchestral
                           # (36 parts/37 staves, bar repeats, appoggiaturas),
                           # lays out via Phase 12 (order-based join,
                           # condensing, bar-repeat synthesis, scale-to-fit);
                           # bar_repeat_min / condense_min / tall_system_min —
                           # small Phase 12 fixtures extracted from complex2
docs/
```

## Working style

- Small, verifiable steps. Each task in `docs/PHASES.md` ends with a
  concrete check ("run X, see Y"). Do the check before moving on.
- Write headless tests for core logic as you build it, not after. Core
  must be testable with plain `pytest`, no display server.
- Type hints everywhere in `core/`. Frozen dataclasses for model types.
- Prefer boring, explicit code over cleverness. No premature abstraction
  beyond the seams named in the architecture (provider, clock, envelope).
- If a Verovio or music21 behavior is uncertain, write a tiny spike script
  in `spikes/` to confirm before integrating. Keep spikes; they document
  library behavior.
- When something in the architecture doesn't survive contact with reality,
  stop and flag it in the session rather than silently deviating.

## Verification quick reference

```
pytest                         # all headless tests
pytest tests/test_no_qt_in_core.py   # boundary check
python -m scoreanim            # launch app (phases 2+)
python spikes/<name>.py        # spike scripts
```
