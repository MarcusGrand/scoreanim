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
   (`t = n / fps`) for deterministic export. The animation layer never
   reads a timer itself.

3. **The audio playhead is the master clock during live playback.** The
   animation reads it; never the reverse.

4. **Engraving is behind the `EngravingProvider` interface.** Verovio types,
   Verovio element IDs, and Verovio SVG never leak past the adapter in
   `core/engraving/verovio_adapter.py`. Everything downstream uses our own
   `ElementId` and neutral `Layout` types. The adapter always sets a fixed
   `xmlIdSeed` so Verovio IDs are deterministic across loads — overrides,
   style rules, and tests depend on stable `ElementId`s.

5. **The project document stores user intent only, never derived data.**
   Layouts, timemaps, and decomposed elements are always re-derived from
   (score file + engraving params + overrides). Layout overrides are
   dx/dy deltas keyed by musical `ElementId`, never absolute pixels.

6. **Effects are data, not code.** An effect is a named bundle of
   `(property, Envelope)` tracks evaluated at `t_rel` to onset. Adding a
   new effect means adding data/preset definitions, not branching in the
   evaluator.

7. **The user owns page layout.** We honor the MusicXML's encoded system
   and page breaks (Verovio break-respect mode). We never reflow to fit
   the window. Paged presentation; mismatched aspect is letterboxed.
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

10. **Slash regions are first-class.** Dorico exports slash regions as
    `<measure-style><slash/>` with no notes; the adapter must synthesize
    slash elements (one per beat, `kind = SLASH`, onsets on the beats) so
    they render and animate like notes. See docs/ARCHITECTURE.md §3.

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
                           # PDF — primary fixture for spikes and tests
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
