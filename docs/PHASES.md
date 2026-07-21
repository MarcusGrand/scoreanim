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

## Phase 8 — Grouping: brackets & joined barlines — ✅ COMPLETE 2026-07-12

Ruling 2026-07-12 (v2 scoping): brackets go through the ENGRAVING
INPUTS — `<part-group>` injection at the prep seam — not render-side
synthesis. Decisive fact: baseline barlines are per-staff segments, and
Verovio's group-barline connectors split around obstacles; render-side
joining would reimplement engraving collision avoidance. **Closes
BACKLOG 1** (sax bracket, "before first production use"). The document
stores the GROUPINGS (user intent); bracket geometry is re-derived —
rule 5 holds.

Build complete 2026-07-12 (330 headless tests green; 25/25 scripted
exit checks on the real MainWindow offscreen). Rulings at plan review
(2026-07-12): commands are the **Add/Edit/RemoveStaffGroup triad**
(supersedes this plan's earlier "SetStaffGroups" wording); the grouping
dialog **applies per action** (each Add/Edit/Remove executes
immediately — one undo step each, live re-engrave behind the open
dialog, Close-only); the symbol combo offers **all four** MusicXML
symbols (bracket/brace/line/square — spike-verified: all four emit the
same single new SVG class). Spike facts (spikes/NOTES.md "Phase 8"):
grpSym is the ONLY new class, id-bearing, one per system per group, no
MEI staffGrp cross-ref; connector paths fold into the measure's
existing id-bearing barLine group (obstacle-split reproduced), so the
decomposer needed NO connector handling; staff-lines min-x is unchanged
by the bracket on the fixture (it fits inside the label margin — no
override-staleness exposure at all).

- [x] **8.1 Part-group spike, properly** (`spikes/part_group.py`):
      injection → grpSym + group barlines on the fixture, all four
      symbols; segment/obstacle behavior, class census, and margin
      geometry recorded in `spikes/NOTES.md`.
- [x] **8.2 Adapter grpSym support**: `ElementKind.GROUP_SYMBOL`
      (static by construction — every animation/tint/reveal set is an
      allowlist), `_KIND_BY_CLASS["grpSym"]`, and a dedicated
      `_identity_for` branch minting part-span-keyed ids
      (`score:sys{n}:grpsym:P1-P2` — the k-th grpSym in a system is the
      k-th group in first-part score order; ordinal fallback for
      native/foreign part-groups). `groups` threaded through
      `EngravingProvider.load` → `load_detailed` → `prepare`. Verified:
      tests/test_adapter_groups.py (loads losslessly, 5 static grpSyms
      with system stamps, deterministic ids, joined barlines fill the
      P1–P2 gap while lower gaps stay empty).
- [x] **8.3 staff_groups → prep injection**: `PartGroupSpec` (neutral
      prep-seam twin of StaffGroup) + `_inject_part_groups` in
      musicxml_prep, alongside transpose neutralization; numbering
      continues past any existing part-groups; ValueError on
      unknown/non-contiguous parts (defense in depth behind the
      commands). **ID stability pinned**:
      test_element_ids_stable_under_grouping asserts the grouped id set
      equals baseline + grpSym ids exactly (discharges the BACKLOG 5
      "verify" note — and the spike showed every VEROVIO id re-rolls on
      injection even with a fixed seed, which is precisely why ours
      must not). Verify: headless, tests/test_musicxml_prep.py.
- [x] **8.4 Commands + UI + reload**: Add/Edit/RemoveStaffGroup with
      `part_order` as runtime data on the command (the
      SetGlobalSwing.end_beat precedent — the doc stores intent only);
      validation in apply (contiguity, overlap ⇒ nesting excluded in
      v1, symbol vocabulary), normalized by first-part score order so
      injection order is deterministic. Staff Groups… dialog atop the
      Parts menu (manager list + From/To part combos — contiguity by
      construction). Reload: `_engrave_and_wire` extracted from
      `_load_score`; `_applied_groups` diff-guard at the TOP of
      `_on_document_changed` re-engraves on execute, undo, AND redo
      before the same pass re-pushes timing/tints/floor; page, system,
      and zoom preserved (no view.fit); open_project engraves grouped
      exactly once (guard sees equal groups after reset_document);
      non-group commands never re-engrave (pinned in the exit run).
      Cost on screen: ~0.6 s GUI-thread stall per group change (0.23 s
      engrave + scene rebuild), status bar re-prints the timings.

**Exit criteria**: the sax section bracket and its joined barlines
render on the fixture, defined interactively in-app, undoable,
ElementIds stable across the re-engrave — BACKLOG 1 closed. **PASSED
2026-07-12** (user's interactive exit run on the build commit 7db56e0:
accepted).

## Phase 9 — Text editing — ✅ COMPLETE 2026-07-13

Ruling 2026-07-12 (v2 scoping, revising BACKLOG 5's framing): the split
is by TEXT CLASS, not by cost — re-engrave is cheap (0.23 s), so the
question is which texts NEED reflow. Title/composer (already stage
texts) and tempo marks (float in empty space above the staff) edit as
OVERLAY, never re-engraving. Part labels (fixed left column engraved
from the longest name — overlay edits collide with the staff) take the
prep-seam re-engrave path, riding Phase 8's infrastructure. **Depends
on Phase 8.**

Build complete 2026-07-12 (368 headless tests green; 12/17/16 scripted
exit checks per task on the real MainWindow offscreen). Rulings at plan
review (2026-07-12): tempo marks identified by threading the SVG class
onto RenderedElement as `text_class` — ids untouched (a finer
ElementKind would re-roll the kind tag inside every text id); UI is
TWO dialogs (Edit → Texts… for stage texts + tempo marks; Parts → Part
Names… beside Staff Groups…, since it re-engraves), per-action apply,
Close-only; band-fit on edit re-fits the WHOLE header block in-command
(band as runtime data, one undo step), DOWN-ONLY — the natural-1.0
layout isn't stored (rule 5), so nothing scales back up.

- [x] **9.1 Stage text editing**: edit content/position/style of stage
      texts (title/composer/lyricist) via undoable commands + minimal
      UI; re-run band-fit scaling on edit. Full stage click-to-select
      stays BACKLOG 9. Verify: edit the title, moves/restyles never
      re-engrave, round-trips, undo works.
      As built (2026-07-12): ONE command, `EditStageText(element_id,
      replacement, band)` — `band` is runtime data (the part_order
      idiom: page_content_top on the current layout, supplied by the
      window). Its apply re-fits the WHOLE header block via the shared
      `fit_texts` (extracted from the seed; _lay_out is linear in
      scale, so the affine refit is the seed's fit exactly). Refit is
      DOWN-ONLY by ruling — the natural-1.0 layout isn't stored (rule
      5), so nothing scales back up; sizes are directly editable.
      Overlay texts (stage:overlay:*, 9.2) and pages 2+ are excluded
      via `is_header_text`. Render: `ScoreScenes.set_stage_texts`
      swaps just the stage-text layer; `_sync_stage` diffs
      `_applied_stage_texts` AND refreshes `AnimationInputs.stage`
      (the Phase 7 staleness gotcha — export follows edits with no
      FrameRenderer change). UI: Edit → Texts… manager (per-action
      apply, Close-only, staff-groups idiom). Scripted exit check
      12/12 on the offscreen MainWindow: live update with the SAME
      ScoreScenes + engraved item objects (no re-engrave), sibling
      rescale in one undo step, save/reload round-trip.
- [x] **9.2 Tempo-mark overlay**: hidden layout-override on the
      engraved TEXT element + a replacement stage text seeded at its
      engraved position/size; edits never re-engrave. Verify: edited
      tempo text shows in place, engraved original hidden, round-trip +
      undo.
      As built (2026-07-12): tempo marks identified by a new
      `RenderedElement.text_class` presentation field (the engraved SVG
      class: tempo/reh/dir/label/labelAbbr/pgHead/pgFoot/mNum) —
      ElementIdentity and minted ids UNTOUCHED by ruling (a finer kind
      would re-roll every text id). The fixture's one tempo mark is
      `P1:m1:s1:v0:text:0` (it carries @staff, so it minted
      part-scoped). `AddTempoOverlay` = hide + replace in ONE undo
      step (first consumer of LayoutOverride.hidden; dx/dy still
      unconsumed); `RemoveTempoOverlay` restores and drops the entry
      when back at default (sparse-doc idiom); editing an existing
      overlay is plain EditStageText on `stage:overlay:<engraved-id>`
      (excluded from the header refit). Seeding collapses Verovio's
      doubled metronome codepoint ACROSS run boundaries (BACKLOG 3's
      tofu lives in the 405px text run) and maps SMuFL→text ("Swing
      ♩ = 120"); fidelity caveat: the replacement renders in the stage
      serif, not Bravura. Render: ScoreScenes.set_element_hidden +
      _sync_hidden diff (undo/redo ride the same pass); export:
      FrameRenderer takes doc.layout_overrides via
      apply_hidden_overrides, passed from the live doc at dialog open
      (the 7.5 mode precedent). Scripted exit check 17/17 offscreen,
      including an export frame with the overlay.
- [x] **9.3 Part-label edits via the prep seam**: part-name/abbreviation
      overrides in the doc (v3 text_overrides field) applied to the
      part-list at prep → re-engrave; the label column re-derives so
      the score shifts to fit (a re-engrave with changed inputs is not
      window reflow — rule 7 holds); abbreviated labels on later
      systems update from the same override. ID stability pinned as in
      8.3. Verify: rename a part in-app → all systems' labels update,
      score shifts, undo restores, ids stable.
      As built (2026-07-12): spike first (spikes/part_label.py, NOTES
      "Phase 9") — Verovio reads the -display twins and IGNORES the
      plain elements, so `_apply_text_overrides` writes BOTH (plain
      because `_parts` reads it); non-blank overrides clear
      print-object="no" (it suppresses even non-empty text); "" is an
      explicit no-label. `PartTextSpec` is the neutral prep-seam twin
      of PartTextOverride (the PartGroupSpec precedent); overrides
      apply BEFORE `_parts`, so PartInfo (which gained `abbreviation`)
      carries effective values and identities/menus update free —
      part_id never changes, so nothing else moves. Threaded as a
      separate `texts` arg on load/load_detailed (params serialize in
      the doc — Phase 8 reasoning verbatim). ID pin:
      tests/test_adapter_part_texts.py::
      test_element_ids_stable_under_part_rename (rename = IDENTICAL id
      set; a FIRST P1/P2 abbreviation appends `score:p{n}:text:{seq}`
      ids — no shift on the fixture, spike Q3 — accepted limit, labels
      are never animation targets). One `SetPartText` command
      (wholesale entry, None+None clears, known_parts runtime data);
      re-engrave guard extended to diff `_applied_text_overrides`;
      Parts → Part Names… dialog takes a parts PROVIDER (each rename
      refreshes effective names). Scripted exit check 16/16 offscreen:
      all-system label update, staff min-x shift, page preserved, one
      undo, and an earlier tempo overlay + part tint SURVIVING the
      re-engrave.

**Exit criteria**: title and tempo-mark edits are pure overlay; a part
rename re-engraves with the score shifting to fit; everything undoable
and round-tripping — BACKLOG 5 resolved as split. **PASSED 2026-07-13**
(user's interactive run on the build commit edb2d79: accepted).

## Phase 10 — Robustness: multi-staff parts & decomposer coverage

Build complete 2026-07-13 (387 headless tests green; 20/20 scripted
exit checks on the real MainWindow offscreen; review artifact with
rendered pages delivered). Rulings at plan review (2026-07-13):
**(a)** `systemDivider` → its own `ElementKind.SYSTEM_DIVIDER`, static
by construction; **(b)** ties Verovio drops → flag-and-continue as
`LoadWarning`s, never silent, never fatal; **(c)** a multi-staff part
is ONE PartId entry everywhere (colors, groups, reveal) — no
schema/UI ripple.

The design round CORRECTED three of the recorded triage mechanisms
(verified against the real files; frozen in the 10.0 spike): the m12
ledger dash belongs to a displaced two-voice REST, not cross-staff
notation; tie continuation ink is drawn ONLY in a tie's END system
(the old start<n<=end predicate over-counted pass-through ties), plus
6 ties Verovio drops entirely (empty <g>s); and the systemDivider root
cause is Verovio's `condense:"auto"` default silently condensing the
layout (hiding empty staves!) at 2+ staff groups — fixed by pinning
`condense:"encoded"`, a rule-7-reinforcing fixed adapter option (the
transposeToSoundingPitch shape), 0/1-group renders byte-identical.

Both defects are ONE class of bug (verified 2026-07-13, triage in
`spikes/NOTES.md` "Phase 10"): the adapter was built against two
fixtures that never exercised multi-staff parts, system dividers, or
several notation classes, so decomposer whitelists and attribution
passes assume things `testdata/video_test.musicxml` violates. NOT a
grouping-logic bug and NOT a text-editing regression — a coverage gap.
This phase makes the loader robust and adds `video_test.musicxml` to
the permanent fixtures. Keep changes surgical; the load-bearing walls
(rules 1–10) hold unchanged.

Root causes established (reproduced against the real files):

- **Multi-bracket (BACKLOG 1 follow-up).** Command layer, dialog, and
  `_inject_part_groups` are all correct for N groups (two disjoint
  groups validate and inject cleanly). When a system carries *two*
  groups Verovio draws a **`systemDivider`** glyph; the decomposer
  whitelist lacks that class, so the "unknown SVG class with drawable
  content" guard raises. One group never draws a divider — which is
  why one always worked. A decomposer-coverage fix, task 10.4.
- **`video_test.musicxml` won't load.** One structural novelty cascades:
  the **Piano is a multi-staff part** (`<staves>2</staves>` — one
  `<score-part>`, two staves; neither prior fixture had one). It yields,
  in order: `build_score_model` raises `music21 sees 8 parts, prep sees
  7` (music21 splits the grand staff, prep counts score-parts);
  `_attribute_ledger_dashes` raises (staff-2 dash matches no notehead);
  `_attribute_spanner_segments` / `_build_elements` raise on grand-staff
  tie continuations (Verovio also warns "5 ties left open / start does
  not occur before end"). Fixed at the root by 10.1, with 10.2/10.3
  as the fall-out.
- **New but non-blocking.** `bracketSpan` and `mSpace` appear as
  NON-drawable classes (don't raise today; add to the container/ignore
  set so a future drawable one never does — 10.4). New notation
  (trills/`wavy-line`, fermatas, ornaments, `ppp`, `wedge` hairpins,
  chord-symbol bass notes) maps to classes already whitelisted — it
  renders; 10.5 verifies it visually.

Rulings to confirm at plan review, BEFORE building (flag-and-stop, do
not guess): (a) `systemDivider` — its own `ElementKind.SYSTEM_DIVIDER`
(static) or fold into `OTHER`; (b) the ties Verovio genuinely drops in
this export — flag-and-continue vs. investigate the export; (c)
multi-staff parts — one part color/group entry, or per-staff.

- [x] **10.0 Triage spike** (`spikes/video_test_triage.py`, kept):
      freeze the enumeration — unknown-SVG-class census, part/staff
      structure, tie warnings — that established the root causes; write
      "which features the prior two fixtures never exercised" into
      `spikes/NOTES.md`. Verify: the script reproduces exactly the four
      failure points above, in order.
      As built (2026-07-13): six sections — A part/staff structure
      (pins the music21 contract: a multi-staff part splits into
      adjacent `PartStaff`s with ids `'<score-part-id>-Staff<k>'`, the
      ONLY parts whose id survives), B SVG-class census, C ledger
      census (the failing dash is REST ink), D tie-continuation table
      (end-system rule closes every count; 6 ink-less MEI ties), E
      condense demonstration (auto condenses at 2 groups; encoded
      byte-identical at 0/1), F the four failures reproduced in order
      (each reports "no longer raises" post-fix). Corrected root
      causes recorded in `spikes/NOTES.md`.
- [x] **10.1 Multi-staff part model**: teach prep / ScoreModel / adapter
      that one `<score-part>` may own N staves; fix the part↔staff join
      so an 8-vs-7 count is correct by construction, not an error.
      Verify: `build_score_model(video_test)` succeeds; piano notes
      carry the right part with staff 1/2; existing fixtures unchanged.
      As built (2026-07-13): prep and the adapter identity chain were
      ALREADY multi-staff-aware (`PartInfo.staff_count`/`first_staff`,
      `part_for_staff`, part-local `staff_local` in ids) — the entire
      fix lives in `build_score_model`: expected music21 part count =
      `sum(staff_count)`; grouped consume (each PartInfo takes its next
      `staff_count` music21 parts) with a loud PartStaff-id contract
      check; per-note `staff` = the PartStaff's 1-based slot (music21
      files notes by MusicXML `<staff>`, the same source as MEI
      `@staff`, so both sides agree by construction — the video join is
      a complete 1368/1368 bijection). `_measures(parts[0])` unchanged.
      This chart's piano LH holds only rests/chord symbols, so staff-2
      NOTES don't occur; staff-2 identity minting is pinned via its
      MRESTs/scaffold (`P5:m*:s2:*`). Tests: tests/test_video_score.py.
- [x] **10.2 Ledger-dash attribution across staves** — mechanism
      corrected: the m12 dash belongs to a two-voice REST displaced off
      the staff (staff 2 = Ten/Bari, not even the piano); the
      (page, measure, staff) scope was already right, the candidate
      pool lacked rests. As built: two-tier attribution in
      `_attribute_ledger_dashes` — noteheads first, RESTS only when no
      notehead matches (same overlap+side rule; onset from the
      timemap's restsOn, layer from SVG nesting) — so testscore is
      byte-identical by construction (its rest tier is never
      consulted; the 90-dash pin untouched). Verified: the m12 dash
      inherits the rest's (onset 42.0, voice 1); all 355 video dashes
      carry onset+voice; STAFF_LINES exactly 5 paths on all 360 staves.
- [x] **10.3 Grand-staff tie/spanner continuation** — mechanism
      corrected: not grand-staff-specific; Verovio draws tie
      continuation ink ONLY in the tie's END system, and drops 6 ties
      outright. As built: class-aware crossing predicate in
      `_attribute_spanner_segments` (ties/lv: end==n; slurs/hairpins:
      start<n<=end, unchanged); count mismatches pair up to the
      shorter list + `LoadWarning("segment-count-mismatch")` instead
      of raising; `_build_elements` skips unmatched continuations with
      `LoadWarning("unattributed-continuation")`. Dropped spanners
      detected STRUCTURALLY (MEI spanner with no inked accumulator —
      empty <g>s; no log parsing) → `LoadWarning("dropped-spanner")`
      with musical coordinates only (rule 4). Warning seam:
      `LoadWarning` (types.py) + `EngravedScore.warnings` (appended
      field); `load()` still returns bare Layout; the status bar shows
      the count. Pinned: video = exactly 6 dropped-spanner warnings, 0
      mismatches, sys-4's six `:seg1`s at extent q29.5→q30.0;
      testscore's 5 known open ties (Phase 0) and the spanner
      fixture's 3 (Phase 5) now flag the same way — no longer silent.
- [x] **10.4 Decomposer class coverage**: two staff groups load on
      `testscore`; `video_test`'s new classes never reach the guard;
      N≥2 pinned by test. As built (2026-07-13): root fix is
      `condense:"encoded"` in the fixed toolkit options — auto-condense
      HID EMPTY STAVES at 2+ groups (7/3/6/3/5 staff rows) besides
      drawing the divider; encoded keeps 7×5 rows, 10 span-keyed
      grpSyms, ZERO dividers, byte-identical 0/1-group renders.
      `ElementKind.SYSTEM_DIVIDER` still added defensively (ruling a):
      id-less `_walk` branch + `score:sys{n}:systemdivider:{seq}` ids,
      covered by a synthetic-SVG unit test since no fixture draws one
      anymore. `bracketSpan` → OTHER, `mSpace` → containers. grpSym
      identity became GEOMETRIC (which staves the symbol's bbox spans →
      part span via `part_for_staff`), replacing injected-slot
      ordinals: Verovio SUPPRESSES a native brace when an injected
      group overlaps its part, so slot bookkeeping can't work. Phase 8
      ids reproduce verbatim (`score:sys{n}:grpsym:P1-P2`); a native
      grand-staff brace mints its part id alone
      (`score:sys{n}:grpsym:P5` × 15 on video); the `x{seq}` fallback
      is gone. Tests: tests/test_adapter_groups.py (two-group load,
      N=2 id stability, divider statics + synthetic decomposition).
- [x] **10.5 End-to-end + fixture promotion**: `video_test.musicxml`
      promoted to the permanent fixtures (`VIDEO_SCORE` +
      `engraved_video`/`video_score_model`/`video_join_mapping`
      session fixtures); tests/test_video_score.py pins the census
      (4661 elements, 7 pages, 1368 note records, complete join), new
      notation kinds, reload determinism, and grouped-id stability
      WITH a native brace in play (adding P1–P2 adds exactly its 15
      grpSym ids). Scripted exit run 20/20 on the offscreen
      MainWindow: opens (join complete, 6 warnings in the status bar),
      animates (4038 crossings, stateless scrub), exports (transparent
      PNG frame with ink), two brackets added live — 30 then 45
      grpSyms — undoable to zero with the native brace intact and
      musical ids stable across every re-engrave. Review artifact with
      all 7 fully-lit pages + the two-bracket render delivered.

**Exit criteria**: `video_test.musicxml` loads, plays, and exports
cleanly; two or more staff-group brackets can be added in-app,
undoable, with stable ElementIds; `pytest` green with the new fixture
in the suite. Build complete 2026-07-13 — 387 tests green incl.
`test_no_qt_in_core.py`, 20/20 scripted exit checks. The user's review
of the rendered output REQUIRED FOUR FIXES (hidden staves, animate
everything, the m44 artifacts, systems-mode framing/never-clip) —
**superseded by Phase 10R below**; acceptance rides its exit.

## Phase 10R — Review fixes (2026-07-13)

The Phase 10 exit review required four fixes. Build complete
2026-07-13 (405 headless tests green; 16/16 scripted exit checks on
the real MainWindow offscreen; updated review artifact with the
hidden-layout pages, the m44 before/after, and a systems-mode frame).
Rulings at plan review (2026-07-13): hide-empty-staves is a per-score
toggle DEFAULT ON for new documents (v≤3 projects load OFF — look
unchanged); meter signatures ANIMATE (literal reading: only barlines +
clef/key stay static among notation); page furniture (part labels,
labelAbbr, pgHead/pgFoot, measure numbers) stays static; **rule 7
amended as the user directed** ("we must allow for page breaks
ourselves") — never clip, repaginate when encoded pages can't hold
their systems, hide-empty-staves as an engraving input. Spike facts in
`spikes/NOTES.md` "Phase 10R" (`spikes/phase10r_spike.py`, kept).

- [x] **10R.0 Spike**: the two-pass MEI-optimize load is id- AND
      timemap-transparent (4959 ids, 215 timemap entries identical; no
      double-transpose; +0.12 s); `optimize` is the ONLY hidden-staff
      switch Verovio honors; condensed layouts draw systemDividers
      unless `systemDivider:"none"` (adopted — Dorico's look); the
      native brace follows staff visibility (3 grpSyms on video
      hide-ON, incl. one-staff braces); testscore hide-ON would hide
      its drum staff mid-slash-region (the fallback exists for this),
      video loses no slash staff; `<print new-page>` injection in part
      1 alone controls pagination; attach-onset census (fermata/trill
      = @startid, dir/tempo/harm/dynam = @tstamp, nothing bare).
- [x] **10R.1 Hide empty staves**: two-pass load in the adapter
      (`_make_toolkit` + `_set_scoredef_optimize`;
      `load_detailed(..., hide_empty_staves=)` — a separate arg like
      groups/texts, rule-5 reasoning); slash contingency AS REFINED at
      plan review: only when a slash-region staff actually vanishes
      does the load redo flat (+"hide-unavailable") — video (which HAS
      slash regions) keeps hiding, testscore degrades safely. Schema
      v4 (`hide_empty_staves`, version-gated read); `SetHideEmptyStaves`
      command; Parts-menu checkable action riding the Phase 8
      re-engrave diff-guard (`_applied_hide_empty`). Pinned:
      tests/test_hide_empty_staves.py (staves/system
      8,2,2,4,2,2,5,4,5,4×6; note_records identical to flat; zero
      overflow; grpSym P5×3; determinism; the testscore fallback),
      serialize v4 tests, command test.
- [x] **10R.2 Animate everything**: ANIMATED_KINDS += TEXT,
      CHORD_SYMBOL, LYRIC, METER_SIG — `is_animated`'s onset gate does
      the rest; the adapter mints page furniture onset-less
      (`_STATIC_TEXT_CLASSES` guard on the measure-start fallback) and
      resolves attach onsets for fermata/trill/mordent/turn/dir/tempo/
      reh/harm (`attach_startid` + `_attach_onset`; a chord @startid
      resolves through its first member — build find). dir/harm gained
      exact @tstamp attach. TINTED/ANCHOR/REVEALED sets unchanged
      (attachments, ruling D stands). Pinned: schedule census rewrite +
      video attach-onset pins.
- [x] **10R.3 Implausible-tie suppression (the m44 fix)**: Verovio
      force-matches 13 unclosable ties to distant same-pitch notes
      (10.5–148.5 quarters; real ties ≤4) whose stacked curves drew as
      ovals around m44. `_flag_implausible_ties` (after segment
      matching — bogus sources stay in the pairing pool — before
      element construction): extent > 2× start-measure duration →
      source AND continuation ink suppressed, one "implausible-tie"
      warning each. Pinned: no surviving tie exceeds the threshold,
      the q17.5→q166 id gone, seg-counter re-derived (system 15's ink
      was entirely bogus), testscore/spanner zero-suppressed.
- [x] **10R.4 Systems framing + never-clip**: the frame KEEPS the
      page's aspect in BOTH live and export — StageView fits a
      page-sized window centered on the band (view sceneRect widened so
      near-edge systems center instead of clamping — build find);
      FrameRenderer sizes system mode exactly like paged
      (`even_size(page, height)`), renders the page-wide window, clips
      to the band's projected strip; ExportSpec.width and the system
      W×H dialog controls REMOVED (one height field, both modes).
      Never-clip: `plan_page_breaks` (pure greedy planner, measured
      margins, 2% drift pad — the re-engrave placed one system 2 units
      lower than measured) + `_repaginate` at the prep seam (strip
      encoded new-page, inject at planned system starts, part 1 only)
      + the measure-verify-retry loop in `load_detailed`
      ("repaginated" warning; defensive "system-overflow" post-check).
      video FLAT: 8/15 systems used to overflow (worst y 6071/2967) →
      now 15 pages, zero clipped. Pinned: tests/test_repagination.py,
      re-shaped export tests, stage page-frame test.
- [x] **10R.5 Docs + fixtures + exit**: rule-7 amendment (CLAUDE.md;
      ARCHITECTURE adapter rulings 7/8/9 + taxonomy + schema v4);
      fixture strategy — testscore family and `engraved_video` stay
      hide-OFF (the flat fixture now exercises suppression AND
      repagination in one load), `engraved_video_hidden` pins the
      new-document default. Scripted exit run 16/16 offscreen: default
      hidden layout (7 pages, no overflow), m44 clean, animate-all
      census, toggle-off → 15-page repagination → undo, page-shaped
      systems frame live + export (transparent outside the band).

**Exit criteria**: video_test opens on the hidden-staff layout with
nothing clipped in either layout; m44 reads clean; texts/trills/
chords/meters animate while barlines/clefs/keys/furniture stay static;
systems mode keeps the page frame with the system centered, live and
exported. Build complete 2026-07-13 — 405 tests green incl.
`test_no_qt_in_core.py`.

Post-review fixes (2026-07-13, from the user's run): a page-follow jump
(bar 3 → page 4 and back) traced to Verovio REUSING SVG group ids
across element types under condensed layout — a note-owned fragment's
own id collided with a distant note's, so `_identity_for` picked up a
late onset and the schedule stamped a stray page/system on that beat.
Fix: onset lookups are gated by svg_class (only notes/rests read
onset_by_id by id; spanner classes the spanner table; "beam" the beam
table; note-owned fragments use owner_onset) — corrects BOTH paged
page-follow and systems-mode system-follow (the same stray stamps).
The systems-mode "canvas changes size" report was the same bug's
visible face in system mode (a wrong-system jump); the frame itself was
already page-constant since 10R.4 — now pinned end-to-end (identical
export pixels across the walk; identical live zoom across systems).
409 tests green. **PASSED pending the user's visual review** (review
artifact updated in place).

## Phase 11 — Dorico robustness: any export loads (complex1)

Planned 2026-07-19 from `docs/PHASE11_BRIEF.md` (Cowork planning
session, 2026-07-15). The brief's diagnosis was re-verified against the
real files by the triage spike (`spikes/complex1_triage.py`, kept)
before planning — the failure chain, censuses, and shim results all
reproduce, and the spike corrected four brief details (below).
Milestone: `testdata/complex1.musicxml` (14 single-staff parts, 3
pages, 921 notes) loads, animates, and exports. **Stepping stone to
Phase 12** (orchestral complex2, `docs/PHASE12_BRIEF.md`): the
decomposer/geometry fixes here are exactly what complex2 needs to get
through decomposition at all — Phase 11's exit only requires complex2
to *load* (with its 20 system-overflow warnings); laying it out is
Phase 12's problem.

Rulings already made — recorded here, not re-opened:

- **Graceful degradation (Marcus, 2026-07-15, Cowork session):** an
  unknown drawable SVG class in the app path no longer fails the load —
  it mints a static OTHER element plus `LoadWarning("unknown-class")`,
  never a silent skip and never a crash (the status bar counts it,
  stderr names the class). Tests stay strict: a fail-fast flag,
  default on under pytest and the doctor's `--strict`, preserves the
  Phase 10 discipline so coverage gaps keep surfacing loudly in
  development.
- **The grace/appoggiatura join fix is Phase 12 task 12.1, NOT this
  phase** (2026-07-15): complex2 showed the join needs an order-based
  rewrite, not a grace tolerance — one fix covers both files. Phase 11
  only PINS complex1's join gap so regressions surface.

Spike corrections to the brief (2026-07-19, all frozen in
`spikes/complex1_triage.py`):

- **The container treatment of bTrem is not clean.** The tremolo
  stroke glyph (SMuFL E222) is a DIRECT child of the id-bearing
  `<g class="bTrem">`, not nested inside the note/stem groups. A
  container shim loads, but the stroke silently folds into the
  enclosing static STAFF_LINES scaffold (complex1's P9 m7 staff gains
  a 6th primitive) — the BACKLOG-6 ledger-line bug shape. bTrem must
  EMIT its own element; ruling (a) below is therefore a real choice,
  not something that falls out for free.
- **fTrem occurs in NEITHER file** — all 85 complex2 tremolos are
  bTrem. fTrem coverage lands defensively via a synthetic-SVG unit
  test only (the SYSTEM_DIVIDER precedent).
- **The 22 unmatched joins are NOT the grace notes.** All 26 graces
  match via join.py's existing onset-excluded grace tier. The
  unmatched are the PRINCIPAL notes carrying the graces: Verovio's
  timemap delays each principal by the grace duration (+0.0957 q,
  exactly, on every pair; both sides flag grace=False) while music21
  keeps the notated beat, so the exact-onset key misses. Identical
  appoggiatura semantics to complex2's 1882/9546 collapse, at
  acciaccatura scale — confirming the one-rewrite-in-12.1 call.
- Minor: complex2's beamSpan raises on page 5, BEFORE its rotates
  (pages 8 and 16 in the raw render — the brief said page 5; all are
  exactly −90°). MEI `beamSpan` carries @startid/@endid but is not in
  the layer-beam table, so a bare kind-mapping yields an onset-less
  beam — 11.1 resolves its onset/extent from startid/endid. And
  because the stroke ink stops folding into the staff, complex1's
  element census becomes **3491, not the brief's shimmed 3490** (the
  bTrem element is new); 11.5 pins the as-built number.

Rulings at plan review (Marcus, 2026-07-19): **(a)** tremolo stroke
ink ANIMATES with the owning note — the bTrem element carries its
child note's onset (chord-member style) and joins the
opacity-triggered set; it is playing ink under the Phase 10R
animate-everything taxonomy (tint scope unchanged). **(b)** all four
spike corrections above accepted — the plan builds on the corrected
mechanisms (census pin 3491; fTrem defensive-only; join gap pinned as
the grace-delayed principals; beamSpan onset from @startid/@endid).

Build complete 2026-07-19 (430 headless tests green incl.
`test_no_qt_in_core.py`; 13/13 scripted exit checks on the offscreen
render pipeline; review artifact with complex1's three rendered pages
delivered). **Exit criteria PASSED 2026-07-19** — full pytest green,
score-doctor PASS on all four permanent fixtures, complex2 loads
through decomposition (42,615 elements, 20 pages, 20 system-overflow
warnings — layout is Phase 12), complex1 opens/animates/exports a
transparent frame with ink. Build facts: the offscreen `MainWindow`
hangs in headless runs (no event loop), so the scripted exit drives
`ScoreScenes` + `FrameRenderer` directly (the render_page_png idiom);
one bTrem in complex1 (P9 m7, onset 24.0) — the census is 3491, not
the brief's shimmed 3490, because the stroke stops folding into the
staff.

- [x] **11.0 Score-doctor CLI**
      (`python -m scoreanim.tools.check_score <file-or-dir>`): headless
      load of any MusicXML; prints PASS (element/page/note counts,
      warning census, join completeness) or the exact failure point;
      batch mode over a folder; `--strict` fail-fast (the 11.4 flag).
      This is the engine of the "any Dorico file" goal: every new
      score becomes one-command triage, and the loop (doctor →
      smallest fix → fixture) becomes routine. Verify: doctor PASSes
      testscore, the spanner fixture, and video_test; on complex1 it
      reports the bTrem failure point (pre-11.1) instead of a
      traceback.
      As built (2026-07-19): `scoreanim/tools/check_score.py` — a total
      triage function `check(path, *, strict)` returning a `_Report`
      (PASS census or a named failure STAGE, never a traceback), a CLI
      with batch-a-folder and `--strict` (non-strict is the default,
      the app path), non-zero exit on any FAIL. Threads a `strict` load
      param through `load_detailed`/`_engrave_prepared`/`_LoadState`
      (inert until 11.4). Tests: tests/test_check_score.py.
- [x] **11.1 Decomposer/geometry coverage**: `bTrem` (and `fTrem`
      defensively) as EMITTING kinds per ruling (a) — the stroke ink
      is claimed by the tremolo element, never the staff scaffold;
      `beamSpan` → BEAM with onset/extent from MEI @startid/@endid
      (the layer-beam table cannot serve it); rotate transforms parsed
      into the Affine matrix + `apply_rect` rewritten to map all four
      corners (exact for 90° multiples, conservative otherwise), the
      "Verovio never rotates" docstring assumption dropped. Verify:
      synthetic-SVG unit tests per class; complex1 decomposes past
      page 2; complex2 decomposes end-to-end; existing fixtures
      byte-identical.
      As built (2026-07-19): `ElementKind.TREMOLO` (added to
      ANIMATED_KINDS only — tint scope unchanged); bTrem/fTrem in
      `_KIND_BY_CLASS`, onset propagated in the walk from
      `_MeiIndex.tremolo_note_ids` (chord-member style). `beamSpan` →
      BEAM with `_MeiIndex.beamspan_ends` (@startid/@endid) in a new
      `_identity_for` branch. `svg_geom.parse_transform` grew a
      `rotate(a[,cx,cy])` case; the `matrix` case dropped its
      is_axis_aligned raise; `Affine.apply_rect` corner-maps (reduces
      to the old two-corner result when axis-aligned). complex2 loads
      end-to-end (42,615 = 42,530 + 85 real tremolos). Tests:
      tests/test_adapter_coverage.py, updated
      test_svg_geom/test_core_types.
- [x] **11.2 mRest ledger tier**: whole-bar rests join the Phase 10.2
      rest tier in `_attribute_ledger_dashes` (same geometry rule —
      complex1 p3 m13 staff 8's two-voice measure displaces its mRest
      onto a ledger dash). Verify: complex1 loads past page 3, the
      x=1277 dash carries the mRest's (onset, voice); testscore and
      video_test byte-identical by construction (the tier is consulted
      only on a notehead miss).
      As built (2026-07-19): one-line change —
      `elif acc.svg_class in ("rest", "mRest"):` in the rests_by_scope
      pass. complex1 loads fully (3491 elements, 899/921). Adds the
      engraved_complex1/complex1_score_model conftest fixtures. Tests:
      tests/test_complex1.py.
- [x] **11.3 Join gap pinned, not fixed**: complex1 joins 899/921; a
      fixture test pins the 22 unmatched as EXACTLY the grace-delayed
      principal set from the triage spike (ids pinned; all 26 graces
      matched; every unmatched pair off by exactly the +0.0957 grace
      delta) so any regression — or the Phase 12.1 fix — moves a
      pinned number. Verify: headless test against the promoted
      fixture.
      As built (2026-07-19): tests/test_complex1.py pins the 22
      unmatched-layout ids (`_GRACE_DELAYED_PRINCIPALS`), all 26 graces
      matched, nothing unmatched is itself a grace, and every pair the
      same pitch off by +0.0957 q.
- [x] **11.4 Graceful degradation** (ruled, above): unknown drawable
      SVG class → static OTHER element + `LoadWarning("unknown-class")`
      in the app path; strict mode (pytest default, doctor `--strict`)
      keeps today's raise. Verify: synthetic unknown-class SVG
      degrades with the warning in app mode and raises in strict;
      no known fixture triggers it after 11.1.
      As built (2026-07-19): the decomposer's unknown-class guard is
      gated on `st.strict` — strict raises; non-strict mints a static
      OTHER accumulator claiming the drawables, appends the warning,
      names the class on stderr. main_window's load/reload passes
      `strict=False`. Tests: tests/test_adapter_coverage.py.
- [x] **11.5 Fixture promotion + exit**: complex1 joins the permanent
      fixtures with census pins (3491 elements, 3 pages, 921 note
      records, join 899/921 with the pinned grace-principal set, 3
      dropped-spanner warnings); scripted exit run on the offscreen
      MainWindow: open, animate, export a frame. Docs close out the
      established way (CLAUDE.md testdata note + unknown-class rule
      text, ARCHITECTURE.md §3 tremolo/beamSpan/rotate rulings +
      LoadWarning code list, BACKLOG.md robustness note). Verify: full
      pytest; doctor PASS on all four fixtures AND "loads with 20
      system-overflow warnings" for complex2.
      As built (2026-07-19): census + notation-coverage pins
      (tremolo element animates untinted, unpitched percussion, reload
      determinism) in tests/test_complex1.py. Scripted exit 13/13 on
      the offscreen render pipeline (MainWindow hangs headless — no
      event loop — so it drives ScoreScenes + FrameRenderer, the
      render_page_png idiom). complex2 stays OUT of the pytest suite
      (~20 s/load); the score-doctor is its check. Docs closed out per
      the checklist.

**Exit criteria**: complex1 loads, plays, and exports cleanly (join
gap = exactly the pinned grace-principal set); the score-doctor
reports PASS for the four permanent fixtures and complex2 loads
through decomposition with only overflow-class warnings; `pytest`
green including `test_no_qt_in_core.py`.

## Phase 12 — Orchestral robustness: complex2 loads usably

Planned 2026-07-21 from `docs/PHASE12_BRIEF.md` (Cowork planning
session, 2026-07-15). **Phase 11 was the stepping stone and is closed.**
The brief's diagnosis was re-verified against the real files during
planning (join pipeline read against `core/score/join.py`; two
read-only complex2 censuses; the condense-render spike
`spikes/condense_prep.py`, kept) — and **corrected the brief on two
points** (below). Milestone: `testdata/complex2.musicxml` (36 parts /
37 staves, 159 measures, 5.7 MB, 11 transposed parts, Dorico-condensed
in the PDF, bar repeats; companion `complex2.pdf`) **loads, renders
usably via load-time user choices, animates, and exports.** complex2
already loads through decomposition (Phase 11: 42,615 elements, 20
pages) but is structurally unusable — every one of the 20 systems
overflows its page (a 37-staff system is taller than one page;
repagination cannot fix a single over-tall system). The user must be
able to reduce staff count at load time (condense / hide / bracket).

Reconciliation with rulings that post-date the brief (now in CLAUDE.md):

- **Animation is a DENYLIST** (`schedule.STATIC_KINDS`; `ANIMATED_KINDS`
  is derived). A new `ElementKind` animates by default, so 12.2's
  synthesized `BAR_REPEAT` elements enter the animated set with ZERO
  allowlist edits — the adapter only mints them with an onset and keeps
  them out of `STATIC_KINDS`. The brief's "the kind census has no repeat
  kind" is a non-issue. Tint scope unchanged (repeat symbols tint like
  slashes — playing ink).
- **No-audio playback (WallClock) exists.** The Score Setup dialog
  re-engraves via the existing `_reengrave` diff-guard (preserves
  page/system/zoom); 12.4/12.5 must verify it does NOT reset the
  no-audio transport/WallClock anchoring (the controller picks the clock
  by `transport.has_media()`). A "don't break it" check, not new work.

Rulings at plan review (Marcus, 2026-07-21):

- **(a) Trigger timing for notes after appoggiaturas — Verovio
  performance qstamp**, not the notated beat. The principal lights when
  it actually sounds (Verovio delays it by the grace duration),
  consistent with how graces already fire (Phase 3.3) and the sync
  contract (ink lands on the audible onset). 12.1's order-based join
  keeps both onsets derivable, so the choice is reversible.
- **(b) Bar-repeat granularity — per measure.** One synthesized repeat
  symbol (SMuFL `repeat1Bar` U+E500) per repeated bar, onset at the
  bar's downbeat. (Verovio draws no glyph at all — full synthesis; a
  measure-repeat is one symbol per bar, so per-beat has no ink to draw.)
- **(c) Score Setup dialog — batch on OK.** The dialog gathers all
  choices; OK applies ONE command (the "fat apply" idiom — there is no
  generic macro command) = one undo step + exactly one re-engrave.
  Chosen because complex2 re-engraves in ~20 s (vs 0.6 s on the
  fixtures), so the existing per-action live-re-engrave dialog model
  (Staff Groups) would stall repeatedly. The Setup dialog is therefore a
  BATCH editor (deferred apply), unlike the per-action Parts dialogs.
- **(d) Condense scope — v1 as designed** (naive shared-staff two-voice
  merge; one voice per player; combined label; NO a2 unison collapse, NO
  divisi logic). Confirmed by the render spike: the naive Flute 1.2
  merge renders cleanly (correct stem/rest/beam separation, no
  collisions) on both unison and divergent passages; the only cost is
  doubled noteheads in unison (a2-collapse deferred to BACKLOG). Merging
  two flutes took that staff 5 pages → 3.

Spike corrections to the brief (2026-07-21, `spikes/NOTES.md` Phase 12):

- **Verovio draws NOTHING for `<measure-repeat>`.** Its MusicXML
  importer has no measure-repeat support — repeat bars import as
  invisible `<space>`; there are ZERO `mRpt`/`beatRpt` glyphs in the MEI
  or the SVG. The brief's "Verovio draws the mRpt symbol" is wrong. →
  12.2 FULLY SYNTHESIZES the % symbol (the slash-region shape), not
  "map the glyph."
- **3 regions / ~32 bars, not "6 regions."** The 6 `<measure-repeat>`
  tags are 3 `[start, stop)` spans (Bongos mm.2–12 & mm.14–24, Drum Set
  mm.98–107) — the same half-open convention `_slash_regions` uses.
- **12.1 join is surgical.** `_match_voice` already sorts+zips both
  sides by document order within a bucket; the ONLY onset dependence is
  `_note_key` embedding `round(onset*4096)` for non-graces. Dropping
  that term is the whole fix; the grace tier already works this way.

- [ ] **12.0 Spikes** (kept — findings in `spikes/NOTES.md`): (a)
      condense-merge prep rewrite (`spikes/condense_prep.py`) — Flute
      1/2 → one staff two voices, rendered before/after, viability
      confirmed (ruling d); (b) measure-repeat census — Verovio draws
      nothing, 3 `[start,stop)` regions / ~32 bars; (c) appoggiatura
      timemap semantics — principal delayed +grace-dur, order-based
      `(pitch, order)` join handles chord-graces. DONE during planning.
- [ ] **12.1 Order-based join**: rewrite `_note_key` so plain notes key
      on `pitch_key` only (drop the `round(onset*4096)` term) — pairing
      falls to `(pitch, document order)` within `(part, measure, staff,
      voice)`, onset as tiebreak, the shape the grace tier already uses.
      Verify: complex1 joins 921/921 (the 22 grace-delayed principals
      now match); complex2's join completes; testscore + video_test
      mappings BYTE-IDENTICAL (re-pin). Update `tests/test_complex1.py`
      (`_GRACE_DELAYED_PRINCIPALS` → complete bijection) and the
      `tools/check_score.py` counts. Trigger stays the qstamp (ruling a
      — no retiming; the fix only closes the match).
- [ ] **12.2 Bar-repeat synthesis**: `ElementKind.BAR_REPEAT` (animates
      by default under the denylist; tinted like SLASH). Detect
      `<measure-repeat>` regions at the prep seam (`_repeat_regions`, a
      `[start, stop)` twin of `_slash_regions`; `RepeatRegion` on
      `PreparedScore`). Synthesize in the adapter (`_synthesize_repeats`,
      a twin of `_synthesize_slashes`): one `repeat1Bar` symbol centered
      per repeated bar, positioned from `staff_geo`, onset =
      `measure_start[m]` (per-measure, ruling b). Extend the slash
      hide-retry guard so a repeat staff is not hidden out. Verify:
      complex2's 3 regions (~32 bars) light on the downbeat; existing
      fixtures byte-identical (no measure-repeats there).
- [ ] **12.3 Prep-seam condensing + schema v5**: `PartCondenseSpec`
      (neutral prep-seam twin beside `PartGroupSpec`) — contiguous like
      parts to merge + combined label ("Flute 1.2"). `_apply_condense`
      in `musicxml_prep`: merge N contiguous `<score-part>` + `<part>`
      bodies into one part, one `<voice>` per player on a shared staff
      (append behind a `<backup>` of the measure's voice cursor, relabel
      voices, force `<staff>1`), combined `<part-name>`/-display; keep
      `PartInfo.staff_count`/`part_for_staff` consistent. v1 naive
      (ruling d): NO a2-collapse, NO divisi → BACKLOG. Decide the
      absorbed-part `<direction>` handling (take primary only vs accept
      doubling on divergent bars). Doc: `condense_groups` field +
      Add/Edit/RemoveCondenseGroup commands (the StaffGroup triad).
      **Schema v5** (one bump; `_READABLE_VERSIONS = 1..5`, writer emits
      5, version-gated read). Thread `condense_groups` through
      `provider.load`/`load_detailed`/`prepare` + the main_window
      conversion + a fourth `_applied_condense` diff-guard clause.
      ElementIds shift when condensing changes (part identity is an
      engraving input, like renames) — overrides re-derive; pin id
      behavior. Verify: merged part loads through the adapter + join;
      undo restores; round-trip.
- [ ] **12.4 Score Setup dialog**: triggered at LOAD when the flat
      render overflows (inspect `engraved.warnings` for
      `code == "system-overflow"` after `load_detailed` in the load path
      — `open_score`/`open_project`/`_load_score`, NOT on every
      `_reengrave`) and on demand via **Parts → Score Setup…**. A
      per-part list with three controls: condense-group, staff-group
      (existing), hide-empty-staves (existing). BATCH editor: OK applies
      one command = one undo step + one re-engrave via the diff-guard
      (ruling c). Verify: complex2 opens → dialog offered; the no-audio
      transport survives the re-engrave (WallClock reconciliation);
      undoable.
- [ ] **12.5 Scale + fixture promotion + exit**: perf numbers recorded
      (load, scene build, tick cost on a dense page — no optimization
      unless targets miss). complex2 promoted to the permanent fixtures
      with censuses pinned (kept OUT of the ~20 s pytest path per the
      Phase 11 precedent — the score-doctor is its check). Scripted
      offscreen exit (ScoreScenes + FrameRenderer idiom — the offscreen
      MainWindow hangs headless): open complex2 → Setup choices (condense
      wind/brass pairs + hide empty) until zero system-overflow →
      animate → export frames. Docs close-out the established way
      (CLAUDE.md rule-10 family + testdata note + a condensing rule;
      ARCHITECTURE §3 mRpt synthesis + appoggiatura semantics, §4 schema
      v5, §7 Setup dialog, §8 orchestral-scale risk; BACKLOG divisi/a2 +
      per-passage condensing). Review artifact: rendered complex2 pages
      next to `complex2.pdf` pages, plus the bar-repeat and appoggiatura
      measures up close (fidelity target "usable and clean", not
      PDF-identical — the user's condense choices differ from Dorico's).

**Exit criteria**: complex2 opens with the Setup dialog and, with
reasonable choices, renders with zero system-overflow warnings,
animates in sync, and exports; join complete on all six fixtures;
`pytest` green including `test_no_qt_in_core.py`.

## Later (explicitly not now)

Continuous-scroll presentation mode; glow (needs perf spike); audio-to-
score auto-alignment provider; custom engraving provider; MIDI input;
richer effect editor; arbitrary-exporter MusicXML robustness (Dorico
robustness advanced in Phase 11 — the score-doctor loop + graceful
degradation; other exporters remain future work).
(In-app score-text editing graduated to Phase 9; brackets/grouping to
Phase 8 — 2026-07-12. Multi-staff-part & decomposer-coverage robustness
to Phase 10 — 2026-07-13. Dorico robustness / complex1 to Phase 11 —
2026-07-19; orchestral complex2 layout + order-based join planned as
Phase 12 — 2026-07-21, rulings recorded, spikes done, ready to build.)
