# ScoreAnim — Rules, long form

The rules in CLAUDE.md are the short form. This file keeps the long
form: the full text as it stood on 2026-07-30, including every dated
amendment and the reasoning behind it. Nothing here is new — it is the
detail that was cut out of CLAUDE.md so every session no longer pays for
it up front.

Read a section here when a rule's short form in CLAUDE.md is not enough
to make a decision. The mechanisms themselves are in
`docs/ARCHITECTURE.md`; this file is about what the rules mean and why
they say what they say.

When a rule changes, change the short form in CLAUDE.md (asking Marcus
first) and update the matching section here.

---

## Non-negotiable rules (the load-bearing walls)

1. **Core is pure Python. Nothing under `scoreanim/core/` may import
   PySide6/PyQt/Qt.** Qt lives only in `scoreanim/render/` and
   `scoreanim/ui/`. There is a test (`tests/test_no_qt_in_core.py`) that
   enforces this; it must always pass.

2. **Time is never accumulated.** No `t += dt` anywhere. Animation state is
   a pure function `state(t)`. `t` comes from an injected `Clock`:
   `AudioClock` (audio playhead position) for live playback, `FrameClock`
   (`t = n / fps`) for deterministic export, `WallClock` (perf_counter
   since play-anchor, no-audio playback — FIX 2). The animation layer
   never reads a timer itself.

3. **The audio playhead is the master clock during live playback.** The
   animation reads it; never the reverse. Amendment (FIX 2, 2026-07-20):
   when NO recording is loaded the score still plays, driven by
   `WallClock` (`ui/wall_clock.py`) — a wall-anchored, re-anchored-on-
   seek/pause pure function (rule 2 holds; no `t += dt`), paced by the
   tempo map with offset 0. AudioClock remains master whenever audio IS
   loaded; the controller picks the clock by `transport.has_media()`.

