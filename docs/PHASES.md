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

Build complete 2026-07-11 (146 headless tests green); exit criteria
**PASSED 2026-07-11** (user's sync session against the real recording).
Rulings taken during planning: recording available as wav+mp3; tempo entry via
sidecar text file (`<score>.tempo`, auto-loaded, F5 reloads, `m<n>`
measure syntax); full note ink animates (heads, slashes, stems, flags,
beams, accidentals, articulations, dots, ties/slurs as step-appear) —
rests/clefs/signatures/barlines/staff lines/dynamics/texts stay static.
[AMENDED 2026-07-12, Phase 5 ruling B: rests, whole-bar rests, and
dynamics JOIN the animated ink (dynamics trigger at their attach
point); statics shrink to clefs/signatures/barlines/staff lines/texts.
Ties/slurs moved from step-appear to clip-grow in Phase 5.2.]
Known defect (ruled 2026-07-11, must fix): ledger lines do not dim with
their notes — they fold into the static STAFF_LINES ink. BACKLOG item 6.

- [x] **3.1 TempoMap** (core/timing/tempo_map.py): piecewise-constant
      bpm → piecewise-linear beats⇄seconds, precomputed boundaries,
      bisect+lerp, exactly invertible; seconds_at(0)==0 (audio lead-in
      is the transport `offset`, from the tempo sidecar). Property
      tests: round-trip < 1e-9, monotone both directions, boundary
      exactness, validation. Swing (Phase 4) slots in as a beat-domain
      warp applied before seconds_at; TempoMap unchanged.
- [x] **3.2 Clock + AudioClock**: spike ran FIRST (risk 3 — see
      spikes/NOTES.md Phase 3): QMediaPlayer.position() updates only
      every 100 ms (wav) / 50 ms (mp3) → raw reads unusable; **verdict
      tier 2b**, sliding-mean anchored extrapolation (measured p95
      7.1 ms wav / 1.2 ms mp3, seeks settle < 1 ms — well inside the
      ≤20 ms ideal band). Clock ABC (core/timing/clock.py) is
      now_seconds() only; AudioClock/AudioTransport in ui/audio.py.
- [x] **3.3 Animation evaluator** (core/animation/): Envelope (with
      `initial`, ARCHITECTURE §3 amendment) / Effect / element_state,
      pure; exact-value tests pre-/at-/post-onset (at-onset inclusive).
      TriggerSchedule gates ties on ScoreNote.tie — chain key is
      (part, staff, pitch) WITHOUT the per-measure voice label (an
      m18→19 drum tie crosses a voice relabeling); tied heads inherit
      the chain-start trigger; graces fire at their fractional Verovio
      qstamp (just before the beat); attachments resolve through an
      any-fresh group rule (fixture has no mixed tied chords — pinned;
      rule covered synthetically).
- [x] **3.4 Wire it**: bottom transport bar (Open Audio/Tempo, Reload
      F5, Play/Pause Space, seek slider, time label, Follow page-turn
      toggle); 16 ms PreciseTimer tick only while playing; cursor-diff
      apply touches only crossed triggers (O(log n + changes)); every
      seek does a one-shot full refresh (scrub is stateless — pinned by
      test and by the offscreen smoke run: walk → scrub back ≡ fresh
      state). Measured on the fixture: tick mean 0.08 ms, max 0.54 ms,
      ~0.5 items/tick — flat.

**Exit criteria**: real score + real recording + hand-set tempo events
play in sync live; all core logic covered headless. **PASSED
2026-07-11** — starter `testdata/testscore.tempo` provided; watch/
listen checklist in the Phase 3 plan (also summarized in the session
close-out).

## Phase 4 — Sync authoring: waveform, tempo lane, taps

Build complete 2026-07-11 (220 headless tests green); exit criteria
**PASSED 2026-07-11** (user's authoring sessions: taps/undo/round-trip
first pass; swing + zoom accepted after two re-test fix rounds — swing
became a global numeric ratio on the transport bar, all zooms moved to
the gentle trackpad curve). Rulings taken at plan review:
file opens live outside the undo stack (open score = new doc + cleared
stack; open audio = ref swap, not undoable — rule 8 governs intent
edits, not session binding); BACKLOG 6 fixed first as task 4.0a; tap
anchor = nearest beat under the current map, sequential quarters after.
Build facts: numpy declared explicitly (already a hard music21 dep);
QAudioDecoder spike passed (decode ~0.03 s for the 35 s fixture, no
worker thread needed — spikes/NOTES.md Phase 4); `.scoreanim` = JSON v1,
paths relative to the project file + sha256 (warn, don't block); drag
gestures preview-against-committed and commit ONE command on release.

- [x] **4.0a Ledger lines dim with their notes** (BACKLOG 6): adapter
      emits per-dash LEDGER_LINES elements attributed to noteheads by
      overlap; staff scaffold back to exactly 5 paths everywhere.
- [x] **4.1 WaveformView**: peak rendering (multi-res min/max/rms
      pyramid in core/audio/peaks.py, O(pixels) paint at any zoom,
      progressive fill), shared TimeAxis on AppState, playhead,
      click-to-seek, wheel zoom shared with the lane.
- [x] **4.2 TempoLaneView**: tempo events as draggable points over the
      same axis; add (double-click)/move (drag, snapped)/remove
      (Delete/context menu); every gesture one undoable command;
      last-event removal refused.
- [x] **4.3 Tap capture**: T during playback records (beat, AudioClock
      seconds); Theil–Sen ±2 smoothing + greedy segmentation (steady →
      ONE event, rit → ramp; 199/200 seeds at σ=30 ms); per-session
      "lock to taps" dense anchors (exact to 1e-9); start residual
      reported, never absorbed. Headless tests incl. the spec's two
      cases.
- [x] **4.4 Swing**: per-quarter piecewise-linear warp upstream of
      seconds_at (the Phase 3 seam held; TempoMap untouched); onset math
      tested at 0.5/0.6/0.667. Authoring (ruling 2026-07-11, superseding
      both drag-to-create and the start/end/ratio dialog): v1 swing is
      ONE GLOBAL ratio, a numeric spinbox on the transport bar
      (SetGlobalSwing command → a single region spanning the score;
      0.50 clears it). SwingRegion stays the document model; per-region
      authoring UI deferred to BACKLOG 7.
- [x] **4.5 Project save/load + undo stack**: ProjectDoc + 11 commands +
      UndoStack (core/project/), versioned JSON round-trip incl. RAW tap
      sessions, Save/Save As/Open Project, dirty star, hash-mismatch
      warnings, close prompt.

**Exit criteria**: full authoring loop — load score + audio, tap through a
rubato section, adjust, save, reload, everything intact; undo works
everywhere.

## Phase 5 — Reveal effects & styling

Build complete 2026-07-12 (258 headless tests green); first visual
session PASSED pop/colors/undo/scrub/round-trip but RE-OPENED the reveal
model with four rulings (2026-07-12), rebuilt same day (260 tests):

- **A — a tied group is one event (STEPPED).** Reveal anchors moved from
  notated onsets to the trigger schedule's tie-gated beats; a tied chain
  collapses to one anchor at (chain start, its furthest ink incl. broken
  segments); nothing advances at a tie-stop's notated onset. Edges
  became per-(system, PART) so one part's tie holds only its own
  spanners (per-voice granularity: known limit).
- **B — rests and dynamics animate.** ANIMATED_KINDS += REST/MREST/
  DYNAMIC; a dynamic's onset is its attach point (MEI @tstamp/@startid,
  resolved in the adapter); rests are reveal anchors, dynamics are not.
- **C — sweep deferred.** "Sweep" is a single smooth shared wavefront
  revealing ALL ink — a different computational model, its own design
  round (BACKLOG 8). Continuous mode stays reachable on the new anchors.
- **D — color scope.** TINTED_KINDS = playing ink + spanners; clefs,
  signatures, texts (fixed — they wrongly tinted before), and — ruled —
  rests/dynamics stay black. Animated set ≠ tinted set.

Second visual session (2026-07-12): A/B/D behaviors passed; one further
ruling — **rests are retrospective ink**: a rest appearing ON its beat
reads as an event at silence. Unified rule (user's choice at
clarification): a rest triggers at min(next note in its part/voice,
end of its own bar) — the whole-bar rest degenerately at its barline;
never on its own beat. Reveal anchors follow (the edge never advances
mid-silence). Exit criteria pending re-verification of the rest feel. Rulings at plan review (2026-07-11):
hairpins JOIN the grow set (5.2 task text supersedes the Phase 3 census
default; dynamic letters stay static); spanners keep a dimmed
floor-opacity ghost under the growing clipped copy; grow REPLACES
step-appear for spanners — RevealMode (global, on the doc, 'Sweep'
toggle) is the only knob. Test material: user-provided Dorico export
`testdata/broken_hairpin_and_slur_test.*` (hairpin broken m4→m5,
slur+ties broken m8→m9, companion wav). Build facts: Verovio renders a
broken spanner as an id-bearing <g> plus one ID-LESS <g> per
continuation system (previously silently absorbed into the static
system element — testscore itself has 7 such broken ties); hairpins are
tstamp/tstamp2+@staff addressed, no startid; PROJECT_VERSION bumped to
2 (v1 part_colors folds into part color rules on load).

- [x] **5.1 reveal_x** per system (core): CONTINUOUS and STEPPED from
      onset-sorted note positions; headless tests for both modes,
      including simultaneous onsets across staves (step to musical onset).
      Anchors are NOTATED onsets (identity.onset — not tie-gated trigger
      beats); lead/end sentinels make CONTINUOUS continuous through
      system breaks; swing applies via the same resolve_seconds seam as
      triggers. RenderedElement gained `system` (adapter-stamped).
- [x] **5.2 Spanner reveal**: clip-rect grow for slurs/ties/hairpins via
      RevealPathItem (paint-time clip, per-child clamp, no re-indexing);
      per-segment elements (`<source-id>:seg<k>`) so system-split
      spanners reveal per segment, later segments at reveal 0 with no
      page logic. Verified: clip statelessness tests + offscreen pixel
      check (ghost < half-grown < full).
- [x] **5.3 StyleRules**: ONE styling system — per-part color+effect
      rules, per-element overrides, reveal mode; element>part>default
      field-wise; effect names fail soft to 'appear'. SetPartColor
      retargeted; SetPartEffect/SetElementStyle/SetRevealMode added.
      Applier: per-element effects, opacity+scale property map (scale
      restricted to anchored kinds), transition window with expiry
      settle, refresh seeds mid-transition seeks. Parts menu: per-part
      color swatches + Custom… + No Color, effect radios enumerated
      from the preset registry.
- [x] **5.4 "pop" effect** as a preset (scale envelope around anchor) —
      proving effects-as-data: zero evaluator changes. The commit diff
      is the proof: presets.py + its test only (`git show --stat`).

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
