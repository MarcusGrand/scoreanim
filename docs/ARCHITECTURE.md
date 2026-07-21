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
    def load(self, score_path: Path, params: EngravingParams,
             groups: tuple[PartGroupSpec, ...] = (),
             texts: tuple[PartTextSpec, ...] = (),
             hide_empty_staves: bool = False) -> Layout: ...
    # `groups` (Phase 8): staff groups injected as <part-group> at the
    # prep seam — engraving INPUTS like the score file itself. A
    # separate argument, NOT an EngravingParams field, because params
    # are serialized in the project document and a groups field there
    # would duplicate doc.staff_groups (rule 5: one source of intent).
    # `texts` (Phase 9.3) and `hide_empty_staves` (Phase 10R) follow
    # the same reasoning (doc.text_overrides / doc.hide_empty_staves).

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
#    Revision AS BUILT (Phase 9, 2026-07-12, resolving BACKLOG item 5):
#    the split is by TEXT CLASS. Stage texts (title/composer/lyricist)
#    edit in place via EditStageText — never re-engrave; the header
#    block re-fits its band in-command (down-only, band supplied by the
#    UI as runtime data). Tempo marks edit as OVERLAY: AddTempoOverlay
#    hides the engraved TEXT element (the first consumer of
#    LayoutOverride.hidden) and adds a replacement stage text
#    (id "stage:overlay:<engraved-id>", seeded from the engraved
#    geometry, SMuFL→♩ substitution) — one undo step; RemoveTempoOverlay
#    restores. Part labels take the prep seam (ruling 6). Only dx/dy of
#    LayoutOverride remain unconsumed.
#
# 6. Part-label overrides via prep rewrite (Phase 9.3, as built
#    2026-07-12): doc-stored text_overrides (user intent) become
#    PartTextSpec at the prep seam and rewrite the part-list BEFORE
#    part extraction — Verovio reads <part-name-display>/-abbreviation-
#    display and ignores the plain elements when twins exist, so the
#    rewrite touches BOTH (plain feeds PartInfo); non-blank overrides
#    clear print-object="no" (it suppresses even non-empty text); ""
#    is an explicit no-label. The label column re-derives so the score
#    shifts to fit — a re-engrave with changed inputs, not window
#    reflow (rule 7). A rename keeps the id set IDENTICAL (pinned:
#    tests/test_adapter_part_texts.py); adding a FIRST abbreviation to
#    a part that had none appends label ids (accepted limit — labels
#    are static TEXT, never animation targets). Tempo/label/etc. TEXT
#    sub-classing rides RenderedElement.text_class — presentation
#    metadata; ElementIdentity and minted ids untouched.
#
# 7. Hide empty staves (Phase 10R, as built 2026-07-13, rule-7
#    amendment b): Verovio honors hidden empty staves ONLY via MEI
#    scoreDef@optimize + condense:"encoded" (staff-details
#    print-object and staffDef@visible are ignored; MusicXML carries
#    no hidden-staff info from Dorico). The adapter runs a TWO-PASS
#    load when doc.hide_empty_staves is on: loadData(MusicXML) →
#    getMEI() → set optimize="true" on the first scoreDef → fresh
#    toolkit → loadData(MEI). The round-trip is id- and
#    timemap-transparent (pinned; spikes/NOTES.md Phase 10R).
#    systemDivider:"none" is a fixed option (condensed layouts draw
#    dividers by default; Dorico's look has none — SYSTEM_DIVIDER
#    decomposer support stays as defense). Slash regions WIN over
#    hiding (rule 10): if a slash-region staff would vanish, the load
#    redoes flat with LoadWarning "hide-unavailable".
#
# 8. Never-clip repagination (Phase 10R, as built 2026-07-13, rule-7
#    amendment a): after every engrave the adapter measures system
#    bands against the page height; on overflow it re-derives page
#    breaks (greedy pack from measured heights + margins, 2% drift
#    pad — core/engraving/systems.plan_page_breaks), strips encoded
#    new-page attributes, injects <print new-page="yes"> at the chosen
#    system starts (part 1 only) at the prep seam, and re-engraves
#    once. Breaks are DERIVED data — recomputed every load, never
#    stored (rule 5). Page-scoped ids (score:p{n}:…) shift; musical
#    ids are pagination-independent. LoadWarning "repaginated".
#
# 9. Load warnings (Phase 10/10R, ruling b): non-fatal anomalies are
#    NEVER silently absorbed — EngravedScore.warnings carries
#    LoadWarning(code, message) in musical coordinates only (rule 4):
#    dropped-spanner (engraver emitted no ink), implausible-tie (a tie
#    force-matched to a distant note — extent > 2× its start measure —
#    is suppressed with its continuation ink; the Phase 10R m44 fix),
#    segment-count-mismatch / unattributed-continuation (tolerant
#    continuation pairing), hide-unavailable, repaginated,
#    system-overflow, unknown-class (a drawable SVG class the decomposer
#    does not know, rendered as a static element — Phase 11.4, app path
#    only), stray-path (a path re-homed out of a cross-system element —
#    item 11 below). The status bar shows the count; stderr the text.
#
# 10. Dorico-robustness decomposer coverage (Phase 11, as built
#    2026-07-19): three notation classes and one geometry gap that the
#    prior fixtures never exercised. (a) TREMOLO — a bowed/measured
#    tremolo's stroke <use> is a DIRECT child of the id-bearing
#    <g class="bTrem|fTrem">, so the class EMITS its own element (a
#    container would fold the stroke into the static staff scaffold, the
#    BACKLOG-6 shape); the element inherits its child note's onset
#    (chord-member style) and animates untinted (ruling a), the nested
#    note keeping its own timemap onset. fTrem is defensive (neither
#    fixture draws one — all tremolos are bTrem). (b) beamSpan → BEAM
#    with onset/extent from MEI @startid/@endid (a measure-level beam is
#    not in the layer-beam table). (c) rotate transforms: Verovio DOES
#    rotate (vertical text carries rotate(-90 …)), so svg_geom parses
#    rotate into the affine matrix and Affine.apply_rect maps by four
#    corners (exact for 90-degree multiples, reduces to the old
#    two-corner result when axis-aligned). (d) the ledger rest tier
#    (Phase 10.2) also claims displaced mRests. Graceful degradation
#    (ruling, Marcus 2026-07-15): in the app path an unknown drawable
#    class no longer fails the open — it mints a static OTHER element +
#    unknown-class warning; strict loads (pytest / doctor --strict)
#    still raise so coverage gaps stay loud. The score-doctor
#    (scoreanim.tools.check_score) is the triage engine.
#
# 5. Staff groups via prep injection (Phase 8, as built 2026-07-12):
#    doc-stored groupings (staff_groups, user intent) become
#    PartGroupSpec at the prep seam and are injected as <part-group>
#    into the canonical MusicXML before Verovio. Verovio then renders
#    the bracket (grpSym → ElementKind.GROUP_SYMBOL, static ink,
#    part-span-keyed ids: score:sys{n}:grpsym:P1-P2) and joins barlines
#    through the group itself — connector segments fold into the
#    existing barLine groups, so the decomposer needs no connector
#    handling and render-side synthesis (which would reimplement
#    engraving collision avoidance) stays rejected. Musical ElementIds
#    are pinned stable across the grouped re-engrave
#    (tests/test_adapter_groups.py) even though every VEROVIO id
#    re-rolls on any input change despite the fixed seed — which is
#    exactly why identity is minted from musical position, not ids.
#
# 10 (Phase 12). Orchestral robustness (complex2). Four pieces:
#    (a) ORDER-BASED JOIN (12.1): the model↔layout match keys plain notes
#    on PITCH only and pairs by document order within (part, measure,
#    staff, voice) — onset is NOT in the key, because Verovio's timemap
#    delays a note after an appoggiatura by the grace's duration while
#    music21 keeps the notated beat. Triggers keep the Verovio qstamp
#    (performance time — the note lights when it sounds; ruling a). A
#    bounded cross-staff fallback re-matches leftovers within (part,
#    measure) across staves for multi-staff parts (complex2's Synth).
#    (b) BAR-REPEAT SYNTHESIS (12.2): Verovio draws nothing for
#    <measure-repeat> (empty <space>), so the adapter synthesizes one
#    ElementKind.BAR_REPEAT % symbol per repeated bar (onset on the
#    downbeat), the slash-region shape (rule 10). (c) CONDENSING (12.3):
#    doc-stored condense_groups (PartCondenseSpec at the seam) merge
#    contiguous like parts onto one staff, one voice per player, behind a
#    <backup> — a canonical rewrite BEFORE Verovio (rule 11); v1 naive,
#    no a2/divisi. ElementIds shift (part identity is an engraving input).
#    (d) SCALE-TO-FIT (12.5): when a single system is taller than its page
#    after repagination (Dorico sized the page for its condensed score),
#    the adapter scales the engraving down uniformly (Verovio `scale`
#    option) so the tallest fits — the never-clip completion, rule-7
#    amendment c (`LoadWarning "scaled-to-fit"`). complex2 renders at 54%,
#    zero overflow. The Score Setup dialog (§7) gathers condense/bracket/
#    hide as ONE undoable batch (ApplyScoreSetup).
#
# 11. Cross-system stray-path re-homing (as built 2026-07-21, bigband1).
#    The per-(system, part) reveal edge assumes an element's ink lies
#    within its attributed system. Under hide-empty-staves the
#    scoreDef@optimize round-trip makes Verovio REUSE one xml:id across
#    element types and emit a LATER system's tie/slur/artic curve as a
#    bare <path> INSIDE an EARLIER note's <g class="stem|flag|artic">
#    whose id collides — the deeper manifestation of the Phase 10R
#    id-reuse hazard (which _identity_for already gates for ONSET). The
#    decomposer used to absorb that path into the early element, so at
#    its reveal time the curve painted down in the later system (a
#    solid-black "tie" bars ahead of the playhead once the ghost floor
#    is 0). _rehome_stray_paths (post-decompose, before ledger/spanner
#    attribution) partitions each page into per-system vertical strips
#    (staff bands split at inter-system-gap midpoints) and, for any
#    element whose bbox straddles a boundary, splits each foreign-system
#    path into its OWN element attributed by GEOMETRY to the system it
#    occupies. Re-homed as a reveal-clip TIE (onset-less, edge-driven)
#    when a staff/part underlies the ink — so it grows in with the
#    playhead sweep at its own x, never popping at the system downbeat —
#    else a measure-start OTHER (no reveal curve to ride; still cannot
#    leak). No ink dropped (rule 7); LoadWarning "stray-path" per
#    re-homed element (ruling b). A no-op on well-formed scores (only a
#    straddling bbox is examined); across testdata only bigband1 and
#    video_test (a system-14 hairpin path in the id-colliding system-13
#    group) fire.

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
    text_class: str | None       # TEXT sub-class ("tempo"/"reh"/"label"/…,
                                 # Phase 9) — presentation metadata; ids
                                 # untouched. None for non-TEXT elements.

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