4. **Engraving is behind the `EngravingProvider` interface.** Verovio types,
   Verovio element IDs, and Verovio SVG never leak past the adapter package
   `core/engraving/verovio/`. Everything downstream uses our own
   `ElementId` and neutral `Layout` types. The adapter always sets a fixed
   `xmlIdSeed` so Verovio IDs are deterministic across loads — overrides,
   style rules, and tests depend on stable `ElementId`s; the golden
   suite (`tests/goldens/`, Phase R) pins 12 fixture loads byte-for-byte
   on exactly that determinism.
   Amendment, Phase 11 (2026-07-15 ruling): an unknown drawable SVG
   class no longer fails the load in the app path — it degrades to a
   warned static OTHER element (`LoadWarning "unknown-class"`; the
   status bar counts it, stderr names the class). Tests stay strict:
   `load_detailed(..., strict=True)` (the default, and the
   score-doctor's `--strict`) still raises, so coverage gaps surface
   loudly in development. The doctor (`python -m
   scoreanim.tools.check_score`) is the triage engine for new exports.

5. **The project document stores user intent only, never derived data.**
   Layouts, timemaps, and decomposed elements are always re-derived from
   (score file + engraving params + overrides). Layout overrides are
   dx/dy deltas keyed by musical `ElementId`, never absolute pixels.

6. **Effects are data, not code.** An effect is a named bundle of
   `(property, Envelope)` tracks evaluated at `t_rel` to onset. Adding a
   new effect means adding data/preset definitions, not branching in the
   evaluator. Amendment (M4, 2026-07-25): an effect may carry scalar
   data the applier consumes generically — a per-element timescale
   (note-value settle, duration from the engraved timemap per rule 12)
   and a signed trigger shift (peak offset). Both are inputs to the one
   evaluation kernel
   (`element_state(trigger, effect, t, timescale)` =
   `state_at((t − trigger − shift) / timescale)`); neither is a branch
   on an effect's name. **Animation is a DENYLIST** (user-ruled 2026-07-20):
   every object on the page animates with the appear/effect system
   EXCEPT the true scaffold — staff lines, barlines, group
   symbols/brackets, system dividers (`schedule.STATIC_KINDS`) — plus
   page furniture (part labels, header/footer, measure numbers, minted
   onset-less). A new `ElementKind` animates by default; the adapter
   resolves an onset for it (10R.2 attach mechanism, else measure
   start). This ruling changes ANIMATION scope only — color scope
   (`TINTED_KINDS`) is unchanged, so clefs and key signatures animate
   but stay black. See ARCHITECTURE.md §3 "Animated-ink taxonomy".

   Amendment (user-ruled 2026-08-06): **glow scope is an ALLOWLIST**
   (`glow_scope.GLOWING_KINDS`), the third scope list and the only one
   of the three that is not a denylist. A halo says "this note is
   sounding", so it reaches a note and the ink drawn as part of one —
   the head, the slash and bar-repeat signs that stand in for a head,
   the stem, flag, beam, tremolo strokes, accidental, dots,
   articulations, ornaments, tuplet brackets and ledger dashes, plus the
   lyric under a note and the tie between two. Dark: rests, dynamics,
   clefs, key and meter signatures, texts, chord symbols, slurs,
   hairpins, scaffold. A **slur is dark where a tie glows** — a tie is
   the note continuing, a slur is not.

   The direction is deliberate and is the reason this list is not folded
   into the denylist. A new `ElementKind` should animate for free, which
   is what a denylist buys; it should NOT glow until somebody decides it
   is a note, which is what an allowlist buys. The two questions have
   opposite safe defaults, so they are two lists.

   Two consequences, both ruled the same day:
   - **A tied chain glows as one note.** A held note is re-notated at
     each barline; the chain's first head owns the halo and every other
     head plus the tie ink follows it, for the chain's whole length.
     This is a GLOW rule only — APPEARANCE is untouched, so rule 1 of
     `schedule.py` (grow-with-playhead, 2026-07-22) stands and a
     continuation head still fills in as the playhead reaches it.
   - **Attached ink shares its head's halo** rather than running its own
     clock, joined through the nearest head — the same join a pop's
     pivot makes. One note is one light.

   Nothing downstream branches on a kind: the driver
   (`render/glow_driver.py`) writes `can_glow` onto the item from this
   list and `render/properties.py` obeys it, so the list IS the switch.
   Widening it from head-and-accidental to the whole note the same day
   it was written cost one frozenset and two test expectations.

7. **The user owns page layout.** We honor the MusicXML's encoded
   SYSTEM breaks always (Verovio break-respect mode). We never reflow
   to fit the window. Paged presentation; mismatched aspect is
   letterboxed.
   Amendment (M5, 2026-07-28): the honored system-break set is the
   encoded breaks ⊕ the user's in-app break overrides
   (`doc.system_break_overrides`, applied at the prep seam). Still never
   window reflow: an edited break set is an engraving input like a part
   rename. Suppressing a break also clears a coincident encoded
   new-page — a page break implies a system break, so leaving it would
   make the suppression inert — and pagination then re-derives by the
   rule-7(a) mechanism below, so suppressing a SYSTEM break can move a
   PAGE break: the page count is **owned, not clipped** (D7).
   Amendment (M6, 2026-07-28): the honored PAGE-break set is likewise
   the encoded page breaks ⊕ the user's in-app page-break overrides
   (`doc.page_break_overrides`), written by the SAME prep-seam pass as
   the system delta — `_apply_breaks` visits one `<print>` once and
   writes both attributes, because two passes racing on one element
   manufacture false inert warnings. Page breaks are the one layout
   input the app already OWNED before the user could author them —
   rule 7(a)'s never-clip repagination re-derives them whenever a system
   would overflow — so authored page intent is honored *within* that
   guarantee, not above it: a forced page break is an INPUT to the
   re-derived plan and survives repagination, and a suppressed one is
   overridden, and warned (`page-break-repaginated`), whenever honoring
   it would clip ink. Never-clip stays absolute; the page count stays
   owned. Where the two maps disagree at one ordinal, **a page break
   implies a system break**: page FORCE beats a coincident system
   SUPPRESS, and page SUPPRESS asserts `new-system="yes"` rather than
   clearing the measure's only marker (the mirror of D7 above) — unless
   the system break is separately suppressed too, which is a coherent
   pair of negatives. The toggles clear the one contradicting pair in
   the same undo entry (`core/editing/break_coherence.py`), so that
   precedence exists for hand-edited files and rule-5 staleness rather
   than for anything the UI can author. And a repagination may NOT
   change SYSTEM content: `_repaginate` promotes every encoded
   `new-page="yes"` to also carry `new-system="yes"` before it strips
   (BACKLOG 16, paid in M6.0).
   Three further amendments (Phase 10R 2026-07-13; (c) Phase 12.5
   2026-07-21):
   (a) encoded PAGE breaks are honored unless a system would overflow
   its page (Dorico breaks are computed assuming hidden staves) — then
   the adapter keeps the system breaks, re-derives page breaks at the
   prep seam, and re-engraves once (`LoadWarning "repaginated"`;
   page-scoped ids shift). **Ink is never clipped.** (b) staves empty
   for a whole system may be hidden via the per-score **Hide Empty
   Staves** option (Verovio `optimize` over an MEI round-trip; the
   MusicXML itself carries no hidden-staff info) — default ON for new
   documents, OFF for pre-v4 projects, undoable, an engraving input
   like staff groups. Slash regions win over hiding (rule 10;
   `LoadWarning "hide-unavailable"`). Amendment (Marcus, 2026-07-24,
   schema v6): a second per-score option, **Hide Empty Staves on First
   System**, extends the hiding to system 1 (Verovio
   `condenseFirstPage` on the same round-trip — id- and
   timemap-transparent, spikes/hide_first_system.py); default OFF, so
   first-system-full remains the convention, and inert unless hiding
   is on. (c) When a single system is still
   taller than its page after (a)/(b) and condensing — pagination cannot
   split one system — the adapter **scales the whole engraving down
   uniformly so the tallest system fits** (`LoadWarning "scaled-to-fit"`;
   a rastral-size reduction, derived every load, not window reflow). This
   completes never-clip: any orchestral score renders without clipped
   ink. Condensing (rule 11) is the readability lever; scale-to-fit is
   the guarantee.
   (Built in Phase 9: part-label edits re-engrave via the prep seam so
   the score shifts to fit — a re-engrave with changed inputs is not
   window reflow; title/tempo texts edit as stage overlay and never
   re-engrave. See docs/BACKLOG.md item 5, resolved as split.)
   Clarification (video canvas, 2026-08-06): a score Scale past 100 %
   crops the page at the canvas's frame edge, live and in export. That
   is the user framing the video — like pointing a camera — not the
   engraving being clipped; never-clip governs the page layout, and
   the whole page is still there at Scale 100 %.

8. **Every document mutation is an undoable command** (command pattern)
   from the first mutation implemented onward.

9. **ScoreAnim always animates concert pitch.** Verovio's
   `transposeToSoundingPitch: True` is a fixed part of `EngravingParams`,
   not a user option in v1. Exception: parts whose MusicXML `<transpose>`
   is octave-only (`octave-change` with no chromatic shift — e.g. guitar,
   bass guitar) keep their conventional written octave; chromatic
   transpositions are rendered at concert pitch. All fidelity comparisons
   and test expectations are against concert-pitch renders.

10. **Slash AND bar-repeat regions are first-class.** Dorico exports
    slash regions as `<measure-style><slash/>` and measure repeats as
    `<measure-repeat>`, both with no notes; Verovio draws NOTHING for
    either (they import as empty `<space>` — verified Phase 12). The
    adapter synthesizes them: slash elements one per beat
    (`kind = SLASH`), and one `%` bar-repeat symbol per repeated measure
    (`kind = BAR_REPEAT`, onset on the downbeat — Phase 12.2), so both
    render and animate like notes. See docs/ARCHITECTURE.md §3.

11. **Condensing is a prep-seam engraving input; the document stores
    condense groups only.** Dorico's condensing is layout-time and does
    NOT export, so a condensed look is reconstructed in-app: contiguous
    like parts merge onto one staff (one voice per source player,
    combined label) by rewriting the part-list BEFORE Verovio (Phase
    12.3, the Phase 8/9 prep-seam pattern). The doc stores `condense_
    groups` (user intent, schema v5); the merged part-list, geometry, and
    shifted ElementIds all re-derive (rule 5). v1 is naive (Marcus,
    2026-07-21): shared staff, one voice per player, NO a2 unison
    collapse and NO divisi logic (BACKLOG). Load-time layout choices
    (condense, bracket, hide) are gathered in the **Score Setup dialog**
    and applied as ONE undoable step. When a single system is still
    taller than its page after these choices (and repagination), the
    adapter **scales the engraving down uniformly to fit** — the
    never-clip completion (rule 7 amendment c).

12. **The engraved timemap is the single beat authority** (ruling
    2026-07-22, FINDING-1 fix). Every beat in the app — note onsets,
    measure starts/spans, triggers, reveal anchors, rest caps,
    score_end, export ranges, TempoMap positions — lives on ONE axis:
    Verovio's timemap qstamps, exposed as `EngravedScore.timeline`
    (`MeasureTimeline`, per-ordinal starts/durations). This is the
    PERFORMANCE axis: the timemap is playback-expanded, so a repeated
    span occupies its passes' beats (repeated bars keep first-pass
    positions and stay lit through later passes; post-repeat music
    syncs with a recording that takes the repeat).
    `build_score_model` REQUIRES the timeline and rebases music21's
    accounting onto it (`onset = starts[ordinal] + intra-measure
    offset`) — music21's own inter-measure accumulation is never
    trusted (it pads pickups to nominal length, never expands repeats,
    rounds half-beat bars, and can self-diverge between parts;
    spikes/beat_domain.py is the census). One exception: a trailing
    event-less bar (final bar-repeat) has no timemap end, so the last
    measure's span is floored with its notated length. Intra-measure
    offsets stay music21's (an appoggiatura-delayed principal still
    triggers at its notated beat — the shear was inter-measure only).

