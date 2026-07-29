# ScoreAnim — CLAUDE.md

Desktop app (Python/PySide6) that animates an already-formatted music score
(Dorico-exported MusicXML) in sync with a recorded audio performance
(wav/mp3), for overlay on performance video.

## Session protocol — read in this order

- `docs/WORKLOG.md` — where the project is RIGHT NOW. Read it first;
  append one line at session end.
- `docs/ROADMAP.md` — the process ("Process — two tracks", including the
  feature-plan checklist) and milestone scope. Do not build ahead of
  what is agreed there.
- `docs/PATTERNS.md` — the established idioms and traps. Every plan
  names which idiom it rides; deviating from one is a flag-and-stop.
- `docs/ARCHITECTURE.md` — design decisions; read before making new ones.
- `docs/PHASES.md` — frozen v0.1-alpha build history; reference, never
  appended to. `docs/briefs/` hold how each milestone was built.

## Process — two tracks (Marcus, 2026-07-29)

**Feature track (the default):** one session per feature — propose a
short plan in-conversation and wait for approval; build in small
verified steps with headless tests for pure logic; suite + goldens
green; the session manages branch/commits/merge itself after Marcus
confirms in the running app; append to WORKLOG.md. No per-feature tag.

**Milestone track** — REQUIRED when work bumps the project schema,
changes adapter/prep-seam semantics or moves goldens, or amends a rule
in this file: ROADMAP scope → brief with spike-first measurements →
Marcus rules the decisions → build → his exit run → merge + tag.

**Escalation is one-way and mandatory:** feature work that discovers it
needs any of the above STOPS and flags — it becomes milestone work.
The full plan checklist lives in ROADMAP §"Process — two tracks".

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
   Verovio element IDs, and Verovio SVG never leak past the adapter package
   `core/engraving/verovio/`. Everything downstream uses our own
   `ElementId` and neutral `Layout` types. The adapter always sets a fixed
   `xmlIdSeed` so Verovio IDs are deterministic across loads — overrides,
   style rules, and tests depend on stable `ElementId`s; the golden
   suite (`tests/goldens/`, Phase R) pins 12 fixture loads byte-for-byte
   on exactly that determinism.
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
   evaluator. Amendment (M4, 2026-07-25): an effect may carry scalar
   data the applier consumes generically — a per-element timescale
   (note-value settle, duration from the engraved timemap per rule 12)
   and a signed trigger shift (peak offset). Both are inputs to the one
   evaluation kernel
   (`element_state(trigger, effect, t, timescale)` =
   `state_at((t − trigger − shift) / timescale)`); neither is a branch
   on an effect's name. **Animation is a DENYLIST** (user-ruled 2026-07-20):
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
   letterboxed.
   Amendment (M5, 2026-07-28): the honored system-break set is the
   encoded breaks ⊕ the user's in-app break overrides
   (`doc.system_break_overrides`, applied at the prep seam). Still never
   window reflow: an edited break set is an engraving input like a part
   rename. Suppressing a break also clears a coincident encoded
   new-page — a page break implies a system break, so leaving it would
   make the suppression inert — and pagination then re-derives by the
   rule-7(a) mechanism below, so suppressing a SYSTEM break can move a
   PAGE break: the page count is **owned, not clipped** (D7).
   Amendment (M6, 2026-07-28): the honored PAGE-break set is likewise
   the encoded page breaks ⊕ the user's in-app page-break overrides
   (`doc.page_break_overrides`), written by the SAME prep-seam pass as
   the system delta — `_apply_breaks` visits one `<print>` once and
   writes both attributes, because two passes racing on one element
   manufacture false inert warnings. Page breaks are the one layout
   input the app already OWNED before the user could author them —
   rule 7(a)'s never-clip repagination re-derives them whenever a system
   would overflow — so authored page intent is honored *within* that
   guarantee, not above it: a forced page break is an INPUT to the
   re-derived plan and survives repagination, and a suppressed one is
   overridden, and warned (`page-break-repaginated`), whenever honoring
   it would clip ink. Never-clip stays absolute; the page count stays
   owned. Where the two maps disagree at one ordinal, **a page break
   implies a system break**: page FORCE beats a coincident system
   SUPPRESS, and page SUPPRESS asserts `new-system="yes"` rather than
   clearing the measure's only marker (the mirror of D7 above) — unless
   the system break is separately suppressed too, which is a coherent
   pair of negatives. The toggles clear the one contradicting pair in
   the same undo entry (`core/editing/break_coherence.py`), so that
   precedence exists for hand-edited files and rule-5 staleness rather
   than for anything the UI can author. And a repagination may NOT
   change SYSTEM content: `_repaginate` promotes every encoded
   `new-page="yes"` to also carry `new-system="yes"` before it strips
   (BACKLOG 16, paid in M6.0).
   Three further amendments (Phase 10R 2026-07-13; (c) Phase 12.5
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
   `LoadWarning "hide-unavailable"`). Amendment (Marcus, 2026-07-24,
   schema v6): a second per-score option, **Hide Empty Staves on First
   System**, extends the hiding to system 1 (Verovio
   `condenseFirstPage` on the same round-trip — id- and
   timemap-transparent, spikes/hide_first_system.py); default OFF, so
   first-system-full remains the convention, and inert unless hiding
   is on. (c) When a single system is still
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

