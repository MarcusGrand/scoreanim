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
   ├──► ScoreModel (music21 + the engraved MeasureTimeline)
   │        notated identities; ALL beats rebased onto the timeline
   │        (CLAUDE.md rule 12 — build_score_model REQUIRES it)
   │
   └──► EngravingProvider (Verovio)   id → position/geometry per page
              │  + MeasureTimeline (timemap qstamps — THE beat axis,
              │    performance/playback-expanded time)
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

# The adapter is a package (Phase R, 2026-07-22), one module per
# pipeline stage — core/engraving/verovio/:
#   kinds.py        policy tables only (class→kind map, container/spanner
#                   sets, scale constants); no logic
#   mei_index.py    Verovio's MEI export → per-id musical lookup tables
#   records.py      AdapterNoteRecord, EngravedScore, _LoadState (the
#                   per-load shared state; each stage module's docstring
#                   lists the fields it reads/writes)
#   decompose.py    one page SVG → identity-bearing element accumulators
#   attribution.py  in-place post-passes: rehome strays, ledger dashes,
#                   spanner segments, implausible ties
#   label_parts.py  the part-label → staff join (obligation 17) and the
#                   one post-pass that writes acc.staff, run last
#   identity.py     ElementId minting + the svg_class-gated onset chain;
#                   accumulators → RenderedElements + note records
#   synthesis.py    slash / bar-repeat synthesis (rule 10)
#   provider.py     toolkit options, hide/repagination/scale-to-fit retry
#                   loops, and _engrave_prepared — the ONE function that
#                   names the pipeline order:
#
#   engrave → parse MEI → timemap → decompose pages → rehome strays →
#   attribute ledger dashes → attribute spanner segments → flag
#   implausible ties → attribute part labels → build elements →
#   synthesize slash/repeat
#
#   The order is a correctness invariant: rehoming must precede the other
#   attribution passes (they must never claim ink that is about to move),
#   implausible-tie flagging must follow segment pairing (bogus sources
#   stay in the candidate pool so the remaining segments pair right),
#   label attribution runs last of the passes because it is the only one
#   that WRITES acc.staff while the others read it, and
#   synthesis follows element construction (it positions from the
#   collected staff geometry; synthetic elements never enter the passes).
#   tests/goldens/ pins 12 fixture loads byte-for-byte (the Phase R
#   safety net, kept as the standing regression suite).

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
#
# 12. Measure identity is the 1-based DOCUMENT-ORDER ORDINAL, never the
#    printed measure number (fix 2026-07-21, complex3). The printed number
#    is not unique or consistent: Dorico exports pickup/split bars as
#    non-numeric "X0"/"X1", which music21 parses to 0 while the DOM/MEI keep
#    the string — so the pickup collides with real bar 1 (both key 1) and
#    the two sides disagree. The k-th <measure> is the SAME bar in music21,
#    the MusicXML DOM and Verovio's MEI (verified 1:1 across every fixture,
#    incl. multi-measure rests, the hide-empty-staves round-trip, repeats),
#    so the ordinal is the one safe key. Every identity dict keys by it —
#    measure_by_id (xml:id→ordinal), system_of_measure, measure_start,
#    measure_duration, meter_unit_by_measure, ScoreNote.measure /
#    AdapterNoteRecord.measure (the join key), slash/repeat region bounds,
#    _repaginate page-break bars, and the ElementId ":m{ordinal}:" segment.
#    The PRINTED number survives only as display: MeasureInfo.number and the
#    tempo/export/measure-label UI. Consequence: for a score not starting at
#    printed bar 1, ":m{n}:" ids shift, so saved dx/dy layout overrides on
#    such a project (which already collided pre-fix) will not re-match — an
#    accepted one-time break (rule 5 override staleness).
#
# 14. The engraved MeasureTimeline is the app-wide beat authority
#    (ruling 2026-07-22, FINDING-1 fix; CLAUDE.md rule 12). The provider
#    exposes EngravedScore.timeline: per-ordinal measure starts (first
#    timemap qstamp) and durations (delta to the next FIRST-PASS
#    downbeat), plus score_end — with a loud load-time invariant that
#    every MEI measure ordinal has a timemap start. The timemap is
#    playback-EXPANDED: a repeat's later passes appear as clone measure
#    ids ("…-rend<k>") which the measure_by_id guard drops by design —
#    repeated measures keep first-pass positions, the next new measure
#    starts after the full expansion, and the axis is therefore
#    PERFORMANCE time (what a recording that takes the repeat plays).
#    build_score_model rebases music21's accounting onto this timeline;
#    music21's own inter-measure accumulation is untrustworthy on real
#    Dorico exports (spikes/beat_domain.py census: X0 pickups padded to
#    nominal length, repeats never expanded, half-beat bars rounded
#    down — complex2 m8/m120 — and per-part self-divergence, complex3
#    part 0 drifting +7.75 by m78). One nominal-length survivor: a
#    trailing event-less bar (final bar-repeat) has no timemap end, so
#    the LAST measure's span is floored with its notated length.
#    The golden suite pins the timeline per fixture (measure_timeline
#    section, 2026-07-22 re-capture).
#
# 15. Courtesy sigs light with their change measure (FINDING-4 fix,
#    2026-07-23). Verovio nests an end-of-system courtesy key/meter/clef
#    restatement in the SVG measure group of the system's LAST measure m
#    while the change it announces takes effect at m+1 (the next
#    system's first bar) — so the measure-start fallback lit it a bar
#    early. The adapter retimes it: for a SIG_KINDS glyph whose nesting
#    measure m is the last of its system (from system_of_measure — the
#    element-free measure-group nesting map, immune to the :seg ordinal
#    hazard), is NOT itself a change measure for its (kind, part), and
#    where m+1 IS one, onset = measure_start[m+1]. Change measures per
#    (kind, part) parse from the canonical MusicXML <attributes>
#    (provider._sig_change_measures → _LoadState.sig_changes); the
#    live-oracle keeps an independent copy of that parse as arbiter.
#    The element id keeps ":m{m}:" (drawn-position identity; onset is
#    timing) and no LoadWarning fires (a courtesy is normal engraving).
#    In-place changes and system-start restatements nest in their own
#    measure and are untouched; a sig matching neither shape stays a
#    loud D2 sig-nesting finding. Known limit: a courtesy drawn in a
#    measure that is itself a system START (old-sig restatement at left
#    + courtesy at right in one measure) is indistinguishable without
#    geometry and is not retimed — no fixture exercises it.
#    Consequence in the schedule: a DISPLACED sig — onset not equal to
#    its own drawn measure's start, i.e. a retimed courtesy — is
#    excluded from a trigger's FRESH page/system hint sets
#    (schedule._displaced_sig, over SIG_KINDS): it is fresh (its onset
#    IS the retimed beat) but drawn on the previous page, and would
#    otherwise drag the min() hint back and delay the page turn past
#    the change downbeat. A sig lighting at its own drawn downbeat
#    still drives hints — system-start restatements are the ONLY fresh
#    elements at rest-heavy system starts (bigband1 m9, complex2 m48),
#    so a blanket sig exclusion would hint the previous system there.
#    Sigs light where drawn; the view follows the music.
#
# 13. Continuation-segment attribution keys by the START-note staff
#    (fix 2026-07-21, complex3). A system-broken spanner continues on its
#    start staff; _attribute_spanner_segments pairs each continuation
#    segment to a crossing source in (staff, end_y) order. The staff must be
#    the source's START-note staff — reliable even when the end note has no
#    drawn accumulator (common under hide-empty-staves: 69 such sources in
#    complex3). Keying by the end-note staff collapsed those to 0, sorting
#    them degenerately and handing a segment the wrong source → a slur
#    painted on another part's staff and revealed on that part's advanced
#    edge (the phantom-slur family, sibling to item 11). See
#    tests/test_phantom_slur.py.

