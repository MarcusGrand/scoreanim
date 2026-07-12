# ScoreAnim — Architecture

## 1. What the app is

The user formats a score in notation software (Dorico primarily) and
exports MusicXML. ScoreAnim animates that score — notes and other elements
appearing/highlighting in time — synchronized to a recorded audio
performance (wav/mp3). The end product is the animation overlaid on
performance video. The app is a live authoring tool (real-time playback
against the audio) with a deterministic frame-by-frame export path.

Explicitly out of scope: score content editing (re-notation happens
upstream in the notation software), audio synthesis, audio time-stretching,
automatic audio-to-score alignment (DTW) — the last may become a later
`AlignmentProvider` but v1 sync is authored manually via tempo marks and
beat tapping.

## 2. Layer map

```
Score file (MusicXML, Dorico export)
   │
   ├──► ScoreModel (music21)          id → musical_time (beats), identities
   │
   └──► EngravingProvider (Verovio)   id → position/geometry per page
              │  honors encoded system/page breaks
              ▼
        base Layout  ⊕  LayoutOverrides (user dx/dy deltas)
              ▼
        EffectiveLayout ── per-element, identity-tagged, paged
              │
              ▼
        Animation layer: state(element, t) → property values
              ▲                    ▲
              │                    │
        TempoMap             Clock (injected)
        beats ⇄ seconds      AudioClock (live) | FrameClock (export)
        (BPM events, taps,
         swing per region)

Render (Qt): EffectiveLayout → QGraphicsItems; applies property values.
UI (Qt): stage view, tempo lane, waveform, transport — observers of AppState.
```

Shared currency across all layers: **our own `ElementId`**, assigned by the
Verovio adapter at decomposition time. Verovio's IDs are translated at the
boundary and never appear downstream.

## 3. Core types (contracts)