12. **The engraved timemap is the single beat authority** (ruling
    2026-07-22, FINDING-1 fix). Every beat in the app — note onsets,
    measure starts/spans, triggers, reveal anchors, rest caps,
    score_end, export ranges, TempoMap positions — lives on ONE axis:
    Verovio's timemap qstamps, exposed as `EngravedScore.timeline`
    (`MeasureTimeline`, per-ordinal starts/durations). This is the
    PERFORMANCE axis: the timemap is playback-expanded, so a repeated
    span occupies its passes' beats (repeated bars keep first-pass
    positions and stay lit through later passes; post-repeat music
    syncs with a recording that takes the repeat).
    `build_score_model` REQUIRES the timeline and rebases music21's
    accounting onto it (`onset = starts[ordinal] + intra-measure
    offset`) — music21's own inter-measure accumulation is never
    trusted (it pads pickups to nominal length, never expands repeats,
    rounds half-beat bars, and can self-diverge between parts;
    spikes/beat_domain.py is the census). One exception: a trailing
    event-less bar (final bar-repeat) has no timemap end, so the last
    measure's span is floored with its notated length. Intra-measure
    offsets stay music21's (an appoggiatura-delayed principal still
    triggers at its notated beat — the shear was inter-measure only).

13. **Selection is object-first; a measure is never selected**
    (ruling 2026-07-27). The user selects OBJECTS — noteheads,
    dynamics, hairpins, texts, barlines. A measure is not a selectable
    thing. Selecting an object implicitly carries its containing
    measure AND the part whose staff it sits on; both are DERIVED from
    the element id grammar, never from geometry, and never stored. A
    barline is an object IN a measure, not the measure itself, so it
    stays selectable — it is M5's only handle. Selection state and the
    way selection LOOKS are both transient render state: never in the
    document, never a style override, never undoable (rule 8 needs
    something to undo). That boundary is what lets M3 exist — the same
    element can be selected (transient) and color-overridden (intent,
    rule 5) at the same time, and the two must stay distinguishable on
    screen.

## Stack (do not substitute without discussion)

- Python 3.11+, PySide6 (LGPL — not PyQt), `verovio` (pip package),
  `music21` for score parsing, `pytest` for tests.
- Audio playback: `QMediaPlayer`/`QAudioSink` via a thin wrapper in
  `render/` or `ui/` that exposes only "current position in seconds" to
  core through the `Clock` interface.
- Do not hand-roll MusicXML parsing, engraving, or a timemap — Verovio and
  music21 provide these.

## Package layout

One-line map only — module histories and per-milestone detail live in
ARCHITECTURE §7 and `docs/PATTERNS.md`; do not re-grow them here.

