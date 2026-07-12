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
[AMENDED 2026-07-12, Phase 5 rulings: rests, whole-bar rests, and
dynamics JOIN the animated ink — dynamics trigger at their attach
point, rests when their silence resolves (min(next note, own barline),
never on the silent beat); statics shrink to clefs/signatures/barlines/
staff lines/texts. Ties/slurs moved from step-appear to clip-grow in
Phase 5.2. The old taxonomy stated here no longer applies; see
ARCHITECTURE.md §3 "Animated-ink taxonomy".]
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

## Phase 5 — Reveal effects & styling — ✅ COMPLETE 2026-07-12

Built and closed in one day across three rounds (261 headless tests
green); **exit criteria PASSED 2026-07-12** over two visual sessions
(first: pop/colors/undo/scrub/round-trip; second: the revised reveal
model incl. rest feel — "silence staying visually empty until it
resolves is exactly right"). This phase superseded more of the original
design than any before it; ARCHITECTURE.md §3 now records the model AS
BUILT.

Rulings at plan review (2026-07-11): hairpins JOIN the grow set (the
5.2 task text supersedes the Phase 3 census default; dynamic letters
were to stay static — later superseded by ruling B); spanners keep a
dimmed floor-opacity ghost under the growing clipped copy; grow
REPLACES step-appear for spanners — RevealMode (global, doc-stored,
'Sweep' transport toggle) is the only knob.

Rulings at the first visual session (2026-07-12), which re-opened the
reveal model:

- **A — a tied group is one event (stepped).** Reveal anchors moved
  from notated onsets to the schedule's tie-gated beats; a tied chain
  collapses to one anchor at (chain start, its furthest ink incl.
  broken segments); nothing advances at a tie-stop's notated onset.
  Edges became per-(system, PART) so one part's tie holds only its own
  spanners (per-voice granularity: accepted limit, BACKLOG 10).
- **B — rests and dynamics animate** (amends the Phase 3 animated-ink
  ruling above). A dynamic's onset is its attach point (MEI
  @tstamp/@startid, adapter-resolved); rests are reveal anchors,
  dynamics are not.
- **C — sweep deferred.** "Sweep means sweep": one smooth shared
  wavefront revealing ALL ink — a different computational model, its
  own design round (BACKLOG 8; scaffold/barline sweep wanted, not
  scheduled). The Sweep toggle meanwhile drives a placeholder
  continuous lerp over the stepped anchors.
- **D — color scope.** TINTED_KINDS = playing ink + spanners; clefs,
  signatures, texts (fixed — they wrongly tinted before) and — ruled —
  rests/dynamics stay black. Animated set ≠ tinted set.