```python
# core/score/
@dataclass(frozen=True)
class ElementIdentity:
    element_id: ElementId
    kind: ElementKind            # NOTEHEAD, STEM, BEAM, SLUR, HAIRPIN, DYNAMIC, ...
    part: PartId                 # "Violin I"
    staff: int
    voice: int
    onset: Beats | None          # None for non-timed elements
    extent: tuple[Beats, Beats] | None   # spanners: (start, end)

# core/engraving/
class EngravingProvider(ABC):
    def load(self, score_path: Path, params: EngravingParams) -> Layout: ...

# Verovio adapter obligations (Phase 0 rulings, 2026-07-10):
#
# 1. Concert pitch, always: transposeToSoundingPitch=True is a fixed part
#    of EngravingParams, not a user option in v1. Exception: parts whose
#    <transpose> is octave-only (octave-change, no chromatic shift — e.g.
#    guitar, bass guitar) keep conventional written octave; chromatic
#    transpositions render at concert pitch. Verovio has no per-part
#    transpose option, so the octave exception is handled at the adapter
#    boundary (e.g. adjusting <transpose> before load).
#
# 2. Deterministic IDs: the adapter always sets a fixed xmlIdSeed.
#    Verovio otherwise generates fresh random ids per load (verified in
#    Phase 0); layout overrides, style rules, and headless tests all
#    depend on stable ElementIds.
#
# 3. Slash-region synthesis: Dorico exports slash regions as
#    <measure-style><slash/> with NO <note> elements (verified: drum part
#    mm. 3-9, 11-15, 16-17 of the test score — three [start, stop)
#    regions; m10 and m18 are real fills), which Verovio renders as empty
#    measures and which produce no timemap events. The adapter must
#    synthesize slash elements: one per beat from the time signature,
#    kind = SLASH, staff-positioned, with onsets on the beats, so slash
#    regions render and animate like notes.
#
# 4. Header as stage element (ruling 2026-07-10): long-term, the
#    title/composer block does NOT come from the engraving pipeline.
#    From Phase 2 on, Verovio renders with the header suppressed;
#    title/composer/lyricist become stage-level text elements stored in
#    stage_config, styled and positioned in-app and animatable like any
#    element (see PHASES 2.3). Phase 1's decomposition nevertheless
#    reproduces whatever Verovio emits — encoded header included —
#    faithfully; suppression is a rendering option, not a decomposition
#    exemption.
#    Planned revision (ruling 2026-07-11, BACKLOG item 5): score-anchored
#    texts (part labels, tempo marks, possibly the title) are to become
#    editable in-app with the engraved score shifting to fit — i.e. text
#    edits feed back into the engraving inputs and re-engrave. Not
#    scheduled; do not build toward it without an explicit decision.

@dataclass(frozen=True)
class RenderedElement:
    identity: ElementIdentity
    page: int
    x: float; y: float           # page coordinates
    bbox: Rect
    anchor: Point                # transform origin (bbox center) for scale/pop
    glyph: RenderPrimitive       # v1: SVG path fragment; engine-neutral wrapper
    system: int | None           # score-wide system index (Phase 5) —
                                 # engraving-derived like page; reveal
                                 # tracks are per (system, part)

@dataclass(frozen=True)
class Layout:
    pages: tuple[PageGeometry, ...]   # page size from the score, not the window
    elements: tuple[RenderedElement, ...]

# core/timing/
@dataclass(frozen=True)
class TempoEvent:
    position: Beats
    bpm: float

@dataclass(frozen=True)
class SwingRegion:
    span: tuple[Beats, Beats]
    ratio: float                 # 0.5 straight … ~0.667 triplet swing

class TempoMap:
    """Piecewise-constant tempo → piecewise-linear beats⇄seconds mapping.
    Precomputed segment boundaries; lookups are binary search + lerp.
    Invertible in both directions. Taps derive tempo events (smoothed)
    or, per region, act as hard anchors (dense events)."""
    def seconds_at(self, beats: Beats) -> float: ...
    def beats_at(self, seconds: float) -> Beats: ...

# core/animation/
class RevealMode(Enum):
    # STEPPED: the edge jumps at the part's EVENTS (tie-gated triggers,
    # rests resolving at min(next note, own barline) — see the reveal
    # section below). CONTINUOUS: placeholder lerp over the same
    # anchors; the real sweep is a single shared wavefront (BACKLOG 8).
    CONTINUOUS = auto()
    STEPPED    = auto()

@dataclass(frozen=True)
class Envelope:
    initial: float                      # value before the first keyframe
    keyframes: tuple[Keyframe, ...]     # (t_rel_seconds, value, easing)
    # `initial` added by Phase 3 ruling (2026-07-11): "floor before
    # onset" is inexpressible with finite keyframes under hold semantics.

@dataclass(frozen=True)
class Effect:
    name: str                    # preset registry: "appear", "pop"
    tracks: Mapping[PropertyId, Envelope]

# Open property set; the evaluator never branches on a property.
# Applied today: opacity (ElementItem parent), scale (around the stored
# anchor, restricted render-side to anchored kinds). REVISED from the
# original sketch (Phase 5 as built): reveal is NOT a property track —
# it is the clip edge driven by reveal_x below — and color is static
# tint (StyleRules), not an animated track. offset/glow remain unbuilt.

# As built (Phase 5.3): the pure kernel stays minimal —
#     element_state(trigger_seconds, effect, t_seconds)
# identity → effect resolution happens OUTSIDE it (StyleRules.resolve
# + the preset registry, cached in the applier), and beats → seconds
# for all triggers/anchors goes through one swing-aware
# resolve_seconds call. No hidden state, no timers, no accumulation;
# the same kernel serves AudioClock playback, scrubbing, and
# FrameClock export.
```

### Reveal / playhead-x unification (revised 2026-07-12, rulings A–C)

Per **(system, part)**, from the sorted `(trigger_beats, x)` pairs of the
part's events — beats taken from the trigger schedule's TIE-GATED
`beats_by_element`, then mapped to x (never derived from engraved x):