### Animated-ink taxonomy — a DENYLIST (revised 2026-07-12; Phase 10R 2026-07-13; inverted 2026-07-20)

**Animation is a denylist, not an allowlist** (ruling 2026-07-20).
EVERY object on the page animates with the appear/effect system EXCEPT
the true scaffold; a new `ElementKind` is animated *by default*. The
allowlist that preceded this shipped every new kind static-until-someone-
remembered — the exact mechanism behind the recurring coverage gaps —
so the default is inverted. `schedule.STATIC_KINDS` is the single
authority; `ANIMATED_KINDS` is derived (`all kinds − STATIC_KINDS −
REVEALED_KINDS`) and the adapter imports `STATIC_KINDS` to decide which
kinds to mint onset-less.

The **scaffold** (static, onset-less) is exactly: **staff lines,
barlines** (including the system-left barline joining a system's
staves — reclassified from OTHER), **group symbols/brackets, and
between-system dividers** — plus **page furniture** (part labels,
page header/footer, measure numbers), which the adapter mints
onset-less via `_STATIC_TEXT_CLASSES` so the onset gate excludes it
without a distinct kind. Everything else is animated ink.

**Clefs and key signatures MOVED from static to animated** with this
ruling; tuplet brackets/numbers, ornaments, and degraded `OTHER` ink
(the Phase 11 graceful-degradation path) animate too. Opacity-triggered
(dim at floor, light at trigger): noteheads, slashes, **synthesized
bar-repeat `%` symbols (Phase 12.2, one per repeated bar, tinted like
slashes)**, stems, flags, beams, accidentals, articulations, tremolo
strokes, dots, ledger dashes, rests, whole-bar rests, dynamics, texts,
chord symbols, lyrics, meter signatures, clefs, key signatures, tuplets,
ornaments/fermatas — every object at its onset. Resolution order: owner note (stems/flags/
accidentals — and **tuplet brackets/numbers and tremolo strokes, which
inherit their notes' first onset so they light WITH the tuplet/tremolo,
not at the downbeat**; bug fix 2026-07-20) → @startid note (chords via
their first member) → @tstamp arithmetic → **measure start** (the last
resort, for genuine bar-level objects: clefs, key signatures, meter
changes, and measure-attached texts/dynamics). Note-region decorations
never use the measure-start fallback, and spanners (slurs/ties/hairpins)
are excluded from it entirely — a spanner's timing is its start note or
nothing. **A rest is
retrospective ink** (ruling 2026-07-12, second session): it triggers
when its silence resolves — at the next note in its part/voice or the
end of its own bar, whichever comes first, never on its own silent beat
(a whole-bar rest completes at its barline). Reveal anchors follow the
same triggers, so the edge never advances mid-silence.