Ruling at the second visual session (2026-07-12): **rests are
retrospective ink** — a rest appearing ON its beat reads as an event at
silence. Unified rule (user's clarification choice): a rest triggers at
min(next note's trigger in its part/voice scope, end of its own bar),
never on its own beat; the whole-bar rest degenerately at its barline.
Reveal anchors follow, so the edge never advances mid-silence.

Test material: user-provided Dorico export
`testdata/broken_hairpin_and_slur_test.*` (hairpin broken m4→m5,
slur+ties broken m8→m9, companion wav). Build facts: Verovio renders a
broken spanner as an id-bearing `<g>` plus one ID-LESS `<g>` per
continuation system (previously silently absorbed into the static
system element — testscore itself has 7 such broken ties); hairpins AND
dynamics are tstamp+@staff addressed (no startid); PROJECT_VERSION
bumped to 2 (v1 part_colors folds into part color rules on load; a v1
build refuses v2 rather than silently dropping styling).

- [x] **5.1 reveal_x** (core): per-(system, part) tracks from the
      schedule's tie-gated triggers (as revised by rulings A/B and the
      rest rule); STEPPED steps at part events, CONTINUOUS is the
      placeholder lerp; interlocking per-part lead/end sentinels; swing
      via the same resolve_seconds seam as triggers. RenderedElement
      gained `system` (adapter-stamped; slashes via staff_geo).
- [x] **5.2 Spanner reveal**: clip-rect grow for slurs/ties/hairpins via
      RevealPathItem (paint-time clip, per-child clamp, no re-indexing)
      over a floor-opacity ghost; per-segment elements
      (`<source-id>:seg<k>`) so system-split spanners reveal per
      segment, later segments at reveal 0 with no page logic. Verified:
      clip statelessness tests + offscreen pixel check.
- [x] **5.3 StyleRules**: ONE styling system — per-part color+effect
      rules, per-element overrides, reveal mode; element>part>default
      field-wise; effect names fail soft to 'appear'. SetPartColor
      retargeted; SetPartEffect/SetElementStyle/SetRevealMode added;
      project schema v2. Applier: per-element effects, opacity+scale
      property map (scale restricted to anchored kinds), transition
      window with expiry settle, refresh seeds mid-transition seeks.
      Parts menu: per-part color swatches + Custom… + No Color, effect
      radios enumerated from the preset registry.
- [x] **5.4 "pop" effect** as a preset (scale envelope around anchor) —
      proving effects-as-data: zero evaluator changes. The commit diff
      is the proof: presets.py + its test only (`git show --stat
      c5268ea`).

**Exit criteria**: a stepped-appearance animation with per-part colors and
growing slurs plays in sync; adding "pop" required only a preset.
**PASSED 2026-07-12.**

## Phase 6 — Export — ✅ COMPLETE 2026-07-12

Built and closed in one day (285 headless tests green); **exit criteria
PASSED 2026-07-12** (user's composite check in his video editor: "ink
lands on the audible onsets, no growing error, page cuts match live
follow" — ghost legibility over footage accepted as-is). Rulings at
plan review (2026-07-12): **R1** export is always transparent-background,
the floor-opacity ghost ink exports as-is (no "opaque paper" option —
judged fine in the composite); **R2** page turns mirror live follow
mode exactly — hard cut on the frame where `current_page()` changes;
**R3** export settings are session memory only, nothing enters the
project document (no schema change). Format ruling: ProRes 4444 .mov is
the default (one file, 10-bit, straight alpha, every NLE), PNG sequence
the no-ffmpeg fallback.

Post-composite polish (same day, ruled at close): dialog shows WIDTH
locked to height (🔗, aspect is the page's own); the export range is
entered in MEASURES (`measure_span_seconds` converts through the same
swing-aware resolve_seconds seam as triggers — a pure input conversion,
frame math untouched, onset-frame test still green); the dialog closes
itself on success (cancel/failure behavior unchanged).

The sync contract, pinned by test: exported video t=0 == recording t=0;
frame n samples t_audio = start + n/fps (frame start), t_score =
t_audio − offset — the exact mirror of the live tick's `_score_time`
(ui/playback.py). Frame count = ceil((end−start)·fps − ε), so the
overlay always covers the full audio span. The export walk uses the
SAME applier methods as live playback (apply_at for n+1, refresh
otherwise — the tick/seek split) over a private ScoreScenes+applier
built from retained `AnimationInputs`; `render/animate.py`,
`ui/playback.py`, and all of `core/animation/` are untouched.

- [x] **6.1 FrameClock + offscreen render**: `FrameClock` (core/timing/
      clock.py, t = n/fps, pure division); `FrameRenderer`
      (render/export.py) renders the current page to transparent
      `QImage`s (ARGB32_Premultiplied, paper rect hidden via the new
      `ScoreScenes.page_rects`), page aspect preserved at a user height,
      dimensions floored to even. Pinned headless against the REAL
      sidecar (offset 0.77): onset frames at start/middle/end within
      ±1 frame (assertion separates uniform error ⇒ offset bug from
      spread ⇒ drift), frame-walk ≡ fresh refresh, byte-identical
      determinism where one renderer ticks and the other seeks, page
      turn on the exact live-follow frame, corner alpha 0 / ghost ≈
      0.3 / lit ≥ 0.78 pixels (tests/test_export.py).
- [x] **6.2 Encoder**: `ProResFfmpegSink` streams RGBA rawvideo to
      ffmpeg stdin (no disk intermediate) → ProRes 4444 .mov
      (prores_ks, yuva444p10le in, 12-bit out per ffmpeg 8's decoder);
      `PngSequenceSink` (pure Qt) is the no-ffmpeg fallback; ffmpeg
      found at runtime (shutil.which), missing → ProRes disabled with a
      brew hint. One convertToFormat(RGBA8888) per frame un-premultiplies
      to straight alpha; bytesPerLine asserted. Cancel/error → abort →
      partial output deleted (pinned incl. an ffprobe smoke).
      **Export Video… dialog** (ui/export_dialog.py, Ctrl+E): fps
      24–60, format, size (height with width locked to the page
      aspect), whole-recording or measure-span range, progress +
      ETA + cancel, auto-close on success; chunked 40 ms batches
      re-armed by QTimer.singleShot(0, …) on the GUI thread (no
      QThread, matching PeakExtractor's idiom). Measured on the
      fixture: 2074 frames at 1526×2160 in 57.5 s (~36 frames/s),
      687 MB.
      Build finds: a QDoubleSpinBox attribute named `_start` shadowed
      the `_start()` slot (renamed `_start_spin`); retaining the
      wrapper `scene.addRect` returns bus-errors shiboken teardown once
      the scene deletes the C++ item first — the paper rect is now
      Python-constructed + addItem, like every other item.

**Exit criteria**: end-to-end — Dorico score in, synced overlay video
out, verified against the recording in a video editor. **PASSED
2026-07-12** (`~/Movies/testscore-overlay.mov` composited over
`testscore.wav`: first note, rehearsal A, final note all within a
frame; no drift; page cuts match live follow).

## Phase 7 — Presentation & reveal control — ✅ COMPLETE 2026-07-12

Built and closed in one day (dd4a021, 308 headless tests green); **exit
criteria PASSED 2026-07-12** (user's review of the diff plus the
scripted exit-checklist run and sample 1920×1080 export frames: "this
works"). Scoped 2026-07-12 (v2 scoping session; verified facts in
`spikes/NOTES.md` "v2 scoping probes"). Rulings at scoping:

- **One schema v3** carries EVERY planned document field — floor
  opacity, presentation mode, staff groups (Phase 8), text overrides
  (Phase 9) — designed once, even where a field lands before its
  feature. No per-phase schema bumps.
- **Floor = 0 scope**: static scaffold (staff lines, clefs, signatures,
  barlines, texts) STAYS at full opacity — notes appear onto a visible
  staff, never a blank page filling in. The animated-ink taxonomy is
  unchanged; sweep-covers-scaffold remains a separate deferred item
  (BACKLOG 8).
- **System-at-a-time is presentation-only** (verified at scoping): every
  element carries a score-wide system index, reveal tracks are already
  per (system, part) — the mode consumes the existing Layout; no
  re-engrave, no engraving change.

- [x] **7.1 Schema v3**: PROJECT_VERSION 3, ONE bump with every planned
      field — `style.floor_opacity` (StyleRules), `stage.mode`
      (PresentationMode enum, stage_config.py), top-level
      `staff_groups` (StaffGroup: parts/symbol/join_barlines) and
      `text_overrides` (PartTextOverride: name/abbreviation), the
      latter two dormant until Phases 8/9. Reader accepts {1, 2, 3} —
      v1/v2 files simply lack the keys and default per-field (no
      migration code); writer emits 3; gate stays strict (version 4
      refused). Pinned: round-trips incl. floor 0.0 (falsy — no `or`
      defaulting), v2-loads-with-defaults, unknown-mode ValueError
      (tests/test_project_serialize.py).
- [x] **7.2 User-settable floor opacity incl. 0**: `build_presets(floor)`
      — the registry as a function of the floor, still pure data (rule
      6; the evaluator untouched). As built, the applier resolves
      against `{**PRESETS, **build_presets(floor)}` so registry entries
      beyond the built-ins still resolve (their own envelopes
      untouched). Floor rides StyleRules, so a change arrives through
      the EXISTING set_style re-resolve+refresh — zero new applier API,
      live and export identical by construction (FrameRenderer already
      takes StyleRules; both ghost_opacity passers now read
      `style.floor_opacity`, the constant import is gone). ScoreScenes
      tracks ghost children (`_ghost_items`) + `set_ghost_opacity`;
      `SetFloorOpacity` command (rejects outside [0,1]/non-finite) + a
      "floor" transport spinbox synced like swing. Verified: floor 0 →
      un-triggered animated ink at 0, scaffold untouched at 1.0
      (scaffold never enters the trigger schedule — ruled, not a bug),
      clip-reveal still grows over the invisible ghost.
- [x] **7.3 System framing (core, pure)**: `core/engraving/systems.py`
      — `system_bands(layout)` (per-system union bbox widened to full
      page width; raises on a page-spanning system) and `centered_fit`
      (scale-to-fit + center both axes, shared by export and tests).
      `Trigger.system` stamped by the schedule with the exact min-fresh
      rule as page (defaulted last field, synthetic construction
      survives); `current_system()` on the applier — the
      `current_page()` idiom on the same bisect cursor. Pinned: fixture
      bands systems 1–5 on pages 1/2/2/3/3, every element bbox
      contained, current_system walk matches the stamps
      (tests/test_systems.py).
- [x] **7.4 System-at-a-time stage mode**: `show_system_band` = setScene
      + fitInView(band) — a hard cut, exactly the page-flip mechanics.
      Masking as built: a `drawForeground` override fills the exposed
      scene area outside the band with the letterbox color — VIEW-level,
      so export scenes structurally cannot see it, and it holds at any
      aspect/zoom/resize. `SetPresentationMode` command + a "Systems"
      transport toggle (synced blockSignals like Sweep); follow emits
      page AND system, the window routes by `doc.stage.mode`; prev/next
      step systems in system mode; page flip implied by the band's
      page. Paged unchanged and default. Pinned: neighbour-system
      pixels read letterbox at 1920×400 AND 400×1000 while the framed
      band does not; clear_band restores paged pixels
      (tests/test_stage_system_mode.py).
- [x] **7.5 System-mode export**: `ExportSpec.mode` +
      `ExportSpec.width` (canvas; both dims independently even-floored,
      no aspect coupling); the dialog shows W×H spinboxes (default
      1920×1080) in system mode, session memory only (R3 — mode-keyed:
      canvas_w/canvas_h alongside paged height, the other mode's
      settings pass through untouched). The dialog reads the mode from
      the LIVE doc at open — `AnimationInputs.stage` is a load-time
      snapshot and goes stale after a mode command. render_frame:
      paged path verbatim behind a guard; system branch composites
      `scene.render(source=band, target=centered_fit)` under an
      explicit `setClipRect` (the bleed guarantee). Pinned: cut frames
      match the live walk for all four system boundaries, sampled
      pixels outside the fit rect fully transparent at wide and tall
      canvases, paged spec builds no band machinery, and every
      pre-existing Phase 6 test passes unmodified — including
      byte-identical walks (tests/test_export.py).

**Exit criteria**: floor 0 plays and exports with unrevealed ink
invisible on a visible scaffold; system mode shows and exports one
system at a time, chronologically, centered, hard cuts in sync with
live follow. **PASSED 2026-07-12** (scripted exit run on the real
MainWindow offscreen: floor 0.3/0/1 with undo restoring doc and scene;
system mode framed sys 1/5 → step → implied page flip → undo clears
the mask; v2 project loads with defaults and resaves as v3, v4
refused; 1920×1080 system-mode export with the sys-2 cut at the exact
live-follow frame and transparent corners — sample frames reviewed by
the user).

## Phase 8 — Grouping: brackets & joined barlines

Ruling 2026-07-12 (v2 scoping): brackets go through the ENGRAVING
INPUTS — `<part-group>` injection at the prep seam — not render-side
synthesis. Decisive fact: baseline barlines are per-staff segments, and
Verovio's group-barline connectors split around obstacles; render-side
joining would reimplement engraving collision avoidance. Verified at
scoping (scratchpad probe, to be re-done properly in `spikes/` as task
8.1): injection renders a `grpSym` bracket and joins barlines through
the group; engrave+decompose costs 0.23 s. **Closes BACKLOG 1** (sax
bracket, "before first production use"). The document stores the
GROUPINGS (user intent); bracket geometry is re-derived — rule 5 holds.

- [ ] **8.1 Part-group spike, properly** (re-do of the scoping probe,
      house style, kept in `spikes/`): injection → grpSym + group
      barlines on the fixture; record segment/obstacle behavior and
      bracket left-margin geometry shift in `spikes/NOTES.md`.
- [ ] **8.2 Adapter grpSym support**: map the class to a static kind
      with sensible identity (unknown SVG classes raise ValueError
      today — without this, grouped scores refuse to load). Verify:
      grouped fixture loads headless; grpSym elements are static (not
      animated, not tinted).
- [ ] **8.3 staff_groups → prep injection**: doc field (ordered groups
      of contiguous parts + symbol + joined-barlines flag; v3 field
      from 7.1) applied as `<part-group>` elements at the prep seam
      (musicxml_prep, alongside transpose neutralization). **Pin ID
      stability**: ElementIds are minted from musical identity — assert
      byte-equal ids with and without grouping (also discharges the
      BACKLOG 5 "verify" note). Verify: headless.
- [ ] **8.4 Command + UI + reload**: SetStaffGroups undoable; grouping
      dialog (parts in score order, symbol, barline flag); group change
      → re-engrave + scene rebuild (same path as project open; 0.23 s
      measured); layout overrides re-apply as deltas on the shifted
      base (accepted staleness — the bracket consumes left-margin
      width). Verify: define the sax group in-app, bracket + joined
      barlines appear, undo removes them, save/reload round-trips.

**Exit criteria**: the sax section bracket and its joined barlines
render on the fixture, defined interactively in-app, undoable,
ElementIds stable across the re-engrave — BACKLOG 1 closed.

## Phase 9 — Text editing

Ruling 2026-07-12 (v2 scoping, revising BACKLOG 5's framing): the split
is by TEXT CLASS, not by cost — re-engrave is cheap (0.23 s), so the
question is which texts NEED reflow. Title/composer (already stage
texts) and tempo marks (float in empty space above the staff) edit as
OVERLAY, never re-engraving. Part labels (fixed left column engraved
from the longest name — overlay edits collide with the staff) take the
prep-seam re-engrave path, riding Phase 8's infrastructure. **Depends
on Phase 8.**

- [ ] **9.1 Stage text editing**: edit content/position/style of stage
      texts (title/composer/lyricist) via undoable commands + minimal
      UI; re-run band-fit scaling on edit. Full stage click-to-select
      stays BACKLOG 9. Verify: edit the title, moves/restyles never
      re-engrave, round-trips, undo works.
- [ ] **9.2 Tempo-mark overlay**: hidden layout-override on the
      engraved TEXT element + a replacement stage text seeded at its
      engraved position/size; edits never re-engrave. Verify: edited
      tempo text shows in place, engraved original hidden, round-trip +
      undo.
- [ ] **9.3 Part-label edits via the prep seam**: part-name/abbreviation
      overrides in the doc (v3 text_overrides field) applied to the
      part-list at prep → re-engrave; the label column re-derives so
      the score shifts to fit (a re-engrave with changed inputs is not
      window reflow — rule 7 holds); abbreviated labels on later
      systems update from the same override. ID stability pinned as in
      8.3. Verify: rename a part in-app → all systems' labels update,
      score shifts, undo restores, ids stable.

**Exit criteria**: title and tempo-mark edits are pure overlay; a part
rename re-engraves with the score shifting to fit; everything undoable
and round-tripping — BACKLOG 5 resolved as split.

## Later (explicitly not now)

Continuous-scroll presentation mode; glow (needs perf spike); audio-to-
score auto-alignment provider; custom engraving provider; MIDI input;
richer effect editor; arbitrary-exporter MusicXML robustness.
(In-app score-text editing graduated to Phase 9; brackets/grouping to
Phase 8 — 2026-07-12.)