- `reveal_x(system, part, t, STEPPED)` — x of the latest event ≤ t.
- `reveal_x(system, part, t, CONTINUOUS)` — piecewise-linear over the
  same anchors. Placeholder: the real continuous mode is a single
  smooth shared WAVEFRONT per system revealing all ink (a different
  computational model — BACKLOG 8, its own design round).

**A tied chain is one event** (ruling A): tie-stop heads carry the
chain-start trigger, so the whole group collapses into a single anchor
at (chain start, x2 of the chain's furthest ink — its tie curves and
broken segments fold into the bucket of the system they sit in). The
edge steps past the full tied value at once and next advances at the
part's next event; a chain broken across systems stands revealed from
chain start on both sides. Events are noteheads, slashes, **and rests**
(ruling B) — a rest's trigger is when its silence resolves:
min(next note's trigger in its part/voice scope, end of its own bar),
never on its own silent beat (second-session ruling 2026-07-12), so the
edge never advances mid-silence. Dynamics animate at their attach point
(MEI @startid / @tstamp, adapter-resolved) but are attachments, not
events. Edges are per part so one part's tie holds only its own
spanners (known limit: per part, not per voice — voice labels relabel
per measure; BACKLOG 10).

**Spanners grow — this REPLACED Phase 3's step-appear** (ruling
2026-07-11): slurs, ties, and hairpins reveal by a clip-rect right edge
at `reveal_x`, opacity pinned 1.0, with a floor-opacity ghost of the
whole curve underneath (consistent with the dimmed ghost score);
RevealMode is the only knob. Spanners split across systems by Verovio
reveal per segment (adapter emits `<source-id>:seg<k>` elements);
segments in not-yet-reached systems sit at reveal = 0 with no page
logic. Any cursor reads this same function.

### Animated-ink taxonomy (revised 2026-07-12)

