# ScoreAnim — Phased build plan

Rules: one phase at a time. Every task ends with a concrete verification.
A phase is done when its exit criteria pass. Do not start UI polish, extra
effects, or later-phase features early. Flag architecture problems the
moment they appear instead of working around them silently.

## Phase 0 — Fidelity & feasibility spikes (no app code) — ✅ COMPLETE 2026-07-10

Exit criteria passed: fidelity judged acceptable by the user against the
concert-pitch renders; timemap and per-element addressability confirmed.
Findings, options, and library behavior are recorded in `spikes/NOTES.md`;
accepted rendering deviations are filed in `docs/BACKLOG.md`. Rulings from
closure: concert pitch always (octave-only transpositions keep written
octave), adapter synthesizes slash regions, adapter always sets xmlIdSeed
— see CLAUDE.md rules 4/9/10 and ARCHITECTURE.md §3.

Purpose: kill the two biggest unknowns before any architecture exists.
Everything here lives in `spikes/`, is throwaway-quality but kept.

Test material: the user provides `testdata/testscore.musicxml` (Dorico
export) and, if available, its companion PDF (`testdata/testscore.pdf`)
for fidelity comparison. Use this score for all Phase 0 spikes and as the
primary fixture for headless tests in later phases. If it is missing,
stop and ask the user rather than substituting another score for 0.2;
music21 corpus scores are acceptable stand-ins for 0.3–0.4 only.

- [x] **0.1 Environment**: pyproject with Python 3.11+, PySide6, verovio,
      music21, pytest. Verify: `python -c "import verovio, music21, PySide6"`.
- [x] **0.2 Dorico→Verovio fidelity test**: load
      `testdata/testscore.musicxml` with verovio, breaks-honored mode,
      render all pages to SVG files. Verify: page count and
      measure-per-system distribution match the Dorico PDF; the user
      judges visual fidelity side by side. Document deviations in
      `spikes/NOTES.md`.
- [x] **0.3 Timemap spike**: from `testscore.musicxml`, get Verovio's
      timemap / per-element times. Print `element_id → onset_ms` for the
      first 20 notes. Verify: onsets are monotone and musically plausible.
- [x] **0.4 SVG anatomy spike**: parse one page's SVG from the test score;
      enumerate element classes and ids (noteheads, stems, beams, slurs,
      dynamics). Verify: noteheads and slurs are individually addressable;
      write findings (granularity, ID scheme, staff/layer nesting) to
      `spikes/NOTES.md`.

**Exit criteria**: fidelity judged acceptable by the user; timemap and
per-element addressability confirmed. If fidelity fails, stop and discuss
(hybrid backdrop approach) before Phase 1.
**PASSED 2026-07-10.** The MusicXML encodes written pitch while the
companion PDF is concert pitch; all fidelity comparisons and test
expectations from here on are against concert-pitch renders (CLAUDE.md
rule 9).

## Phase 1 — Core skeleton: parse → Layout → headless tests — ✅ COMPLETE 2026-07-10

Exit criteria passed: 43 headless tests green; `python -m
scoreanim.tools.dump_notes testdata/testscore.musicxml` prints all 500
noteheads + 52 synthesized slashes with (part, onset_beats, page, x, y).
Build findings (Verovio stylesheet baking, ChordSymbol exclusion,
accid.ges unreliability → join keys on (step, octave), tied-to notes as
fresh timemap onsets) recorded in `spikes/NOTES.md`. Decomposition
fidelity reviewable in the bbox-overlay artifact
(`scoreanim/tools/bbox_overlay.py`).

- [x] **1.1 Package layout** as in CLAUDE.md; `tests/test_no_qt_in_core.py`
      (walks core/ AST or imports, asserts no Qt). Verify: pytest passes.
- [x] **1.2 Core types**: ElementId, ElementIdentity, ElementKind, Layout,
      RenderedElement, EngravingParams, EngravingProvider ABC. Frozen
      dataclasses, full type hints. ElementKind includes SLASH (Phase 0
      ruling). EngravingParams fixes transposeToSoundingPitch=True (not
      user-facing in v1).
- [x] **1.3 Verovio adapter**: MusicXML → Layout. Decompose SVG per
      element; assign our ElementIds; recover part/staff/voice from SVG
      nesting + music21 cross-reference; record bbox and anchor; honor
      encoded breaks; capture page geometry from the score. Always set a
      fixed xmlIdSeed (Verovio ids are otherwise random per load). Render
      at concert pitch; parts with octave-only <transpose> (guitar, bass)
      keep conventional written octave (see ARCHITECTURE.md §3).
      Verify (headless tests against `testdata/testscore.musicxml`,
      concert-pitch expectations): expected page count, expected notehead
      count, a slur with correct extent, identities carrying correct part
      names.
- [x] **1.4 ScoreModel**: music21 parse → onset beats per note, joined to
      ElementIds. Verify: for the test score, `id → onset` matches
      Verovio's timemap ordering.
- [x] **1.5 Slash-region synthesis**: adapter synthesizes slash elements
      for `<measure-style><slash/>` regions — one per beat from the time
      signature, kind = SLASH, staff-positioned, onsets on the beats so
      they animate like notes. Verify (headless test against
      `testdata/testscore.musicxml` mm. 3–19, drum part): slash count per
      measure equals beats from the active 2/4 / 4/4 signature; onsets
      fall on the beats; elements carry page/x/y within the drum staff.

**Exit criteria**: `pytest` green; a script can print, for a real score,
every notehead with (part, onset_beats, page, x, y).