Clip-revealed (opacity pinned 1.0, animated by the reveal EDGE not the
opacity trigger — so `is_animated` excludes them): slurs, ties,
hairpins. **Animation scope ≠ color scope** (ruling D stands): this
ruling widened what animates, not what tints — `TINTED_KINDS` is
unchanged, so clefs and key signatures animate but stay black.

### Styling

`StyleRules` map musical identity → base visual properties (per-part
color + effect assignment, reveal mode). Rule-based, sparse; per-element
user overrides are higher-priority rules, merged field-wise. Serialized
in the project document. StyleRules SUBSUMED Phase 2's `StyleConfig`
(Phase 5.3) — one styling system: the tint menu drives part color
rules; effect names are stored intent resolving against the preset
registry (unknown → default, the name round-trips untouched). The
element-override editing UI waits on stage click-to-select (BACKLOG 9).
**The ghost floor is a StyleRules field since Phase 7.2**
(`floor_opacity`, document intent, 0 allowed): built-in presets are
built from it (`presets.build_presets(floor)` — the registry stays
data, rule 6), spanner ghosts re-dim through
`ScoreScenes.set_ghost_opacity`, and both live and export read the
same value through the one StyleRules path (`presets.FLOOR_OPACITY`
remains only as the default). Static scaffold never dims — it never
enters the trigger schedule, so floor 0 means invisible unrevealed ink
on a fully visible staff. **Color scope ≠ animated scope** (ruling D):
`TINTED_KINDS` = the playing ink (heads through ledger dashes, plus
slurs/ties/hairpins) — rests and dynamics animate but stay black, like
clefs, signatures, and text.