# 16. Scene parents are HIT-TRANSPARENT (M2.3, 2026-07-25). GroupItem
#    (hence every ElementItem) overrides shape() to return an empty
#    QPainterPath. Qt's default shape() is boundingRect() as a path and
#    ours is childrenBoundingRect(), so without the override a parent
#    answers a click anywhere in its children's united bbox — a
#    STAFF_LINES element spans its whole system, so it was a candidate
#    for every click on the page (measured: a notehead click also
#    returned the staff lines and the part label). Children are stock
#    QGraphicsPathItem/SimpleTextItem whose own shape() includes the pen
#    stroke, so thin stems and staff lines stay clickable through them,
#    and the selection controller walks child -> parent to recover
#    identity. Painting is unaffected — paint() is empty and
#    boundingRect still reports the true extent — and the golden suite
#    is byte-identical across the change.
#
# 17. Part labels reach their part by DOCUMENT ORDER, self-checked (M7,
#    2026-07-30; CLAUDE.md rule 13 amendment). A label is the one object
#    the id grammar cannot carry a part for: Verovio draws it as a child
#    of the system with no staff ancestor and no MEI @staff, and its SVG
#    id does not exist in the MEI at all (measured 0/129,
#    spikes/label_part.py — the M3 id-join hypothesis is dead). What
#    works, and is exact on every fixture: pair the labels a system draws
#    against the MEI labels of the class being drawn, in order, filtered
#    to the staves visible on that system. The filter is load-bearing —
#    a part with no abbreviation draws NOTHING after system 1, and naive
#    order without it is 101/129 and MIS-ATTRIBUTES rather than failing.
#    Two hosts, two tiers: an ordinary part's label hangs on its
#    <staffDef>, a MULTI-STAFF part's on the <staffGrp> around its
#    staves, and Verovio draws every group label FIRST (measured 41/41,
#    spikes/label_group.py), so group labels lead and staff labels
#    follow. Plain staff order is kept as a second candidate and the
#    label TEXT decides between them. Every pairing is confirmed against
#    the text the MEI carries, so a label the join will not vouch for
#    keeps part=None: the failure mode is a disabled rename, warned
#    ("label-unattributed"), never a renamed wrong instrument.
#    The pass (core/engraving/verovio/label_parts.py) runs LAST among the
#    post-passes because it is the only one that WRITES acc.staff, and it
#    writes nothing else: _identity_for already derives part/part_name/
#    part-local staff from acc.staff, and the label's ElementId is
#    unchanged (the part-bearing id form needs a measure, which a label
#    has none of). So the goldens moved in exactly three fields on label
#    rows — part, part_name, staff — with no id, geometry or onset
#    change. Labels also stay STATIC: the onset gate is
#    _STATIC_TEXT_CLASSES by svg_class, not part.