Opacity-triggered (dim at floor, light at trigger): noteheads, slashes,
stems, flags, beams, accidentals, articulations, dots, ledger dashes,
**rests, whole-bar rests, dynamics** (ruling B — everything IN the
staves animates; a dynamic's trigger is its attach point). **A rest is
retrospective ink** (ruling 2026-07-12, second session): it triggers
when its silence resolves — at the next note in its part/voice or at
the end of its own bar, whichever comes first, never on its own silent
beat (a whole-bar rest completes at its barline). Reveal anchors follow
the same triggers, so the edge never advances mid-silence.
Clip-revealed (opacity pinned 1.0): slurs, ties, hairpins. Static:
clefs, key/time signatures, barlines, staff lines, texts, lyrics,
chord symbols.

### Styling

`StyleRules` map musical identity → base visual properties (per-part
color + effect assignment, reveal mode). Rule-based, sparse; per-element
user overrides are higher-priority rules, merged field-wise. Serialized
in the project document. StyleRules SUBSUMED Phase 2's `StyleConfig`
(Phase 5.3) — one styling system: the tint menu drives part color
rules; effect names are stored intent resolving against the preset
registry (unknown → default, the name round-trips untouched). The
element-override editing UI waits on stage click-to-select (BACKLOG 9);
the floor opacity is preset data (`presets.FLOOR_OPACITY`), not a
StyleRules field. **Color scope ≠ animated scope** (ruling D):
`TINTED_KINDS` = the playing ink (heads through ledger dashes, plus
slurs/ties/hairpins) — rests and dynamics animate but stay black, like
clefs, signatures, and text.

## 4. Project document

```
Project (saved file, versioned schema)
├── score_ref            path + content hash of MusicXML
├── audio_ref            path + content hash of wav/mp3
├── engraving_params     scale etc. (page geometry comes from the score)
├── layout_overrides     {ElementId → dx, dy, hidden}
├── tempo_map            events, swing regions, raw taps (kept for re-derive)
├── style_rules          reveal mode, per-part {color, effect-name}
│                        rules, per-element overrides
└── stage_config         background, letterbox behavior, header text
                         elements (title/composer/lyricist — stage-level
                         text, not engraved; adapter ruling 4)
```

Schema versions (`core/project/serialize.py`, strict gate): **v1**
(Phase 4) had `style.part_colors`; **v2** (Phase 5.3) is the StyleRules
shape above. The reader accepts {1, 2} and folds v1 `part_colors` into
part color rules at load; the writer emits 2. The gate is
strict-by-version ON PURPOSE: a Phase 4 build REFUSES a v2 file instead
of tolerantly reading it, silently dropping all styling, and destroying
it on the next save. Effect names are stored intent — an unknown name
fails soft to the default preset at animation time but round-trips
untouched (rule 5).

Never persisted: Layout, timemaps, decomposed geometry — always re-derived.
All mutations go through undoable commands (`core/project/commands.py`).

Override staleness is accepted: after a reflow (e.g. Verovio upgrade),
deltas keyed to musical identity reapply on the new base; some may need
re-touching. "Clear overrides on selection" must be cheap.

## 5. Clocks, sync, drift

- `Clock` interface in core: `now_seconds() -> float` relative to
  transport start. **No transport state on the ABC** (Phase 3 ruling,
  2026-07-11): no core consumer branches on transport — the UI drives
  the tick and owns play/pause/seek on the Qt wrapper. Transport state
  joins the interface only when a core consumer actually needs it.
- `AudioClock`: wraps the audio backend's playhead position query.
  Implemented in render/ui land (it touches Qt multimedia); core sees only
  the interface. Because `QMediaPlayer.position()` is cached at a
  50–100 ms cadence (Phase 3 spike), the implementation is **tier 2b**:
  `now = perf_counter() + mean(position_i − perf_counter_i)` over the
  last ~12 positionChanged anchors, monotone-clamped, frozen while
  paused, re-anchored on seek. Not accumulation: a pure function of
  (recent authoritative audio positions, wall time), error bounded by
  the anchor cadence — the audio playhead stays master (rules 2/3).
- `FrameClock` (core/timing/clock.py, Phase 6 as built): `now =
  frame_index / fps` — a fresh division per query, never `t += 1/fps`,
  so drift in export is impossible by construction and out-of-order
  frame walks yield the same times as in-order ones.
- **The export path does not fork the live path** (Phase 6 as built,
  render/export.py). `FrameRenderer` owns a FrameClock and a PRIVATE
  `ScoreScenes` + `AnimationApplier` pair built from the same
  `AnimationInputs` the window retains at load (layout, stage, trigger
  schedule, reveal tracks — identical geometry and triggers, no
  re-engrave). Frame n calls `apply_at(t)` when n follows the last
  frame and `refresh(t)` otherwise — the exact tick/seek split of
  `PlaybackController`. Everything downstream (`element_state`,
  `reveal_x`, `current_page()`) is byte-for-byte the live path, and the
  export walk is pinned against fresh refresh, byte-identical across
  independent walks, in tests/test_export.py. **Needing to edit
  render/animate.py, ui/playback.py, or anything in core/animation/
  for export is a flag-and-stop moment, not an implementation detail.**
- **Sync contract** (Phase 6): exported video t=0 == recording t=0.
  Frame n samples t_audio = start + n/fps (frame start) and hands the
  applier t_score = t_audio − offset_seconds — the exact mirror of live
  playback's `_score_time` (ui/playback.py); core never sees the offset
  (`TempoMap.seconds_at(0) == 0` by construction). Frame count is
  `ceil((end − start) · fps − ε)` so the overlay always covers the full
  audio span. Range export shifts frame 0 to `start` (entered as a
  measure span in the dialog, converted through the same swing-aware
  `resolve_seconds` seam); the user composites the clip at that offset.
  Pinned headless with the real sidecar offset: onset frames at the
  start, middle, and end of the piece within ±1 frame — a uniform error
  is an offset bug, a growing error is drift, and the assertion
  separates them.
- **Offscreen transparent render** (Phase 6): pages render to
  `QImage(ARGB32_Premultiplied)` filled transparent — no window, no
  view — with the paper rect hidden (`ScoreScenes.page_rects`); the
  floor-opacity ghost ink exports as-is (ruling R1, transparent-only).
  Page turns hard-cut on the frame where `current_page()` changes,
  identical to live follow (ruling R2). One
  `convertToFormat(RGBA8888)` per frame un-premultiplies to the
  straight alpha encoders expect. ProRes 4444 .mov (ffmpeg stdin
  stream, runtime-discovered) is the default; PNG sequence (pure Qt)
  is the no-ffmpeg fallback. Export settings are session memory only
  (ruling R3) — nothing enters the project document.
- Rule 2 in CLAUDE.md (no time accumulation) exists because accumulated
  `t += dt` drifts over minutes-long pieces; absolute queries do not.

## 6. Rendering & performance model

- Load time (expensive, once): parse, engrave, decompose SVG into
  per-element `QGraphicsItem`s with identity, build indexes
  (trigger-bucketed schedule; reveal tracks and revealed-spanner lists
  per (system, part)).
- Per frame (cheap): update only elements whose state changes — crossed
  triggers, timed effects inside their transition window, plus one
  clip-edge move per active spanner (per-(system, part) edges are
  cached, so a STEPPED edge that holds between events costs nothing).
  Target 60 fps on a dense page.
- Glow caveat: real blur effects rasterize per frame. Apply live Qt
  effects only to elements currently transitioning, or fake glow with a
  pre-rendered halo item whose opacity animates. Spike before promising
  glow on tutti textures.
- Scale/pop transforms use the element's stored `anchor` as origin.

## 7. UI structure

Three synchronized views over one `AppState` (document + playhead +
selection + shared time-axis zoom/scroll):

- **StageView**: the paged score at the score's own aspect ratio,
  letterboxed in the window; shows animation state; click-to-select for
  overrides.
- **TempoLaneView**: tempo events as draggable points; shares the time
  axis with the waveform. Swing is a single global ratio set numerically
  on the transport bar in v1 (ruling 2026-07-11); the SwingRegion data
  model is unchanged and per-region authoring returns later (BACKLOG 7).
- **WaveformView**: rendered peaks, playhead, click-to-seek; tap capture
  during playback.

Views never talk to each other — only observe/mutate AppState via signals
and commands. Window orientation (portrait/landscape panel arrangement) is
a QSplitter/dock concern, orthogonal to the stage's aspect.

## 8. Known risks (spike before building on them)

1. Dorico MusicXML → Verovio fidelity with breaks honored — **resolved
   Phase 0**: fidelity accepted by the user 2026-07-10; findings and
   remaining deviations in `spikes/NOTES.md` and `docs/BACKLOG.md`.
2. Verovio SVG decomposition: element granularity, ID coverage,
   identity recovery for stems/beams/spanners (Phase 1). Phase 0
   established: every musical element carries a unique id except
   `notehead` (the single child of its id-bearing `note` group).
3. Qt audio playhead query precision/latency for AudioClock — **resolved
   Phase 3** (spike 2026-07-11, `spikes/audio_playhead.py`): raw
   position() too coarse (50–100 ms cadence); sliding-mean anchored
   extrapolation passes the ≤20 ms band (see §5 and spikes/NOTES.md).
   Absolute output latency remains unmeasured (needs loopback); any
   constant is absorbed by the tempo sidecar's `offset`.
4. Glow performance (deferred; property-bag design accommodates either
   backend).
5. QtSvg (SVG Tiny 1.2) cannot render Verovio SVG (nested <svg> is
   skipped → blank). Constraint, not a blocker: rendering decomposes SVG
   into per-element QGraphicsItems; whole-SVG preview via QtSvg is not
   an available shortcut (verified Phase 0).

## 9. Licensing notes

- PySide6 (LGPL), Verovio (LGPL), music21 (BSD): all fine for a
  distributable app.
- MuseScore is a valuable *reference* for tempo-map and swing modeling.
  It is GPL: study the approach, never copy code.
