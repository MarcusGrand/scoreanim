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
    CONTINUOUS = auto()          # lerp x between onset positions (sweep)
    STEPPED    = auto()          # step function; jumps at musical onsets

@dataclass(frozen=True)
class Envelope:
    initial: float                      # value before the first keyframe
    keyframes: tuple[Keyframe, ...]     # (t_rel_seconds, value, easing)
    # `initial` added by Phase 3 ruling (2026-07-11): "floor before
    # onset" is inexpressible with finite keyframes under hold semantics.

@dataclass(frozen=True)
class Effect:
    name: str                    # "appear", "pop", "glow_pulse"
    tracks: Mapping[PropertyId, Envelope]

# Open property set. v1 properties: opacity, color, reveal_fraction,
# scale, offset_x, offset_y, glow. Adding a property must not require
# touching the evaluator.

def element_state(identity, style_rules, effects, tempo_map, t_seconds
                  ) -> Mapping[PropertyId, Value]:
    """Pure. No hidden state, no timers, no accumulation. Same function
    serves AudioClock playback, scrubbing, and FrameClock export."""
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
(ruling B); dynamics animate at their attach point but are attachments,
not events. Edges are per part so one part's tie holds only its own
spanners (known limit: per part, not per voice — voice labels relabel
per measure).

Per-spanner grow (slurs, ties, hairpins: clip-rect right edge at
`reveal_x`) and any cursor read this one function. Spanners split
across systems by Verovio reveal per segment; segments in
not-yet-reached systems sit at reveal = 0 with no page logic.

### Animated-ink taxonomy (revised 2026-07-12)

Opacity-triggered (dim at floor, light at trigger): noteheads, slashes,
stems, flags, beams, accidentals, articulations, dots, ledger dashes,
**rests, whole-bar rests, dynamics** (ruling B — everything IN the
staves animates; a dynamic's trigger is its attach point). Clip-revealed
(opacity pinned 1.0): slurs, ties, hairpins. Static: clefs, key/time
signatures, barlines, staff lines, texts, lyrics, chord symbols.

### Styling

`StyleRules` map musical identity → base visual properties (per-part
color + effect assignment, reveal mode). Rule-based, sparse; per-element
user overrides are higher-priority rules, merged field-wise. Serialized
in the project document. **Color scope ≠ animated scope** (ruling D):
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
├── style_rules          part colors, effect assignments, overrides
└── stage_config         background, letterbox behavior, header text
                         elements (title/composer/lyricist — stage-level
                         text, not engraved; adapter ruling 4)
```

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
- `FrameClock`: `now = frame_index / fps`. Export walks frames, evaluates
  `element_state`, renders offscreen (transparent background for overlay),
  hands frames to the encoder. Deterministic by construction; drift is
  impossible in export.
- Rule 2 in CLAUDE.md (no time accumulation) exists because accumulated
  `t += dt` drifts over minutes-long pieces; absolute queries do not.

## 6. Rendering & performance model

- Load time (expensive, once): parse, engrave, decompose SVG into
  per-element `QGraphicsItem`s with identity, build indexes
  (onset-sorted per system; per-part; spanner list).
- Per frame (cheap): update only elements whose state changes — those
  inside a transition window around the playhead — plus one clip-edge move
  per active spanner. Target 60 fps on a dense page.
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