13. **Selection is object-first; a measure is never selected**
    (ruling 2026-07-27). The user selects OBJECTS — noteheads,
    dynamics, hairpins, texts, barlines. A measure is not a selectable
    thing. Selecting an object implicitly carries its containing
    measure AND the part whose staff it sits on; both are DERIVED from
    the element id grammar, never from geometry, and never stored. A
    barline is an object IN a measure, not the measure itself, so it
    stays selectable — it is M5's only handle. Selection state and the
    way selection LOOKS are both transient render state: never in the
    document, never a style override, never undoable (rule 8 needs
    something to undo). That boundary is what lets M3 exist — the same
    element can be selected (transient) and color-overridden (intent,
    rule 5) at the same time, and the two must stay distinguishable on
    screen.
    Amendment (M7, 2026-07-30): a PART LABEL is the one object whose part
    the id grammar cannot carry. Verovio draws it as a child of the
    system, with no staff ancestor, no MEI `@staff`, and an SVG id that
    does not appear in the MEI at all (measured 0/129,
    `spikes/label_part.py`) — and the label has no measure, so the
    part-bearing id form does not apply to it. Its part is therefore
    joined in the ADAPTER, from document order: the labels a system draws,
    paired against the staves whose MEI label matches the class being
    drawn (`core/engraving/verovio/label_parts.py`). This is document
    order, not geometry, and it is SELF-CHECKING — every pairing is
    confirmed against the label text the score carries, and a label the
    join will not vouch for keeps `part=None`, so the failure mode is a
    disabled rename (warned, `LoadWarning "label-unattributed"`) and
    never a renamed wrong instrument. Downstream still reads the part off
    the identity the adapter minted, exactly as the rule intends; only
    the adapter knows how it was found.