## 4. Project document

```
Project (saved file, versioned schema)
├── score_ref            path + content hash of MusicXML
├── audio_ref            path + content hash of wav/mp3
├── engraving_params     scale etc. (page geometry comes from the score)
├── layout_overrides     {ElementId → dx, dy, hidden} — hidden consumed
│                        since Phase 9.2 (tempo overlays); dx/dy still
│                        unconsumed schema slots
├── tempo_map            events, swing regions, raw taps (kept for re-derive)
├── style_rules          reveal mode, floor opacity (v3), per-part
│                        {color, effect-name} rules, per-element overrides
├── stage_config         presentation mode (paged | system, v3), header
│                        text elements (title/composer/lyricist —
│                        stage-level text, not engraved; adapter ruling 4)
│                        plus tempo-overlay replacements
│                        (stage:overlay:<engraved-id>, Phase 9.2)
├── staff_groups         consumed since Phase 8 (v3): ordered groups of
│                        contiguous parts + symbol + joined-barlines flag
│                        (bracket geometry re-derives via prep injection;
│                        adapter ruling 5)
├── text_overrides       consumed since Phase 9.3 (v3): per-part
│                        name/abbreviation edits, rewritten into the
│                        part-list at the prep seam (adapter ruling 6)
├── hide_empty_staves    v4 (Phase 10R): per-score bool, default ON for
│                        new documents; the hidden layout re-derives
│                        via the MEI optimize round-trip (adapter
│                        ruling 7); rule-7 amendment b
└── condense_groups      v5 (Phase 12.3): contiguous like parts merged
                         onto one staff (one voice per player, combined
                         label); the merged part-list re-derives at the
                         prep seam (adapter ruling 10); CLAUDE.md rule 11
```