## Phase 2 — Static render: Layout on screen — ✅ COMPLETE 2026-07-11

Exit criteria passed: visual review accepted by the user 2026-07-11
(review artifact: Qt render vs Phase-0 reference vs Dorico PDF, tinted
part demo). 74 headless tests green. `python -m scoreanim <score>` shows
the paged score letterboxed with zoom/pan and a Parts tint menu. Build
findings (header:"none" id-stability + space reclaim, Dorico credit
coordinates unreliable, Qt WindingFill / QPen SVG defaults, Bravura WOFF2
registration) in `spikes/NOTES.md` Phase 2 section. Stage-header defaults
(credit positions ignored, block fitted above the top staff) accepted.

- [x] **2.1 Scene builder** (`render/scene.py`): Layout →
      QGraphicsItems keyed by ElementId; per-element addressability
      demonstrated by recoloring one part.
- [x] **2.2 StageView + minimal app shell**: paged display at the score's
      own aspect, letterboxed; page prev/next; zoom.
      Verify: open `testdata/testscore.musicxml`, flip through pages,
      one part tinted.
- [x] **2.3 Header as stage element** (ruling 2026-07-10, ARCHITECTURE.md
      §3 ruling 4): engrave with Verovio's header suppressed;
      title/composer/lyricist become stage-level text elements in
      stage_config, styled and positioned in-app, animatable like any
      element. Defaults seeded from the score's credit texts.
      Verify: stage shows title/composer from stage_config, not from the
      engraved page; moving/restyling them never re-engraves.

**Exit criteria**: app opens a Dorico MusicXML and displays it paged,
faithful to Phase-0 SVGs, with per-element control proven. **PASSED
2026-07-11.**

## Phase 3 — Time: TempoMap, clocks, transport, first animation

- [ ] **3.1 TempoMap** (core, headless-tested): events, seconds_at/
      beats_at both directions, segment precomputation. Property tests:
      round-trip beats→seconds→beats; monotonicity.
- [ ] **3.2 Clock interface + AudioClock**: load wav/mp3, play/pause/seek;
      AudioClock exposes playhead seconds. Spike Qt playhead query
      precision first (risk 3). Verify: seek + query agree within a frame.
- [ ] **3.3 Animation evaluator** (core): properties, Envelope, Effect,
      element_state(t) — pure. Headless tests: exact expected values at
      chosen t for "appear" (step envelope) including pre-onset, at-onset,
      post-onset.
- [ ] **3.4 Wire it**: transport bar; per-frame tick queries AudioClock →
      TempoMap → element_state → scene update, touching only changing
      elements. Effect: notes at floor opacity, full opacity at onset.
      Verify: play the test score against its recording with a manually
      entered BPM; notes land audibly on time; scrubbing is instant and
      stateless.

**Exit criteria**: real score + real recording + hand-set tempo events
play in sync live; all core logic covered headless.

## Phase 4 — Sync authoring: waveform, tempo lane, taps

- [ ] **4.1 WaveformView**: peak rendering, shared time axis, playhead,
      click-to-seek.
- [ ] **4.2 TempoLaneView**: tempo events as draggable points; add/remove;
      all edits as undoable commands.
- [ ] **4.3 Tap capture**: tap key during playback records
      (beat, timestamp); derive smoothed tempo events per tapped section;
      optional per-region "lock to taps" (dense events). Headless tests on
      synthetic tap data (noisy taps → stable BPM).
- [ ] **4.4 Swing regions**: ratio parameter shifting off-beat
      subdivisions; lane UI; headless tests for onset math at 0.5/0.6/0.667.
- [ ] **4.5 Project save/load + undo stack** across all of the above.

**Exit criteria**: full authoring loop — load score + audio, tap through a
rubato section, adjust, save, reload, everything intact; undo works
everywhere.

## Phase 5 — Reveal effects & styling

- [ ] **5.1 reveal_x** per system (core): CONTINUOUS and STEPPED from
      onset-sorted note positions; headless tests for both modes,
      including simultaneous onsets across staves (step to musical onset).
- [ ] **5.2 Spanner reveal**: clip-rect grow for slurs/hairpins; respects
      RevealMode; system-split segments. Verify visually: stepped slur
      ticks with the notes; continuous slur sweeps.
- [ ] **5.3 StyleRules**: per-part colors, effect assignment, per-element
      override rules; serialized; UI to assign part colors.
- [ ] **5.4 "pop" effect** as a preset (scale envelope around anchor) —
      proving effects-as-data: zero evaluator changes.

**Exit criteria**: a stepped-appearance animation with per-part colors and
growing slurs plays in sync; adding "pop" required only a preset.

## Phase 6 — Export

- [ ] **6.1 FrameClock + offscreen render**: walk t = n/fps, render stage
      to transparent-background frames.
- [ ] **6.2 Encoder**: pipe frames to ffmpeg (alpha-capable format, e.g.
      ProRes 4444 or PNG sequence); mux nothing — video overlay happens in
      the user's editor. Verify: exported overlay lines up with the
      recording in a video editor, start to finish, no drift.

**Exit criteria**: end-to-end — Dorico score in, synced overlay video out.

## Later (explicitly not now)

Continuous-scroll presentation mode; glow (needs perf spike); audio-to-
score auto-alignment provider; custom engraving provider; MIDI input;
richer effect editor; arbitrary-exporter MusicXML robustness; in-app
editing of score-anchored texts (part labels, title, tempo marks) with
the score shifting to fit — ruling 2026-07-11, BACKLOG item 5.