# Followed page/system (render/animate.py) is MONOTONIC non-decreasing over
# the time-ordered triggers (prefix-max): the view never turns backward
# while the clock advances. A per-trigger page/system is only a hint —
# schedule.py aggregates each beat bucket with min(), and tie/rest/group
# retiming plus sub-beat bucket-merging across a system break can dip it
# N, N-1, N; without the clamp _follow_position turns the page back and
# forward on every such dip. A genuine backward SEEK still resets (the
# bisect cursor moves earlier into the monotone array). Assumes v1's linear
# through-composed playback (no repeat/D.S.-driven backward follow).

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
    or, per region, act as hard anchors (dense events).
    Positions are PERFORMANCE-AXIS beats (CLAUDE.md rule 12): every
    producer (sidecar m<n> anchors via MeasureInfo.start, taps,
    triggers, export ranges) lives on the engraved timeline, so beats
    and seconds share one domain end to end."""
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
    # M4 (2026-07-25): scalar DATA the applier consumes generically —
    # never branched on by name (rule 6 amendment).
    trigger_shift: float = 0.0        # "Peak offset": signed seconds the
                                      # WHOLE effect moves vs its trigger
    settle_to_note_value: bool = False  # stretch settle to each element's
                                        # own engraved duration

# Open property set; the evaluator never branches on a property.
# Applied today: opacity (ElementItem parent), scale (around a pivot and
# under a ceiling, both pure policy — see below). REVISED from the
# original sketch (Phase 5 as built): reveal is NOT a property track —
# it is the clip edge driven by reveal_x below — and color is static
# tint (StyleRules), not an animated track. offset/glow remain unbuilt.

# As built (Phase 5.3; timescale/shift M4): the pure kernel stays
# minimal —
#     element_state(trigger_seconds, effect, t_seconds, timescale=1.0)
#     = effect.state_at((t − trigger − effect.trigger_shift) / timescale)
# The shift is absolute seconds (applied before the division, so
# ±100 ms means ±100 ms regardless of note length); the timescale is a
# per-element scalar the applier resolves (engraved duration in seconds
# over the effect's authored duration — durations.py, rule 12's one
# axis). identity → effect resolution happens OUTSIDE it
# (StyleRules.resolve — element > part > document default — + the
# preset registry built from (floor, effect_params), cached in the
# applier), and beats → seconds for all triggers/anchors/duration ends
# goes through one swing-aware resolve_seconds call. No hidden state,
# no timers, no accumulation; the same kernel serves AudioClock
# playback, scrubbing, and FrameClock export.

# Effects that run together (2026-08-01): one element may animate with
# SEVERAL effects at once. The stored intent stays ONE name, the parts
# joined by "+" ("drop+fade"), so the document and its schema are
# untouched and a part this build does not know is skipped while the
# rest still runs (presets.split_effect_name / effects_for). Envelopes
# are NEVER merged — two eased curves cannot be merged exactly at their
# keyframes — so each part keeps its own tracks, its own trigger_shift
# and its own timescale, goes through the kernel above on its own, and
# the RESULTS combine property by property:
#     combined_state(trigger_seconds, ((effect, timescale), ...), t)
# The combining table is data too (core/animation/compose.py): opacity
# takes the MIN (not a product — every opacity envelope starts at the
# document floor, and a product would put a combined ghost below it),
# scale multiplies, the two offsets add. A part that carries no track
# for a property contributes that property's neutral. Every operation
# is commutative, so the order of the parts never matters.

# What a SCALE turns around, and how far it may go (2026-08-01, revising
# the 2026-07-31 "a scale moves the whole note" ruling). Both are pure
# policy, decided once per load and carried on the item; the applier
# only applies (render/properties.py).
#   core/animation/scale_groups.py — the pivot. Every notehead swells
#     about its OWN centre, so it grows where it was engraved; a chord's
#     heads used to share one point and slid sideways as they grew. The
#     ink hanging off a note follows the head it belongs to: a stem
#     stands on the head at its foot, a flag and tremolo strokes ride
#     the stem, an accidental or dot turns around the nearest head.
#     BEAMS and LEDGER LINES never scale — a beam belongs to several
#     notes at once, so any pivot for it is a compromise. No pivot, no
#     scale, which is also how a cross-staff beam with no head in its
#     group stays out of it.
#   core/animation/stem_caps.py — the ceiling. A stem grows towards its
#     beam, and the beam no longer moves, so an unchecked stem would
#     push through it. Each beamed stem carries the largest scale that
#     keeps its tip inside the beam (a geometric join, like ledger
#     dashes finding their note). Measured on testscore, that leaves
#     about 3% of length, so a beamed stem thickens where a flagged one
#     pops with its head. Two traps, both paid for once (2026-08-01):
#     a beam is measured on its drawn OUTLINE at the stem's own x, never
#     by its box — most beams are tilted, and a tilted box reaches far
#     above its own ink at the low end of the slant; and a beam is this
#     stem's only where the stem's tip is drawn INSIDE its ink, because
#     a looser test let the beam one staff up claim an unbeamed stem.
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

**Grow-with-playhead** (ruling A/B REVISED 2026-07-22, complex3): a held
note FILLS IN with the playhead. Every notehead — including a tie
'stop'/'continue' — fires at its OWN notated onset, so the reveal edge
sweeps across a held note's re-notated barline noteheads with the
playhead and the tie ink over them grows left-to-right; a broken chain
reveals each side with its own system's playhead. Ties do NOT anchor the
edge (they clip-reveal against it). The prior "a tied chain is one
event" rule carried the chain-start trigger and folded each tie's
furthest x onto it, so a 14-beat held note's tie painted to the system's
end at once while the playhead was mid-system (the complex3 Oboe/
Clarinet phantom). Scrubbing into a held note now lands it filled-in up
to the playhead (the audio position); the default "appear" effect is an
opacity fade, so a continuation REVEALS rather than re-attacks. Events
are noteheads, slashes, **and rests** (ruling B) — a rest still keeps its
retimed trigger (the edge must not advance at a silent beat): its
trigger is when its silence resolves,
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
logic. Any cursor reads this same function. **The clip default is
HIDDEN** (FINDING-2 fix, 2026-07-22): a reveal child constructs fully
clipped (`-inf`) and only an arriving edge reveals it, so a revealed
item whose (system, part) key matches no reveal curve fails safe as
invisible ink over its floor ghost instead of painting from t=0; the
applier warns loudly per uncovered key at construction
(`reveal warning [curve-less-key]`, `uncovered_reveal_keys`), and the
live-oracle's D3 pins that such items stay hidden at every t.

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
changes, and measure-attached texts/dynamics). One refinement inside
the measure-start fallback (FINDING-4 ruling 2026-07-23): a sig
(clef/key/meter, `schedule.SIG_KINDS`) drawn as an **end-of-system
courtesy** — nested in a system's LAST measure while its change takes
effect at the next measure — lights WITH the change measure
(`onset = measure_start[m+1]`), not at its drawn position; see adapter
item 15. Note-region decorations
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

**Glow scope is a third list, and the one ALLOWLIST** (ruling
2026-08-06, `core/animation/glow_scope.GLOWING_KINDS`). A halo says
"this note is sounding", so it reaches a note and the ink drawn as part
of one: noteheads, the slash and bar-repeat signs that stand in for a
head, stems, flags, beams, tremolo strokes, accidentals, dots,
articulations, ornaments, tuplet brackets and numbers, ledger dashes,
the lyric under a note, and the tie between two. Dark: rests, whole-bar
rests, dynamics, clefs, key and meter signatures, texts, chord symbols,
slurs, hairpins, and all the scaffold. A **slur is dark where a tie
glows** — a tie is the note continuing, a slur is not — which is the one
place the clip-revealed kinds part company.

The direction is the point, and it is why the three lists are not one.
A new `ElementKind` should animate for free (denylist) and should stay
dark until somebody decides it is a note (allowlist): opposite safe
defaults, so two lists. Dots reach the list through `ElementKind.OTHER`,
which also carries the ornaments and the tuplet brackets — all note ink,
but not separable until OTHER is split into real kinds.

Two consequences of the same ruling. **A tied chain glows as one note**:
the chain's first head owns the halo, every other head and the tie ink
between them follows it, and the halo lasts the whole chain rather than
the first head's engraved value. That is a glow rule only — appearance
is untouched, so `schedule.py` rule 1 (grow-with-playhead, 2026-07-22)
stands and a continuation head still fills in as the playhead reaches
it. And **attached ink shares its head's halo** rather than running its
own clock, joined through the nearest head, the same join a pop's pivot
makes: one note is one light.

Mechanism: `render/glow_driver.py` writes `can_glow` onto each
`ElementItem` from this list and clears it for ink whose halo its leader
owns; `render/properties.py` obeys it and decides nothing. So the list
IS the switch — widening it from head-and-accidental to the whole note
cost one frozenset and two test expectations.

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
├── condense_groups      v5 (Phase 12.3): contiguous like parts merged
│                        onto one staff (one voice per player, combined
│                        label); the merged part-list re-derives at the
│                        prep seam (adapter ruling 10); CLAUDE.md rule 11
├── system_break_overrides
│                        v8 (M5): a SPARSE DELTA on the score's encoded
│                        system breaks — {measure ordinal → FORCE |
│                        SUPPRESS}, keyed by the measure that would
│                        START the system. Rewritten into <print
│                        new-system> on part 1 at the prep seam,
│                        UPSTREAM of condense / hide / repaginate /
│                        scale-to-fit, so all four operate on the edited
│                        break set exactly as they do on the encoded
│                        one; rule-7 M5 amendment
└── page_break_overrides
                         v9 (M6): the same shape for <print new-page>,
                         keyed by the measure that would START the page.
                         Written by the SAME pass as the map above, and
                         additionally fed to the never-clip planner —
                         pages are the one layout input the app already
                         owned, so authored page intent lives INSIDE
                         rule 7(a) rather than over it; rule-7 M6
                         amendment
```

**The break-override seam (M5 systems, M6 pages).** The document stores
intent and only the DELTA — never the whole break set, so a measure with
no override keeps whatever the file encodes. `core/score/
musicxml_rewrite.py:_apply_breaks` is the pass, a deliberate twin of
`_repaginate`: part 1 only (Verovio reads print layout from the first
part), keyed by 1-based document ordinal (never the printed number),
creating `<print>` when a positive assertion needs one. Two things it
does NOT copy from `_repaginate`: it never strips the encoded breaks
first, and it is stored rather than derived. `prepare()` takes the two
maps as `system_breaks=` / `page_breaks=`, and `load_detailed` must pass
BOTH on all THREE of its retry paths — the hide-unavailable retry (which
re-engraves the same prep), the repagination retry and the scale-to-fit
retry (which both re-prepare) — or a score that repaginates silently
loses the user's breaks. The pass returns, per axis, the ordinals it
could not apply, which become `LoadWarning "break-override-inert"` and
`"page-break-override-inert"`.

**ONE pass over both maps, not two (M6, D3).** The two override maps
write two attributes of the SAME `<print>` element. Measured with two
passes, whichever ran first left the second nothing to change, so a
gesture that had worked perfectly reported itself inert. Writing both
attributes in one visit removes that by construction. The coupling rules
live in one pure function, `_wanted_break_attrs`, because the incoherent
combination was measured resolving in OPPOSITE directions under the two
possible pass orderings and therefore has to be STATED:

- **page FORCE wins outright**, including over a coincident system
  SUPPRESS — a page break that refuses its own system break is not a
  layout, and the positive assertion is the one that can be honored;
- **page SUPPRESS asserts the system break it removes** (Dorico encodes
  a page break as `new-page` alone, so clearing it would silently merge
  two systems), unless the system break is separately suppressed too;
- **system SUPPRESS clears a coincident `new-page`** (M5's D7), so
  suppressing a SYSTEM break can move a PAGE break — acceptable under
  rule 7(a), which already has us owning the page count.

`core/editing/break_coherence.py` is the document-side half of the same
ruling: the toggles clear the one contradicting pair in the same undo
entry, so the precedence above exists for hand-edited files and rule-5
staleness rather than for anything the UI can author.

**Page intent and never-clip (M6, D1).** `_repaginate` strips every
encoded page break before asserting its own plan, so a page FORCE
written at the seam is destroyed exactly when the guard engages — and
measured to fail rarely and silently, which is the worst failure shape
available. So authored page intent is ALSO an input to
`plan_page_breaks`: forced ordinals join the plan, restricted to real
system starts. A SUPPRESS is deliberately NOT a parameter — it is
already applied at the seam, so the bands the planner measures honor it
and every break the planner emits is one it needs. Subtracting them
would delete breaks never-clip requires (measured: a 40% scale-to-fit
rescue on bigband1 instead of an extra page). A suppression is therefore
honored wherever the planner does not need that break and overruled
where it does, reported by `LoadWarning "page-break-repaginated"` — a
different code from the inert one on purpose, since "your override was
stale" and "your override was overruled to avoid clipping ink" want
different things from the user. The two are read off the FINAL layout so
they partition rather than overlap.

`_repaginate` itself promotes every encoded `new-page="yes"` to also
carry `new-system="yes"` before it strips (BACKLOG 16, paid in M6.0):
a repagination may not change SYSTEM content, which is what rule 7(a)
always claimed and did not do.

The layout consequence re-derives like every other engraving input:
`ui/score_loader.py` carries `_applied_breaks` and `_applied_page_breaks`
as applied inputs, so execute / undo / redo all route through one
`needs_reengrave` trigger, and `page_of_measure` — composed from the
system bands and the measure→system map, needing no adapter change —
rides on `LoadedScore` for the toggle to read. Staleness follows rule 5
— an ordinal that no longer means anything is inert and warned, never an
error.

**Gestures compose over the two primitives, above this seam (M5.7).**
"Move to Previous System" is SUPPRESS at the first measure of N's system
plus FORCE at N+1 — computed purely in `core/editing/breaks.py` from
`(N, overrides, system_of_measure)` and written by ONE `SetSystemBreak`,
whose `also` field carries the extra entries (rule 8 counts gestures,
the fat-apply idiom). Nothing at the seam knows the gesture happened,
which is the point: a new break gesture is a new entry-set function, not
a new pass, a new field or a new schema version. Two rules the entry set
follows are worth keeping: each half CLEARS an opposite override where
that suffices rather than writing a new one (sparse, and reversible),
and an entry that would rewrite an encoded break with itself is omitted
— it changes nothing and would report itself as inert.

Schema versions (`core/project/serialize.py`, strict gate): **v1**
(Phase 4) had `style.part_colors`; **v2** (Phase 5.3) is the StyleRules
shape above; **v3** (Phase 7.1) added floor_opacity, presentation mode,
staff_groups, and text_overrides in ONE bump — every planned v2-era
field designed at once, no per-phase bumps; **v4** (Phase 10R) added
hide_empty_staves, VERSION-GATED on read: v≤3 files predate the option
and load OFF so their look is unchanged, while new documents default
ON; **v5** (Phase 12.3) added condense_groups (no read gate needed — a
missing key defaults to (), the correct look for older files); **v6**
(2026-07-24) added hide_first_system; **v7** (M4) added
style.default_effect and style.effect_params; **v8** (M5) added
system_break_overrides; **v9** (M6) added page_break_overrides. v4 is
still the ONLY read gate — every later field's missing key defaults to
the pre-option look. The reader accepts
{1 … 9}: v1 `part_colors` folds into part
color rules, older files default newer fields per-field (no migration
code — they just lack the keys); the writer emits 9. The gate is
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
  re-engrave). M4's per-element durations ride
  `TriggerSchedule.duration_by_element` (resolved once by the loader
  via `core/animation/durations.py`) and its effect params ride
  `StyleRules` — so note-value settle, amplitude/settle, and peak
  offset all reached export with ZERO exporter edits, pinned by
  test_export's live-vs-exported state comparison. Frame n calls `apply_at(t)` when n follows the last
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
  `convertToFormat` per frame puts the bytes in R,G,B,A order whatever
  the machine's endianness. ProRes 4444 .mov (ffmpeg stdin stream,
  runtime-discovered) is the default; PNG sequence (pure Qt) is the
  no-ffmpeg fallback. Export settings are session memory only (ruling
  R3) — nothing enters the project document.
- **Alpha mode** (2026-08-06, `render/encode.py::AlphaMode`): that same
  convert also decides how the file writes colour beside alpha, and it
  is the user's choice with **premultiplied ("matted with black") the
  default**. Straight was the only option until a glow exported for
  Premiere came out solid: an editor that reads straight frames as
  premultiplied puts every soft edge on at full strength, wrong by
  1/alpha (measured on a real halo pixel — alpha 70/255 carrying
  (251,197,91) should composite over black to (69,54,25) and arrived as
  the full gold, 3.6x). Premiere assumes premultiplied and offers no
  switch, so the app matches it. The matte is then RELABELLED as plain
  RGBA — the same bytes under a name Qt will not undo — because
  `pixelColor` un-premultiplies on the way out and Qt's PNG writer
  converts premultiplied data back to straight before saving. Pinned:
  the two modes are the same picture (premultiplied == straight x its
  own alpha), and a premultiplied clip's colour channel decodes to the
  app's own over-black composite within 2/255.
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
- **The scene has one parent per system.** Every element whose `system`
  is known hangs off a `SystemGroupItem` for its (page, system)
  (`render/system_group.py`); ink that belongs to no system — stage
  texts, page furniture — stays a direct child of the scene. The group
  paints nothing, is hit-transparent (the same empty `shape()` that
  keeps per-element parents out of selection's candidate list), sits at
  the origin, and carries **no transform at all** until somebody scales
  it, so every child keeps the scene coordinates it had before the
  parent existed. `set_system_scale` turns the system around the centre
  of its own ink, frozen once at build time — nudges and animation both
  run later and must not drag that point — and 1.0 is exactly identity.
  A scale changes every descendant's scene transform, so it re-derives
  their reveal clips through `ElementItem.refresh_reveal_clip` (the M3.2
  trap below, reached the other way).
  *Paint-order caveat:* elements are mostly but not entirely contiguous
  by system — synthesis appends slashes and stray ties at the end of
  `layout.elements` — so grouping moves that tail earlier relative to
  OTHER systems' ink on the same page. Order within a system is exact.
  Measured invisible: 21 pages over testscore, video_test and complex1
  render bit-identically (`tools/render_page_png.py`, 2026-08-01).
- **The system pulse is the one thing that scales those groups**
  (2026-08-02, `render/pulse_driver.py`). A size per system per FRAME,
  and two independent things move it. Deliberately NOT a property track
  either way: it is not per element, not per trigger, and never enters
  `element_state`, so the evaluator and the compose table are untouched.
  - *Follow volume*: `amount × intensity_at(recording, t + offset)`, one
    number for the whole page, so it breathes as one object. It reads
    the RAW loudness, not the volume response's quiet-to-loud gain —
    two features, two knobs, one reading.
  - *Onset pop*: at every beat the system the notes land in jumps to
    `pop_amount × strength` and eases linearly back to nothing over
    `settle` — the note pop's own shape, so the two read as one gesture.
    `strength = heads / notes_for_full`, capped at 1, counting HEAD_KINDS
    only (a stem or dot is ink hanging off a head already counted) and
    counting each head in the system it is DRAWN in, never in the
    trigger's single min()-aggregated system hint. Overlapping bumps take
    the LARGEST live one, never the sum, so a fast run cannot inflate a
    system. Evaluation is a bisect over that system's trigger times
    bounded by `settle`. **No audio anywhere in it** — the schedule is
    the whole input.
  - The two DEVIATIONS add: `1 + follow + pop`. Both at 0 means no group
    is ever touched, so the page is bit-for-bit what it was.
  - The applier holds the driver beside the reveal driver and feeds it
    from `_recompute_audio` (the recording half) and `_recompute_bumps`
    (the schedule half), both of which already run on every seam that can
    move them — which is why live preview and export need no wiring of
    their own. The unchanged-value skip is per GROUP, keyed like the
    reveal edges, because the bumps differ per system.
  - Nothing checks whether two systems meet: the 0–0.2 clamps are the
    only guard, and they are **not tight enough** — at 0.10 two systems
    already overlap on testscore page 2 (`spikes/system_pulse.py`;
    `spikes/onset_pop.py` for the pop half, where a gap closes from one
    side only and 0.10 leaves 6.2 units).

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

  Navigation is the ordinary desktop set (ruling 2026-07-30, replacing
  M2's): **pinch zooms** (a macOS native gesture on the viewport, caught
  in `viewportEvent`), **two-finger scroll moves the view** on both
  axes, **Cmd/Ctrl + wheel zooms** so a plain mouse can too, and
  **nothing pans by dragging** — so the cursor over the page is the
  plain arrow, with no `setCursor` call anywhere. All three zoom paths
  go through `StageView.zoom_by`, which clamps with the pure
  `clamped_factor` and leaves fit mode. Zoom is always a change to the
  VIEW transform, never to items (see the reveal-cache trap below).
  Qt's own scrollbars are switched off: the macOS style here reports
  `SH_ScrollBar_Transient = False`, so showing them reserves space and
  would shove the score sideways by 20 px mid-gesture
  (`spikes/stage_gestures.py`). `ui/stage_scrollbars.py` paints a
  fading hint instead — feedback only, not draggable.

- **TempoLaneView**: the lane under the waveform, sharing its time axis.
  A host widget with two modes, chosen by `AppState.grid.display`
  (Ticks is the default since 2026-07-30)
  (`ui/grid_options.py` — view state, never document intent). The host
  owns what they share: background, measure grid, playhead, the beat ⇄ x
  mapping, the cached `TempoMap`, click-to-seek and wheel zoom; each mode
  owns its drawing and its gestures, and gets first refusal on every
  event. `ui/lane_tempo.py` is tempo events as draggable points (the red
  step line); `ui/lane_ticks.py` makes the grid lines themselves the drag
  handles — see "Grid alignment" below. Swing is a single global ratio
  set numerically on the transport bar in v1 (ruling 2026-07-11); the
  SwingRegion data model is unchanged and per-region authoring returns
  later (BACKLOG 7).

  **Grid alignment (2026-07-30).** Dragging a grid line onto the
  waveform is solved back into `(position, bpm)` tempo events —
  `core/timing/retime.py`, one command `AlignBeat`. `tempo_events` stays
  the only tempo representation, so the same edit reads as a step in
  tempo mode.

  What holds still is the user's LOCKS (`TimingConfig.locked_beats`,
  schema v10), set by double-clicking a line. `lock_anchors` takes the
  nearest lock either side — the score start standing in below, None
  above meaning the music after keeps its tempo and slides. `AlignBeat`
  reads them off the document rather than taking them as fields, so the
  view cannot hand over a pair that disagrees with the locks, and it
  locks the beat it just placed in the same command (one gesture, one
  undo entry). A lock anchors its neighbours; dragging a locked line
  moves it and re-locks it there.

  Two rules, both holding the anchors: `flatten_span` (the default)
  gives the span one constant bpm — evenly spaced, whatever was inside
  is gone; `scale_span` multiplies the bpms instead, keeping tempo
  detail worth having, like a tapped rubato passage. `span_bounds` gives
  the view the reachable window for either, so a drag cannot build a
  command that fails on release. The first line has no anchor before it,
  so it edits the offset. Locks store beats only — the second is derived
  (rule 5) — and constrain tick drags alone.

  Setting a tempo numerically works off the same selection: clicking a
  line sets `AppState.grid.selected_beat` (lane state — a position on the
  time axis, not a rule-13 score object, and never in
  `AppState.selection`), the Tempo field on the strip retitles itself
  "Tempo from m5", and committing it runs `SetTempoFrom`, which replaces
  every event after that line and releases the locks after it. With no
  line selected the field edits the initial tempo, as it always did.
  That is the whole job the tempo line's drag used to do, so Tempo mode
  is now a second view rather than the way to work.
- **WaveformView**: rendered peaks, playhead, click-to-seek; tap capture
  during playback.

Views never talk to each other — only observe/mutate AppState via signals
and commands. Window orientation (portrait/landscape panel arrangement) is
a QSplitter/dock concern, orthogonal to the stage's aspect.

**Selection (M2, as built 2026-07-25; reworked M2.8 2026-07-27).**
Transient UI state, never document state (rule 13): `AppState.selection`
holds a `Selection | None` with a `selection_changed` signal, never
serialized and never undoable (rule 8 needs something to undo). Five
separated concerns: the pure hit-priority policy in
`core/selection/policy.py` (Qt-free, headless-tested); the selection
SHAPE in `core/selection/context.py`; the click gesture on `StageView`
(press/release under `startDragDistance()`, and no modifier key needed —
the threshold was built to tell a click from a pan, and outlived the pan;
it stays so a hand that slides while pressing cannot change the
selection); `ui/selection.py`
`SelectionController`, which collects candidates within a 6-page-unit
tolerance, calls the policy, and owns the highlight; and the readout in
`ui/panels/selection_panel.py`.

`Selection` stores exactly ONE thing — the object the user picked — and
derives what it carries on read: the part off the minted identity, the
measure ordinal off the id grammar. Nothing stored, nothing geometric,
no second field to keep in step, and no way to build a selection whose
context disagrees with its object. `AppState.selected` remains as the
object-alone accessor. The panel shows the object in one block and
part/measure under a dimmed "carries" caption in another; the two levels
are **panel-only** — nothing on the stage marks them, because a measure
is never a selection target and must never look like one.

The policy orders candidates `(not exact, tier, area, element_id)` —
exactness first because a stem's authored `Rect` has w=0 and would
otherwise beat its own notehead, then a layer tier (animated ink /
scaffold / STAFF_LINES as the backdrop) because a system barline's bbox
is LARGER than one staff's staff lines and both are scaffold, then the
engraved bbox area, then the id so the pick is permutation-independent.
Area is the Verovio-authored rect, not Qt path bounds, so it is
identical on every machine. Scaffold stays selectable — barlines are
M5's handle. The BACKDROP is filtered out of the pick entirely
(`is_selectable`), so a click on empty staff space deselects, the same
answer the paper margin gives.

**The highlight is a TINT on the element's own ink** (M2.8, superseding
M2.4's outline; `core/selection/highlight.py` holds the colors, pure and
headless). The compositing rule, which export and M3 both sit downstream
of:

> Selection composites LAST and modifies only the two channels it needs.
> An element's painted appearance is a function of three inputs in fixed
> order — authored color (document intent) → animation state
> (opacity/scale from the evaluator) → selection (transient). Selection
> replaces the color and raises an opacity floor; it never touches
> scale, never touches the reveal clip, and never writes back into the
> first two. Deselecting re-derives the composite of the first two;
> nothing is remembered.

`ElementItem` is the one place that composes it. Each input has its own
setter, so writing one never destroys another — which is required, not
tidy: `DocumentSync.sync_styles` is a diff cache, and anything that
overwrote the authored color behind its back would leave it believing a
color it could no longer restore. Three consequences, each measured
before being written here (M2.8, M1–M4):

- **Opacity.** A selected element is held at or above
  `SELECTION_MIN_OPACITY` (0.85) whatever the evaluator wrote. This is
  the only way it can work: the ghost floor may be **0**, where an
  unfloored tint is a tint on nothing. Measured across a pop envelope at
  floor 0.3 and 0.0 — unselected 0.3/0.0 → 1.0 at trigger, selected
  never below the floor at any sample.
- **The reveal clip is sidestepped, not fought.** A spanner's dimmed
  ghost of the whole curve is always present, so the tint rides it. But
  ghost opacity MULTIPLIES the parent's, so a parent-only floor still
  composited to 0.000 at floor 0; ghost opacity therefore lives on
  `ElementItem` too and composes the same way (`ScoreScenes` delegates),
  giving 0.850.
- **Authored color.** A user can already color an element (part tint
  today, per-element override with M3), and tinting an orange note
  orange makes the selection invisible on the object it names. When the
  authored color is within a redmean distance of 120 of
  `SELECTION_COLOR` the tint falls back to `SELECTION_ALT_COLOR`. That
  threshold is a **judgment, not a measurement**, read off the distance
  table pinned in `tests/test_selection_highlight.py` (near-oranges land
  at 32–118, the nearest other hue at 175).

Two properties the tint gains over the outline: it follows a pop's scale
transform (the box deliberately did not), and it adds no object to any
scene, so nothing can be mistaken for score ink.

Export purity survives the change but rests on a different argument.
M2.4's proof was that the highlight was a separate item export could not
see; a tint is paint on an ordinary `ElementItem`, exactly what export
DOES rasterize. What holds instead is that `FrameRenderer` builds its
own private `ScoreScenes` from `AnimationInputs`, whose items are
constructed unselected, and nothing in the export path can reach
`AppState`. Pinned by a byte-identical frame comparison with a positive
control (the live item's paint really changed) and a non-vacuity guard
matched to the mechanism: selecting an element in the EXPORT renderer's
own scenes must move the frame digest.

Selection CLEARS where its items are destroyed (`_install` on every
load/re-engrave, `reset_document` on project open) and SURVIVES page
flips and mode switches, because scenes are per-page and retained
(ruling D2, 2026-07-25).

**Direct edit (M3, 2026-07-27).** Three affordances over machinery that
already existed. Policy is pure and headless in `core/editing/`
(`text_route.py`, `nudge.py`, `segments.py` — the `core/selection/
policy.py` shape); the Qt halves are `ui/text_edit.py`, `ui/nudge.py`
and `ui/panels/selection_style.py`.

*Double-click is not selection.* It resolves through its own hit path
over both engraved TEXT and stage texts, so D5 stands — stage texts stay
out of `AppState.selection` while being editable. The two gestures ask
different questions: selection asks which rule-13 object was picked, and
an object carries a measure and a part, which a stage text has neither
of. This is load-bearing, not tidy: once a tempo mark is overlaid the
thing on screen IS a stage text, so a shared path would make a
just-created replacement uneditable.

*The staff-label route, completed in M7 (2026-07-30).* M3 wrote and
unit-tested the part-label route but could not reach it: the adapter
minted labels with `part=None`, so `route_for` returned None for every
real one and the first M3 exit criterion went unmet (BACKLOG 14). M7
supplied the attribution in the adapter (obligation 17) and the route
lit up with no change to `SetPartText`, the prep seam, or the document
schema — the affordance was already built, waiting for a part.

One route was ADDED: a **condensed** staff's label edits its condense
group, not the kept part (ruling 2026-07-30). Its label IS the group's
combined name and `doc.condense_groups` is where that name lives, so
`TextRoute.CONDENSE_LABEL` runs the existing `EditCondenseGroup` and the
score and the Score Setup dialog keep showing one string. `SetPartText`
would also have worked — text overrides are applied after the condense
rewrite at the prep seam, so the override wins — but then the two would
disagree. Note the asymmetry this inherits: `CondenseGroup.name = ""`
means "derive from the sources", where `SetPartText("")` means "no
label", so blanking a condensed label restores the derived name.

The condense route needs the SCORE's part order, not the condensed one
the current build reports — a condensed score's part list has no P2 in
it, while the group still names P2, and the condense commands validate
against the order they are handed. `editing.flat_part_order` rebuilds it
by putting each group's parts back at its kept part's position, the exact
inverse of `_apply_condense`. Handing a condensed order to those commands
makes them fail silently, which the Score Setup dialog still does
(BACKLOG 20).

*The nudge seam.* `LayoutOverride.dx/dy` were schema slots from Phase 4
until `SetLayoutOverride` (M3.2). The delta is **absolute, not
incremental**, and that is what makes one command per gesture possible:
a drag previews by moving the scene item, touches no document state, and
executes once on release (rule 8), while undo is a plain replay of the
previous value rather than an unwinding. Deltas are page units — scene
coordinates ARE page coordinates, which is why `render/scene.py` builds
one scene per page rather than one scene with page offsets — and keyed
by musical `ElementId`, so the engraved position they ride on re-derives
every load and is never stored (rule 5). Override staleness stays the
accepted trade: an id the current engraving lacks is skipped.

*Export parity is structural.* `apply_hidden_overrides` grew into
**`apply_overrides`**, applying the whole `LayoutOverride` rather than
just `.hidden`. It consumed only `.hidden` because dx/dy were dead
slots; now that a nudge is real, anything that function skips is a way
for the exported frame to disagree with the stage. One function, every
field, and the live side diffs the same values through
`DocumentSync.sync_offsets`. Pinned by rendering real frames through
`FrameRenderer` with the document's overrides: after a nudge the
export's private scenes carry the same delta and the frame digest moves;
clearing restores the original bytes exactly.

*Moving ink invalidates a reveal cache.* `RevealPathItem.set_clip_right`
takes the reveal edge as a SCENE x and maps it into the child's local
coordinates through an inverse scene transform it caches on first use.
That cache was correct as long as nothing moved, which was true of every
element before nudging existed. Measured (`spikes/nudge_reveal.py`): a
+30 nudge displaced the clip edge by exactly +30, so the spanner
revealed as if the playhead were dx further right. `ElementItem.
set_offset` invalidates it and **re-pushes the last edge** — necessary
because the clip in force was computed with the stale inverse and
nothing else recomputes it until the next tick, which never comes while
paused, and nudging is something people do while paused. With the
invalidation the local clip tracks exactly −dx and is y-independent.
`HAIRPIN` therefore stays nudgeable despite being in `REVEALED_KINDS`.

*Two writers, one position* (2026-07-31, the slide effect). The nudge is
no longer the only thing that moves an item: `OFFSET_X`/`OFFSET_Y` are
animatable properties, in scene units from the engraved place. So the
position joins colour and opacity as a **composed** input —
`ElementItem` stores the document's nudge and the animation's offset
separately and derives `setPos(doc + animated)` itself. Neither writer
may call `setPos`: a nudged note has to slide to its NUDGED place, and
an applier that wrote the position directly would undo the nudge on
every frame. The derived path carries the reveal-cache invalidation
above, so an animated move stays correct too — spanners get no triggers,
so nothing exercises that today, but the item does not depend on it.
`AnimationApplier.set_style` resets a stale animated offset to (0, 0)
the same way it resets a stale scale.

*The `:seg` fan-out.* A per-element override on a system-broken spanner
writes the whole family (`core/editing/segments.py`: strip one trailing
`:seg<digits>` for the source, members are the source plus every
`^source:seg\d+$`, intersected with the loaded registry so no override
names an id the engraving lacks). Sound because the adapter mints
segments as `replace(source, element_id=...)` — everything but the id is
inherited — audited across four fixtures before the ruling. Because rule
8 counts gestures rather than documents touched, `SetElementStyle`
carries a `segments` field and the family is ONE undo entry: the "fat
apply" idiom `ApplyScoreSetup` names, there being no generic macro
command.

*M3 writes the AUTHORED channel only.* The style controls execute
commands and let `DocumentSync.sync_styles` — which owns the diff cache
— push colour through `set_color`. Nothing in M3 writes the transient
tint, so the compositing rule above is unchanged and a user who colours
an element the selection's own orange still sees it selected via the
`SELECTION_ALT_COLOR` fallback.

Since M1 Shell (2026-07-24) the window is a composition root, not a
widget owner: the stage alone is central, the transport strip + lanes
live in a bottom-dock lower zone (`ui/transport.py`), the collapsible
inspector is a right dock (`ui/inspector.py`), and static chrome, the
dynamic Score menu, the load pipeline, document→scene diff-sync, and
file/project handlers are components (`ui/menus.py`, `ui/parts_menu.py`,
`ui/score_loader.py`, `ui/document_sync.py`, `ui/file_actions.py`) that
receive AppState (plus the playback controller where needed) and never
reach into each other. `ui/live_field.py` is the same kind of small
shared piece on the input side: it wires a spinbox to AppState's
preview/commit pair, so every number field previews as you type and a
typing session lands as one undo entry (PATTERNS, "A number field
previews as you type"). M3.0 (BACKLOG 9b) finished the job before adding
to it: **`ui/view_router.py`** owns which presentation unit the stage
shows (page/system position, step, follow, the mode diff), bound per
load like `DocumentSync`, and driving the chrome through
`MainMenus.set_position` rather than reaching for its widgets; the
part-shaped dialogs moved to `ui/parts_menu.py`, which is already handed
the parts on every load, and the Texts… dialog to `ui/text_edit.py`,
which owns the engraved layout it reads. QSettings (`ui/window_state.py`) persists window
geometry, dock layout, and section expansion — UI state only, saved on
accepted close; nothing document-derived enters it and nothing of it
enters the document (rule 5).

**Break authoring has two surfaces and one implementation** (M5.4,
M5.7, M6.5/M6.6). `ui/break_action.py` owns three QActions — the system
toggle, Move to Previous System, the page toggle — with one enable/label
sync driven by the pure policies in `core/editing/`; the policy never
enters the UI and the QAction never enters core. The Score menu holds
those actions (re-inserted per load, since it is rebuilt per load), and
so does **`ui/layout_zone.py`**, a LEFT dock on the inspector's template
(BACKLOG 17, built once three actions needed a home). Its buttons take
those QAction objects as their `defaultAction`, so text, enabled state,
status tip and trigger all come from ONE object and the two surfaces
cannot diverge — the `follow_action` precedent, and the reason the zone
syncs nothing of its own. The zone also hosts
`ui/panels/break_overrides.py`, which lists both override maps in
measure order with a per-entry clear; the clear needs no new command,
since `mode=None` already pops and reaches the same `execute()` path
that re-engraves, re-anchors and restores the selection. A third dock
needed no persistence change: one `saveState` pair covers all three, and
a stored layout predating the zone still places it (measured before
deciding, since bumping `_STATE_VERSION` would discard every user's
window layout).

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