```
scoreanim/
  core/            # pure Python, no Qt (rule 1)
    score/         # music21 → ScoreModel; musicxml_prep.py (prep-seam
                   # orchestrator) + musicxml_rewrite.py (the passes)
    engraving/     # EngravingProvider ABC, neutral Layout types
      verovio/     # adapter package, one module per pipeline stage:
                   # kinds (policy tables) · mei_index · records ·
                   # decompose · attribution · identity · synthesis ·
                   # provider (toolkit, retries, pipeline)
    timing/        # TempoMap (BPM events, taps, swing), beat↔seconds
    animation/     # Envelope, Effect, state(t); durations.py seam
    selection/     # pure hit-priority policy, Selection context,
                   # highlight colors
    editing/       # pure edit policies: text_route · nudge · segments ·
                   # breaks · page_breaks · break_coherence
    project/       # document, serialization (schema version lives
                   # here), commands/ split by domain
  render/          # Qt only: Layout → QGraphicsItems, property
                   # application, reveal clipping, export scenes
  ui/              # Qt shell; window = composition root, one module per
                   # responsibility: view_router · menus · parts_menu ·
                   # inspector + panels/ · selection · text_edit ·
                   # nudge · break_action · layout_zone · transport ·
                   # file_actions · score_loader · document_sync ·
                   # window_state · stage view, lanes, playback,
                   # app_state, dialogs
  app.py
tests/             # headless; tests/goldens/ pins fixture loads
                   # byte-for-byte
testdata/          # Dorico fixtures: testscore (primary) · video_test ·
                   # complex1..3 · bigband1 (app-path only: 'gliss') ·
                   # bar_repeat_min · condense_min · tall_system_min ·
                   # pickup_min · brackets
docs/              # WORKLOG (state) · ROADMAP (process + milestones) ·
                   # PATTERNS (idioms) · ARCHITECTURE (design) ·
                   # BACKLOG · briefs/ · PHASES (frozen)
```

## Working style

- **No monoliths — this is a hard rule (Marcus, 2026-07-24).** Every
  module has ONE clear responsibility and stays small enough to read top
  to bottom. Treat a file approaching ~400 lines, or one that has started
  doing two jobs, as a refactor signal: split it along a real seam BEFORE
  adding more, not "later" — and the split is its own commit with no
  feature code in it (PATTERNS: "the split-first commit"). No
  god-objects, narrow interfaces, pure logic factored out of Qt so it
  can be tested headless (rule 1 already forces this seam for core/).
  Readability, maintainability, and robustness beat expedience
  everywhere; flag-and-stop applies to code hygiene, not just
  architecture.
- Small, verifiable steps. Every task — milestone-brief task or
  feature-plan step — ends with a concrete check ("run X, see Y"). Do
  the check before moving on.
- Write headless tests for core logic as you build it, not after. Core
  must be testable with plain `pytest`, no display server.
- Type hints everywhere in `core/`. Frozen dataclasses for model types.
- Prefer boring, explicit code over cleverness. No premature abstraction
  beyond the seams named in the architecture (provider, clock, envelope).
- **Plain language everywhere you write words (Marcus, 2026-07-29).**
  Code comments, docstrings, plan messages, commit messages, user-facing
  warnings, and doc updates are written in plain, everyday language:
  short sentences, one idea each, no dense or overly compressed
  phrasing, no jargon where a common word works. If a sentence needs
  re-reading to parse, rewrite it. Explaining simply beats sounding
  technical.
- If a Verovio or music21 behavior is uncertain, write a tiny spike script
  in `spikes/` to confirm before integrating. Keep spikes; they document
  library behavior.
- When something in the architecture doesn't survive contact with reality,
  stop and flag it in the session rather than silently deviating.

## Verification quick reference

```
pytest                         # all headless tests
pytest tests/test_no_qt_in_core.py   # boundary check
python -m scoreanim            # launch app
python spikes/<name>.py        # spike scripts
python -m scoreanim.tools.check_score <file>   # score doctor (triage)
```
