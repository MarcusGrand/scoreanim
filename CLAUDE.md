# ScoreAnim — CLAUDE.md

Desktop app (Python/PySide6) that animates an already-formatted music
score (Dorico-exported MusicXML) in sync with a recorded audio
performance (wav/mp3), for overlay on performance video.

## Session protocol

Read `docs/WORKLOG.md` — one short file, tells you where the project is
right now. Append one line to it before you finish.

Everything else is read on demand, only when the task needs it:

- `docs/PATTERNS.md` — how this codebase solves problems, and the traps
  that have already cost a debugging session. Read it when you are about
  to touch a seam it names.
- `docs/ARCHITECTURE.md` — design decisions and the full adapter
  obligations. Read it before making a new design decision.
- `docs/BACKLOG.md` — known gaps and deferred work.
- `docs/RULES.md` — the long form of the rules below, with the dated
  rulings behind them. Read a section when a rule's short form is not
  enough to decide.
- `docs/history/` — the archive (old roadmap, phase history, milestone
  briefs). Do not read it unless Marcus asks about history.

## How we work

Marcus prompts one task at a time. Build it. There is no plan-approval
step, no brief, no milestone ceremony — those are retired.

- Work in small steps, and end each one with a real check ("run X, see
  Y"). Do the check before moving on.
- Write headless tests for pure logic as you write the logic, not after.
- Keep the tests green. Run the full suite before you merge.
- Git: a branch for anything bigger than a small fix, commit as you go,
  merge to `main` after Marcus confirms it works in the running app. No
  tags unless he asks.
- Finish by appending one line to `docs/WORKLOG.md`.

**Ask first, in one sentence, before you do any of these three things.**
They are cheap to ask about and expensive to get wrong:

1. Bumping the project schema — it changes project files Marcus has
   already saved.
2. Re-capturing goldens (`SCOREANIM_UPDATE_GOLDENS=1`) — that command
   will happily bless a real regression, so he wants eyes on the diff.
3. Changing a rule in this file.

Everything else: just do it.

If the task turns out to be much bigger than it sounded, or you cannot
tell what Marcus means, say so in a sentence and ask. Don't guess, and
don't write a planning document.

**Flag and stop** when reality contradicts what the docs say, rather
than silently working around it. That applies to code hygiene too — a
module about to bloat is worth stopping over.

## The rules (the load-bearing walls)

The short form is here. `docs/RULES.md` has the long form and the
history; `docs/ARCHITECTURE.md` has the mechanisms.

1. **Core is pure Python. Nothing under `scoreanim/core/` may import
   PySide6/PyQt/Qt.** Qt lives only in `scoreanim/render/` and
   `scoreanim/ui/`. `tests/test_no_qt_in_core.py` enforces this and must
   always pass.

2. **Time is never accumulated.** No `t += dt` anywhere. Animation state
   is a pure function `state(t)`, and `t` comes from an injected
   `Clock`: `AudioClock` for live playback, `FrameClock` (`t = n / fps`)
   for deterministic export, `WallClock` for playback with no audio
   loaded. The animation layer never reads a timer itself.

3. **The audio playhead is the master clock during live playback.** The
   animation reads it, never the reverse. With no recording loaded the
   score still plays, driven by `WallClock` (re-anchored on seek and
   pause, so rule 2 still holds). The controller picks the clock by
   `transport.has_media()`.

4. **Engraving is behind the `EngravingProvider` interface.** Verovio
   types, Verovio ids and Verovio SVG never leak past the adapter
   package `core/engraving/verovio/`; everything downstream uses our own
   `ElementId` and neutral `Layout` types. The adapter always sets a
   fixed `xmlIdSeed`, so ids are deterministic across loads — overrides,
   style rules and the golden suite all rest on that. An unknown drawable
   SVG class degrades to a warned static element in the app, but still
   raises under `strict=True` (the pytest and score-doctor default), so
   coverage gaps stay loud. Triage a new export with `python -m
   scoreanim.tools.check_score`.

5. **The project document stores user intent only, never derived data.**
   Layouts, timemaps and decomposed elements are always re-derived from
   the score file plus engraving params plus overrides. Layout overrides
   are dx/dy deltas keyed by musical `ElementId`, never absolute pixels.

6. **Effects are data, not code.** An effect is a named bundle of
   `(property, Envelope)` tracks evaluated against the time since onset.
   Adding an effect means adding data, never branching on an effect's
   name in the evaluator. An effect may carry scalar data the applier
   consumes generically (a per-element timescale, a signed trigger
   shift); both feed the one kernel, `element_state(trigger, effect, t,
   timescale)`. **Animation is a denylist**: everything on the page
   animates except the true scaffold — staff lines, barlines, group
   brackets, system dividers — plus page furniture. A new `ElementKind`
   animates by default. Colour scope (`TINTED_KINDS`) is a separate
   list, so clefs and key signatures animate but stay black. Glow scope
   (`GLOWING_KINDS`) is a third list and the one ALLOWLIST: a halo marks
   a sounding note, so it reaches a note and the ink drawn as part of
   one, and nothing else. A new `ElementKind` is dark until somebody
   decides it is a note.

7. **The user owns page layout, and ink is never clipped.** We honor the
   score's encoded system and page breaks, combined with the user's own
   break overrides, applied at the prep seam. We never reflow to fit the
   window. When a system would overflow its page the app re-derives
   pagination — so the page count is owned, not clipped — and if a single
   system is still too tall it scales the whole engraving down uniformly.
   Hiding empty staves and condensing are the readability levers;
   scale-to-fit is the guarantee. Every one of those adjustments raises a
   `LoadWarning`. The precedence rules where the two break maps disagree
   are in `docs/RULES.md` rule 7 and `core/editing/break_coherence.py`.

8. **Every document mutation is an undoable command** (command pattern).

9. **ScoreAnim always animates concert pitch.**
   `transposeToSoundingPitch: True` is fixed, not a user option.
   Exception: parts whose `<transpose>` is octave-only (guitar, bass
   guitar) keep their conventional written octave. All test expectations
   are against concert-pitch renders.

10. **Slash and bar-repeat regions are first-class.** Verovio draws
    nothing for either — they import as empty `<space>` — so the adapter
    synthesizes them: one slash element per beat, one `%` symbol per
    repeated bar on the downbeat. Both render and animate like notes.

11. **Condensing is a prep-seam engraving input; the document stores
    condense groups only.** Dorico's condensing does not export, so a
    condensed look is rebuilt in-app by rewriting the part list before
    Verovio. The merged part list, geometry and shifted ids all re-derive
    (rule 5). v1 is deliberately naive: shared staff, one voice per
    player, no a2 collapse and no divisi.

12. **The engraved timemap is the single beat authority.** Every beat in
    the app — onsets, measure starts and spans, triggers, reveal anchors,
    score end, export ranges, tempo positions — lives on one axis:
    Verovio's timemap, exposed as `EngravedScore.timeline`. It is the
    performance axis, so repeats occupy their passes' beats and playback
    stays in sync with a recording that takes the repeat.
    `build_score_model` rebases music21's accounting onto it; music21's
    own inter-measure accumulation is never trusted.

13. **Selection is object-first; a measure is never selected.** The user
    selects objects — noteheads, dynamics, hairpins, texts, barlines. An
    object implicitly carries its measure and its part, both derived from
    the element id grammar, never from geometry and never stored.
    Selection state and the way selection looks are transient render
    state: never in the document, never a style override, never undoable.
    One exception: a part label carries no part in its id, so the adapter
    joins it to its part from document order and checks every pairing
    against the label text the score carries. A pairing it cannot vouch
    for keeps `part=None`, which disables the rename instead of renaming
    the wrong instrument.

## Stack (do not substitute without discussion)

- Python 3.11+, PySide6 (LGPL — not PyQt), `verovio` (pip package),
  `music21` for score parsing, `pytest` for tests.
- Audio playback: `QMediaPlayer`/`QAudioSink` behind a thin wrapper that
  exposes only "current position in seconds" to core, through `Clock`.
- Do not hand-roll MusicXML parsing, engraving, or a timemap — Verovio
  and music21 provide these.

## Package layout

One-line map only. Module detail lives in ARCHITECTURE §7; do not
re-grow it here.

```
scoreanim/
  core/            # pure Python, no Qt (rule 1)
    score/         # music21 → ScoreModel; musicxml_prep.py (prep-seam
                   # orchestrator) + musicxml_rewrite.py (the passes)
    engraving/     # EngravingProvider ABC, neutral Layout types
      verovio/     # adapter package, one module per pipeline stage:
                   # kinds (policy tables) · mei_index · records ·
                   # decompose · attribution · label_parts · identity ·
                   # synthesis · provider (toolkit, retries, pipeline)
    timing/        # TempoMap (BPM events, taps, swing), beat↔seconds
    animation/     # Envelope, Effect, state(t); durations.py seam
    selection/     # pure hit-priority policy, Selection context,
                   # highlight colors
    editing/       # pure edit policies: text_route · nudge · segments ·
                   # breaks · page_breaks · break_coherence · deletion
    project/       # document, serialization (schema version lives
                   # here), commands/ split by domain
  render/          # Qt only: Layout → QGraphicsItems, property
                   # application, reveal clipping, export scenes
  ui/              # Qt shell; window = composition root, one module per
                   # responsibility: view_router · menus · parts_menu ·
                   # inspector + panels/ · selection · text_edit ·
                   # nudge · break_action · layout_zone · transport ·
                   # file_actions · score_loader · document_sync ·
                   # window_state · recents · stage view, lanes,
                   # playback, app_state, dialogs
  app.py
tests/             # headless; tests/goldens/ pins fixture loads
                   # byte-for-byte
testdata/          # Dorico fixtures: testscore (primary) · video_test ·
                   # complex1..3 · bigband1 (app-path only: 'gliss') ·
                   # bar_repeat_min · condense_min · tall_system_min ·
                   # pickup_min · brackets
docs/              # WORKLOG (state) · PATTERNS (idioms) ·
                   # ARCHITECTURE (design) · BACKLOG · RULES (long form)
                   # · history/ (archive — roadmap, phases, briefs)
```

## Working style

- **No monoliths — this is a hard rule.** Every module has one clear
  responsibility and stays small enough to read top to bottom. A file
  approaching ~400 lines, or one that has started doing two jobs, is a
  refactor signal: split it along a real seam before adding more, and
  make the split its own commit with no feature code in it. No
  god-objects, narrow interfaces, pure logic factored out of Qt so it can
  be tested headless.
- Small, verifiable steps. Every step ends with a concrete check.
- Type hints everywhere in `core/`. Frozen dataclasses for model types.
- Prefer boring, explicit code over cleverness. No premature abstraction
  beyond the seams the architecture already names (provider, clock,
  envelope).
- **Plain language everywhere you write words.** Comments, docstrings,
  commit messages, warnings and doc updates all use plain, everyday
  language: short sentences, one idea each, no jargon where a common word
  works. If a sentence needs re-reading to parse, rewrite it.
- If a Verovio or music21 behavior is uncertain, write a small spike
  script in `spikes/` to confirm before integrating. Keep spikes — they
  document how the libraries actually behave.

## Verification quick reference

```
pytest                         # headless suite
pytest tests/test_no_qt_in_core.py   # boundary check
python -m scoreanim            # launch app
python spikes/<name>.py        # spike scripts
python -m scoreanim.tools.check_score <file>   # score doctor (triage)
```
