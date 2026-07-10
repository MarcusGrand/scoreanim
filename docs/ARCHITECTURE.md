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
#    mm. 3-19 of the test score), which Verovio renders as empty measures
#    and which produce no timemap events. The adapter must synthesize
#    slash elements: one per beat from the time signature, kind = SLASH,
#    staff-positioned, with onsets on the beats, so slash regions render
#    and animate like notes.

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
    keyframes: tuple[Keyframe, ...]     # (t_rel_seconds, value, easing)

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

### Reveal / playhead-x unification

Per system, from the sorted `(onset_beats, x)` pairs of its noteheads
(onsets taken from the timing model, then mapped to x — not derived from
engraved x):

- `reveal_x(system, t, CONTINUOUS)` — piecewise-linear interpolation.
- `reveal_x(system, t, STEPPED)` — x of the latest onset ≤ t.

The whole-system sweep, per-spanner grow (slurs, hairpins: clip-rect right
edge at `reveal_x`), and any cursor all read this one function. Spanners
split across systems by Verovio reveal per segment; segments on
not-yet-current pages sit at reveal = 0.

### Styling

`StyleRules` map musical identity → base visual properties (per-part color,
floor opacity, assigned Effect). Rule-based, sparse; per-element user
overrides are higher-priority rules. Serialized in the project document.

## 4. Project document

```
Project (saved file, versioned schema)
├── score_ref            path + content hash of MusicXML
├── audio_ref            path + content hash of wav/mp3
├── engraving_params     scale etc. (page geometry comes from the score)
├── layout_overrides     {ElementId → dx, dy, hidden}
├── tempo_map            events, swing regions, raw taps (kept for re-derive)
├── style_rules          part colors, effect assignments, overrides
└── stage_config         background, letterbox behavior
```

Never persisted: Layout, timemaps, decomposed geometry — always re-derived.
All mutations go through undoable commands (`core/project/commands.py`).

Override staleness is accepted: after a reflow (e.g. Verovio upgrade),
deltas keyed to musical identity reapply on the new base; some may need
re-touching. "Clear overrides on selection" must be cheap.

## 5. Clocks, sync, drift

- `Clock` interface in core: `now_seconds() -> float` relative to
  transport start, plus transport state.
- `AudioClock`: wraps the audio backend's playhead position query.
  Implemented in render/ui land (it touches Qt multimedia); core sees only
  the interface.
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
- **TempoLaneView**: tempo events as draggable points, swing regions,
  tap markers; shares the time axis with the waveform.
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
3. Qt audio playhead query precision/latency for AudioClock (Phase 3).
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