Schema versions (`core/project/serialize.py`, strict gate): **v1**
(Phase 4) had `style.part_colors`; **v2** (Phase 5.3) is the StyleRules
shape above; **v3** (Phase 7.1) added floor_opacity, presentation mode,
staff_groups, and text_overrides in ONE bump — every planned v2-era
field designed at once, no per-phase bumps; **v4** (Phase 10R) added
hide_empty_staves, VERSION-GATED on read: v≤3 files predate the option
and load OFF so their look is unchanged, while new documents default
ON; **v5** (Phase 12.3) added condense_groups (no read gate needed — a
missing key defaults to (), the correct look for older files). The
reader accepts {1, 2, 3, 4, 5}: v1 `part_colors` folds into part
color rules, older files default newer fields per-field (no migration
code — they just lack the keys); the writer emits 5. The gate is
strict-by-version ON PURPOSE: an older build REFUSES a newer file
instead of tolerantly reading it, silently dropping fields, and
destroying them on the next save. Effect names are stored intent — an
unknown name fails soft to the default preset at animation time but
round-trips untouched (rule 5).

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
- `WallClock` (ui/wall_clock.py, FIX 2 as built 2026-07-20): the live
  clock for **no-audio playback**. `now = anchor_position +
  (perf_counter() − anchor_wall)` — anchored on play, frozen on pause,
  re-anchored on seek; a pure function of the wall source, no `t += dt`
  (rule 2). Qt-free (headless-testable via an injected `now`). The
  `PlaybackController` reads it instead of the AudioClock whenever
  `transport.has_media()` is false, with the audio offset simply 0 and
  the tempo map (default 120 bpm, sidecar, taps, or the transport BPM
  spinbox — all the existing tempo-map machinery) setting the pace; the
  no-audio timeline length is the score's own duration through the same
  `resolve_seconds` seam as triggers. The controller is the single
  bridge, so its `playing_changed`/`duration_changed`/`time_changed`
  signals are identical across both clock sources. **AudioClock remains
  master whenever audio is loaded** (rule 3). Export is unchanged and
  already audio-independent (FrameClock below): a no-audio export uses
  offset 0 and the score-length duration, verified not rebuilt.
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
- **System-mode export** (Phase 7.5): when the document's presentation
  mode is SYSTEM, the canvas is user-chosen (W×H, default 1920×1080,
  dialog-editable, still session memory — R3 stands) and each frame
  composites the current system's band — cropped from its page scene
  — CENTERED both axes, scaled to fit preserving the band's aspect,
  under an explicit clip rect (the bleed guarantee). Cuts land on the
  frame `current_system()` changes — the same applier walk as live
  follow (R2 extended to systems; `current_system()` is the
  `current_page()` bisect idiom over `Trigger.system`, stamped by the
  schedule with the same min-fresh rule as page). Band geometry is
  `core/engraving/systems.py::system_bands` — pure, derived from the
  Layout on demand, never persisted. The paged path runs verbatim
  behind a guard: a paged export is byte-identical to Phase 6, pinned
  by the unmodified Phase 6 test suite. The export dialog reads the
  mode from the live document at open, never from `AnimationInputs.
  stage` (a load-time snapshot that goes stale after a mode command).
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
  overrides. System-at-a-time mode (Phase 7.4, document intent
  `stage.mode` + `SetPresentationMode` + a transport toggle): frames
  the current system's band centered — a hard cut via the same
  setScene page-flip mechanics — with a `drawForeground` override
  painting letterbox color over everything outside the band, so a
  same-page neighbour system never bleeds in at any window aspect.
  View-level on purpose: export scenes structurally cannot see the
  mask. Follow emits page AND system; the window routes by mode;
  prev/next step the current presentation unit. Paged stays default.
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
