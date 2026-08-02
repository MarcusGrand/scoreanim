# ScoreAnim — Backlog

Items live here so they are not forgotten and not worked on early. Do not
pick these up without an explicit decision.

## Known rendering deviations (vs. the Dorico PDF, found in Phase 0)

See `spikes/NOTES.md` for the full investigation of each.

1. **Sax section bracket missing.** Priority: **fix before first production
   use.** Cause established: the Dorico MusicXML export contains no
   `<part-group>` elements at all, so there is nothing for Verovio to
   render — remedy is a Dorico re-export with bracket/group export enabled,
   or adapter-synthesized brackets.
   **SCHEDULED → Phase 8** (2026-07-12, v2 scoping): remedy chosen —
   `<part-group>` injection at the prep seam from doc-stored groupings
   (verified at scoping: Verovio renders the `grpSym` bracket AND joins
   barlines through the group; see `spikes/NOTES.md` "v2 scoping
   probes"). No Dorico re-export needed; render-side synthesis rejected
   (group-barline connectors need engraving collision avoidance).
   **BUILT 2026-07-12 (Phase 8)**: groups defined in-app (Parts → Staff
   Groups…), stored as intent (`staff_groups`, schema v3 — no bump),
   injected at the prep seam, undoable (Add/Edit/RemoveStaffGroup);
   ElementId stability across the grouped re-engrave pinned by test
   (which also discharges item 5's "verify" note).
   **CLOSED 2026-07-12**: Phase 8 exit criteria passed (user's
   interactive run, accepted).
   **RE-OPENED → Phase 10 (2026-07-13)**: only ONE group works; adding
   a second makes Verovio draw a `systemDivider` glyph the decomposer's
   SVG-class whitelist rejects (raises "unknown SVG class"). The
   grouping logic itself is correct (two disjoint groups validate and
   inject cleanly — verified); this is a decomposer-coverage gap, fixed
   as Phase 10 task 10.4. N-group loading pinned by test at close.
   **CLOSED 2026-07-13 (Phase 10.4)**: root cause was deeper than the
   whitelist — Verovio's `condense:"auto"` default silently switches
   to condensed layout at 2+ staff groups, HIDING empty staves per
   system (testscore: 7/3/6/3/5 staff rows) and drawing the divider.
   The adapter now pins `condense:"encoded"` (rule-7-reinforcing fixed
   option, the transposeToSoundingPitch shape; 0/1-group renders
   byte-identical — triage spike section E). Two groups → 10 span-keyed
   grpSyms, zero dividers, all staves; `SYSTEM_DIVIDER` mapped
   defensively anyway (static kind, synthetic-SVG test). N≥2 loading +
   two-group id stability pinned in tests/test_adapter_groups.py;
   in-app two-bracket add/undo verified in the Phase 10 exit run.
2. **m. 19 guitar slash notehead renders wrong** (stack of strokes instead
   of a slash). Priority: medium, cosmetic.
3. **"Swing ♩ = 120" renders with a tofu box** before the note glyph.
   Priority: low, cosmetic. (Upstream: Verovio duplicates the metronome
   codepoint into the 405px text run, where the text face has no glyph.)
   User-side workaround since Phase 9.2: the tempo overlay replaces the
   whole mark with plain text — the seed collapses the doubled
   codepoint, so the replacement reads "Swing ♩ = 120", no tofu.
4. **Dorico title block simplified** to Verovio's one-line running header
   (all credit texts present, size/placement differ). Priority: low,
   accepted as-is.

## Planned capabilities (user rulings, not scheduled)

5. **In-app editing of score-anchored texts** (Marcus, 2026-07-11, at
   Phase 2 closure): part labels, the title block, tempo markings and
   similar texts should be editable in the app, **and the engraved score
   should shift to accommodate the edited text** — not float over it.
   Implications to work out when picked up:
   - Editing implies a re-engrave with modified inputs (text overrides
     applied to the canonical MusicXML before Verovio), not a stage-text
     tweak. Rule 5 holds: the project stores the text *edits* (user
     intent); the shifted layout is re-derived. Rule 7 holds: encoded
     system/page breaks stay honored — a re-engrave with changed text is
     not window reflow.
   - This extends/partially revises ARCHITECTURE.md §3 ruling 4: today
     title/composer are stage-level texts that never re-engrave. Some
     texts may move back into (or gain a path into) the engraving inputs;
     stage texts remain for purely overlaid/animated text.
   - ElementId stability across such re-engraves matters (ids are minted
     from musical identity, so they should survive; verify).

   **REVISED + SCHEDULED → Phase 9** (2026-07-12, v2 scoping): re-engrave
   is cheap — 0.23 s measured for full engrave+decompose — so the split
   is by TEXT CLASS, not by cost of reflow. Title/composer (already
   stage texts) and tempo marks (float in empty space) edit as OVERLAY
   and never re-engrave; only PART LABELS take the re-engrave path
   (fixed left column engraved from the longest name — overlay edits
   collide with the staff). Phase 9 rides Phase 8's prep-injection
   infrastructure; the id-stability "verify" above is pinned by test in
   Phase 8 (task 8.3).
   **RESOLVED as split, BUILT 2026-07-12 (Phase 9)**: stage texts edit
   via EditStageText + band refit (9.1); tempo marks via
   AddTempoOverlay — hidden layout-override + replacement stage text,
   one undo step (9.2); part labels via text_overrides rewritten into
   the part-list at the prep seam → re-engrave, score shifts to fit,
   rename keeps the id set identical (pinned, 9.3). Editing UI: Edit →
   Texts… and Parts → Part Names… dialogs (stage click-to-select
   remains item 9).
   **CLOSED 2026-07-13**: Phase 9 exit criteria passed (user's
   interactive run, accepted).

## Animation fixes required (user rulings)

6. **Ledger lines must dim with their notes** (Marcus, 2026-07-11, at
   Phase 3 review). **FIXED 2026-07-11 (Phase 4 task 4.0a)**: the adapter
   emits each ledger dash as its own LEDGER_LINES element, attributed to
   its notehead by horizontal-overlap + staff-side within
   (page, measure, staff); a shared dash takes the earliest owner onset.
   Ties resolve through the schedule's attachment-group rule (the dash
   inherits the owner's onset+voice). Pinned:
   tests/test_adapter_layout.py::test_ledger_dashes_are_note_owned_elements
   (90 dashes, 15/44/31 per page; every STAFF_LINES back to exactly
   5 paths).
   Original ruling: ledger lines stayed at full opacity while the notes
   sitting on them were at floor opacity.
   Cause (established): Verovio gives `<g class="ledgerLines">` no ids
   (Phase 0 finding), and the adapter lists `ledgerLines` in
   `_CONTAINER_CLASSES` (verovio_adapter.py), so its dash paths fold
   into the enclosing staff's STAFF_LINES element — static scaffold by
   the Phase 3 animated-ink ruling. Verified on the fixture: the 133
   STAFF_LINES elements carry 5 staff-line paths plus 1–7 ledger dashes
   wherever ledger notes occur.
   Fix shape: stop folding — emit ledger dashes as their own minted
   elements (OTHER-with-onset already animates, or add a LEDGER_LINES
   kind), attributing each dash to a notehead by geometric overlap
   (bbox x/y within the same staff+measure; a dash shared by several
   heads takes the earliest of their resolved triggers). Verify:
   staff-line path count returns to exactly 5 everywhere; a ledger-note
   measure (e.g. P4 mm 2–5) dims dashes with its notes.

7. **Per-region swing authoring UI** (Marcus, 2026-07-11, at Phase 4
   re-test): v1 swing is one global ratio on the transport bar
   (SetGlobalSwing). The document model, commands
   (Add/Set/RemoveSwingRegion), warp math, and serialization already
   support arbitrary non-overlapping regions — only the authoring UI is
   deferred ("we will implement more sophistication later"). When picked
   up, match the tempo-event editing idiom.

8. **Single-wavefront sweep mode** (Marcus, 2026-07-12, at the Phase 5
   reveal re-plan): "Sweep means sweep" — when Sweep is on, ONE smooth
   shared wavefront per system moves in tempo and reveals EVERYTHING
   (all animated ink, through glyphs). **Barlines and staff scaffold
   sweeping too is RULED WANTED, not scheduled** (Phase 5 close-out) —
   include it in the wavefront design round. Ties are irrelevant to the
   front ("we shouldn't have to worry about tied notes being regarded
   as a single note" in this mode) — a different computational model
   from the stepped per-(system, part) event anchors. Design sketch to
   propose when picked up: a per-system front x(t) from
   measure-boundary geometry (measure starts ↔ barline x, lerped in
   tempo) rather than note anchors; ghost + clipped-copy layers
   generalized from spanners to all ink incl. scaffold (~2× path items,
   measure); opacity triggers route to no-op for OPACITY in sweep mode
   (pop's SCALE still fires); mode switching must stay scrub-stateless.
   Until then the Sweep toggle drives the placeholder continuous mode
   (anchor lerp).

9. **Per-element style override UI** (deferred at Phase 5.3): the model,
   `SetElementStyle` command, and serialization exist and are tested;
   the editing UI waits on stage click-to-select (which layout
   overrides also need). On a spanner broken across systems an override
   targets ONE segment (`…:seg<k>` ids) — decide whether the UI should
   fan out to all segments of a source when it lands. (Phase 9's Texts…
   dialog is list-based on purpose — text editing did not wait for
   click-to-select; this item is about the general per-element case.)
   **HALF DONE (M2, 2026-07-25):** click-to-select exists — the
   selection, its highlight, and the identity readout ship; the editing
   controls in the Selection panel are M3. The `:seg` fan-out question
   is still open, and the panel already labels a segment selection
   "Slur (segment 1)" so it never implies the whole spanner is picked.
   Three M2 seams M3 inherits: (a) **stage texts are unselectable**
   (`ElementItem(identity=None)` — title/composer/lyricist and tempo
   overlays), so M3's double-click-to-edit needs its own hit path for
   them; (b) **selection is not re-resolved after a re-engrave** — it
   clears, though musical ids usually survive, so re-resolving via
   `scenes.items.get(eid)` is available polish; (c) `measure_ordinal_of`
   duplicates `schedule.py`'s private `_MEASURE_RE` — if a third caller
   appears, promote the public helper and migrate.
   **DONE (M3.3, 2026-07-27).** The Selection panel's style controls
   (`ui/panels/selection_style.py`) write colour and effect through
   `SetElementStyle`, plus "Clear style overrides". The `:seg` question
   is **resolved: fan out** (ruling, after `spikes/seg_fanout.py`
   audited the grammar on 4 fixtures / 116 broken spanners — no
   nesting, no orphans, no identity mismatch). `core/editing/segments.py`
   is the family arithmetic; `SetElementStyle` gained a `segments` field
   so the family is ONE undo entry (the "fat apply" idiom, not a new
   command class). The panel still labels the pick "Hairpin (segment
   1)" — it is the OVERRIDE that spreads, not the selection.
   Of the three inherited M2 seams: **(a) is resolved** — M3.1 gave
   stage texts their own double-click hit path, so D5 stands and they
   are editable without being selectable; **(b) is still open** —
   selection still clears on re-engrave rather than re-resolving via
   `scenes.items.get(eid)`, and nothing in M3 needed it; **(c) is still
   open** — `measure_ordinal_of` still duplicates `schedule.py`'s
   private `_MEASURE_RE`, and M3 added no third caller.

   **(b) CLOSED (M5.5, 2026-07-28), (c) still open.** M5 was the first
   milestone with a concrete reason to want (b): toggling a break
   deselected the barline you had just clicked, so toggling back needed
   a fresh click on ink that had moved. `SelectionController.bind_scenes`
   now re-resolves the held identity against the FRESH item table —
   restored when the id survived, cleared when it did not — which the
   spike justified by measuring all 19 of testscore's measure-scoped
   barline ids byte-identical across both a forced and a suppressed
   break. Re-resolution, not retention: the restored identity is the new
   item's. One wrinkle worth remembering: `AppState.set_selection`
   no-ops on an EQUAL identity and fires no signal, so the controller
   re-lights the tint explicitly rather than making AppState re-emit for
   everyone. (c) is untouched — M5 read `Selection.measure_ordinal` as
   the M2.8 note asked, so there is still no third caller.

   **M2.8 (2026-07-27) removed the hard part of the color case:**
   authored color and the selection tint are separate channels composed
   in `ElementItem`, so a per-element override is written through
   `set_color` (which the DocumentSync diff cache owns) and never
   collides with the transient highlight — including the case where the
   user picks the selection color itself, which falls back to
   `SELECTION_ALT_COLOR`. M3 adds a writer for the authored channel and
   must not add a second writer for the tint. Note (c) now has a second
   caller shape: `Selection.measure_ordinal` wraps it, so M5 should read
   the property rather than call the helper directly.

9b. **`ui/main_window.py` is at the 400-line ceiling** (399 after M2's
   wiring; the no-monoliths rule says split BEFORE adding more).
   Candidate seams: page/system routing (`show_page`/`show_system`/
   `step`/`show_current`/`_on_*_followed`/`_sync_presentation_mode`,
   ~70 lines) into a `ui/view_router.py`, and the four dialog openers
   into the components that own their data. M3 must do this before
   adding window-level wiring.
   **Still open after M2.8 (2026-07-27), and still at 399:** the
   selection rework needed ZERO lines there — its four selection lines
   are construction and wiring, and every edit landed in
   `ui/selection.py`, `render/items.py`, `render/animate.py`,
   `core/selection/` and the panel. So the split was correctly NOT done
   here; it remains M3's to do first.
   **DONE (M3.0, 2026-07-27), as the first commit on the branch and
   with no feature code in it:** 399 → **312** lines (317 after M3's own
   wiring). Both of the seams named above were used.
   `ui/view_router.py` took the position state and the six routing
   methods, bound per load like `DocumentSync`; `MainMenus` grew
   `set_position()` so the router never reaches for the readout widgets
   the chrome owns. `ui/parts_menu.py` took Score Setup / Staff Groups /
   Part Names **and** the `_parts` tuple they guarded on — `rebuild()`
   was already called with the parts on every load, so the three
   `Callable`s the window passed down disappeared with it. The fourth
   opener, Texts…, moved at M3.1 to `ui/text_edit.py`: 9b's criterion is
   "the component that owns their data", its data is the current
   engraved layout, and no component owned that until in-place text
   editing existed. `tests/test_view_router.py` (12 stub-based tests)
   gives the routing coverage it never had while it was window methods.

10. **Per-voice reveal granularity** (accepted limit at the Phase 5
    reveal re-plan, ruling A): reveal edges are per (system, part), not
    per voice — a moving second voice under another voice's held tie
    sits inside the revealed region early. Voice labels relabel per
    measure (the m18→19 hi-hat tie), so voice-level keying needs a
    stable voice identity first. Revisit only if it shows on real
    material.

## Export (deferred at Phase 6, 2026-07-12)

11. **Project-persisted export settings** (ruling R3 deferred the
    alternative): fps/format/size/range are session memory on the
    dialog only (Phase 7.5 added system-mode canvas_w/canvas_h to the
    same session dict, mode-keyed). Persisting per-project means an
    ExportConfig on ProjectDoc, an undoable SetExportConfig command
    (rule 8), and a schema bump — v3 landed in Phase 7.1 WITHOUT this
    field (v3 carries only floor/mode/groups/text-overrides), so this
    would be v4. Pick up only if re-entering settings proves annoying
    across sessions.

12. **Fractional/NTSC frame rates (29.97/23.976)**: v1 export is
    integer fps only — FrameClock, frame_count, and the ffmpeg
    `-framerate` argument would all need rational timebases end-to-end.
    Noted in the dialog; no demand yet.

13. **Hardware ProRes encode** (`prores_videotoolbox`): the software
    `prores_ks` encoder keeps up with rasterization today (~36
    frames/s at 1526×2160 on the fixture), so this is a perf option,
    not a need. Revisit for long scores or 4K-height exports.

## Dorico robustness (Phase 11 progress, 2026-07-19)

Phase 11 made the loader robust to arbitrary Dorico exports, using
`testdata/complex1.musicxml` (14 parts, 921 notes) as the milestone:

- The **score-doctor** (`python -m scoreanim.tools.check_score`) is the
  standing triage tool — one command loads any MusicXML and prints PASS
  with a census or the exact failure stage. The routine loop for a new
  export is doctor → smallest fix → fixture.
- **Graceful degradation**: an unknown drawable SVG class degrades to a
  warned static element in the app path (`unknown-class`); strict loads
  (pytest / doctor `--strict`) still raise (CLAUDE.md rule 4).
- Decomposer/geometry coverage landed: tremolo strokes (bTrem/fTrem —
  animate untinted, ruling a), beamSpan, rotate transforms, and the
  mRest ledger tier.
- **complex2** (orchestral, `docs/PHASE12_BRIEF.md`) loads through
  decomposition (42,615 elements) but overflows every system — its
  layout, and the order-based grace/appoggiatura join rewrite (which
  fixes complex1's pinned 899/921 gap too), are **Phase 12 (task 12.1)**.
- Tremolo animation polish (the stroke dims/lights with its note but
  stays black — untinted per ruling a): if a tinted-stroke look is ever
  wanted, it is a one-line TINTED_KINDS add, parked here.

## Phase 12 (orchestral robustness) — deferrals

Built 2026-07-21: complex2 lays out (order-based join, bar-repeat
synthesis, prep-seam condensing + schema v5, Score Setup dialog, auto
scale-to-fit). Parked:

- **Condensing sophistication.** v1 is naive (shared staff, one voice per
  player). No **a2 unison collapse** (a unison passage draws doubled
  noteheads/stems), no **divisi** logic, no per-passage condensing (a
  group is condensed for the whole piece or not at all). These are the
  Dorico-condensing features that would make the merged look match the
  PDF; v1's target is "usable and clean", and the user picks sane pairs.
- **Hide-empty-staves is a no-op on scores with percussion slash/repeat
  regions.** Those staves import as `<space>`, so Verovio's `optimize`
  would hide them → the rule-10 fallback disables hiding globally
  (`hide-unavailable`). Scale-to-fit (rule-7 amendment c) now guarantees
  the layout regardless, so hiding is a readability nicety here, not the
  overflow fix. A proper fix (keep slash/repeat staves visible under
  optimize by filling their region measures with invisible rests so
  hiding can thin the genuinely-empty staves) is parked.
- **Condensing multi-staff parts** (e.g. two grand-staff keyboards) is
  rejected in v1 (raises); needs a per-staff merge design.

## Phase R (adapter package split) — deferrals

- **`_LoadState` narrowing** into per-stage inputs: every stage module
  now documents which fields it reads/writes, but the type is still one
  shared mutable dataclass. Explicitly deferred by the refactor brief.
- **`_identity_for` onset-chain table**: the svg_class-gated if/elif
  chain works and is pinned by the goldens; restructuring it into a
  dispatch table is deferred (brief).
- **Redundant re-prepare in the scale-to-fit path** (R.4 finding F4):
  when systems overflow but `plan_page_breaks` returns no breaks,
  `load_detailed` re-runs `prepare()` with identical inputs before the
  scaled engrave — wasted work, output unaffected. Perf work is out of
  the refactor's scope (brief).
- **Golden snapshots are the standing regression net** for all future
  adapter work: `tests/goldens/` pins 12 loads byte-for-byte
  (`SCOREANIM_UPDATE_GOLDENS=1` re-captures after a deliberate change —
  commit the diff with the change that caused it).

## One beat domain (FINDING-1 fix, 2026-07-22) — deferrals

- **Repeat-skipping recordings.** The beat axis is performance time
  (playback-expanded timemap, CLAUDE.md rule 12), which syncs with a
  recording that TAKES the repeats. A recording that skips a repeat
  currently needs an ugly tempo-map workaround (a near-infinite-bpm
  region over the skipped pass); a proper affordance (per-repeat
  "played/skipped" toggle compressing the timeline) is future work.
- **Second-pass cosmetics.** During a repeat's later passes the tap
  label reads as extra beats of the repeated bar (e.g. "m37 beat 6"
  in a 4/4 bar) and the tempo lane draws no gridlines inside the
  expanded span (clone downbeats carry no measure ordinal). Accepted
  for v1; fixing needs an expansion map from the timemap clones.

## M1 Shell (2026-07-24) — deferrals

- **Systems toggle has no menu home** (brief flag 4): the roadmap's
  View menu lists fit/prev/next/dock toggles and Playback lists Follow,
  but neither lists Systems. M1 leaves it inspector-only; a View-menu
  item is a one-liner if wanted.
- **Lower-zone lane heights are not persisted.** `QMainWindow.saveState`
  does not cover the waveform/tempo-lane QSplitter inside the dock;
  M1.8's scope was geometry + dock state + section expansion. A
  `saveState()`-of-the-splitter one-liner in `ui/window_state.py` if
  wanted.
- **`render/export.py` comments still say `_load_score`** (renamed
  `MainWindow.load_score` in the M1.9 split). Comment-only staleness
  left in place because M1's boundary forbade touching `render/`.

## M4 Effects (2026-07-25)

- ~~**Per-part effect authoring gap (until M3).**~~ **CLOSED (M3.3,
  2026-07-27, ruled in scope).** The Selection panel's style controls
  carry a scope switch — this element / this part — so a per-part
  effect rule is authorable again through `SetPartEffect`, keyed by the
  part the selection already carries (rule 13). It governs colour as
  well as effect, and disables itself on score-level ink, which has no
  part.
- **Pre-swell-on-floor-ghost variant.** Peak offset is a uniform
  signed trigger shift (brief F3): at a negative offset the note also
  BECOMES VISIBLE early. If appearance-on-beat with a pre-swell of the
  floor ghost is ever wanted, that is signed `t_rel` keyframes — a new
  preset and a real model change, not the existing knob.

## M3 Direct edit (2026-07-27)

14. **A part label carries no part, so it cannot be renamed by
    double-clicking it** — **CLOSED 2026-07-30 (M7).** The adapter now
    joins a label to its staff by document order, self-checked against
    the label text (ARCHITECTURE obligation 17,
    `core/engraving/verovio/label_parts.py`), and the M3 route lit up
    with no change to `SetPartText`, the prep seam, or the schema. The
    goldens moved in exactly three fields on label rows — `part`,
    `part_name`, `staff` — with no id, geometry or onset change, because
    a label has no measure and so never took the part-bearing id form.
    Building it turned up one case the spike's 6 configurations did not
    contain: a MULTI-STAFF part hangs its label on the `<staffGrp>`
    around its staves, not on a `<staffDef>`, and Verovio draws every
    group label FIRST — so video_test placed 0 of 7 labels until the join
    grew a second tier (measured 41/41, `spikes/label_group.py`). All 16
    fixture configurations now place every label with zero warnings
    (1354 labels). The original analysis, kept because it is what the
    work was measured against:
    MEASURED, not assumed:
    Verovio emits labels as direct children of `<g class="system">` with
    no staff or part ancestor, so the adapter mints them
    `score:p<PAGE>:text:<n>` with `part=None`, and `tests/goldens/`
    pins that null. `SetPartText` is keyed by `PartId`, so the route
    cannot be completed from the UI side at all.
    Resolving it means attributing labels to parts in the adapter —
    plausibly via the MEI index, since the label's xml:id should reach
    a `staffDef` — which is an adapter change that MOVES GOLDENS, and
    therefore outside M3's "UI affordances, not new document semantics".
    Geometry or vertical order could infer the part instead; both were
    rejected as fragile (hidden staves and condensing perturb both, and
    rule 13's spirit is that context comes from the id grammar, never
    from position). Until then, Part Names… remains the way to rename.

    **MEASURED 2026-07-29 (`spikes/label_part.py`, 129 labels over 6
    configurations). The MEI-index hypothesis above is FALSE: 0/129.**
    A rendered label's SVG id does not exist in the MEI at all —
    Verovio mints a throwaway id for the drawn object and
    `getElementAttr` answers "Element not found". Notes join fine (the
    spike's control), so this is specific to labels.
    What the spike DID find is a join that works: the MEI side is clean
    (every label hangs on a `staffDef` carrying `@n`, the global staff
    number, which `part_for_staff` turns into a part), and pairing a
    system's drawn labels against its visible staves **filtered to
    those whose staffDef carries a label of the class being drawn**
    (`label` on system 1, `labelAbbr` after) is exact — 129/129 with
    zero text disagreements, under hidden staves and condensing alike.
    Naive order without that filter is 101/129 and MIS-ATTRIBUTES
    rather than failing, because a part with an empty abbreviation
    draws nothing after system 1.
    The join is self-checking: each pairing can be verified against the
    staffDef's own label text, so the adapter can attribute only on
    agreement and leave the label part-less otherwise — the failure
    mode is then a disabled action, never a renamed wrong instrument.
    A condensed label names the KEPT part (`parts[0]`), so condensing
    raises no extra decision.
    Still milestone work: it moves the goldens (36 label elements in
    bigband1_hidden alone) and changes what the adapter mints.
    The routing policy is written and unit-tested
    (`tests/test_text_route.py`), and `tests/test_text_edit.py`
    asserts the current limitation so it fails the moment labels gain a
    part.

15. **Nudge is excluded from "Clear style overrides"** (M3.3, deliberate).
    The button clears colour and effect on the whole `:seg` family in one
    undo entry; a `LayoutOverride.dx/dy` lives in a different part of the
    document, so folding it in would make one click either two undo
    entries (rule 8) or need a command that does not exist. Undo and
    drag-back cover it today. Revisit if a combined "reset this element"
    is actually wanted.

## M5 Breaks (2026-07-28)

16. **`_repaginate` destroys a system break that is encoded only as a
    page break.** **CLOSED 2026-07-28 (M6.0)** — paid as its own commit
    with no feature code, per the brief's D0. `_repaginate` now promotes
    every encoded `new-page="yes"` to also carry `new-system="yes"`
    before it strips, so a repagination may not change SYSTEM content —
    which is what rule 7(a) always claimed and did not do, and is now
    written into rule 7's M6 amendment.

    One correction to the "likely fix" note below, found at build: the
    fix is **not** golden-free. The brief's F1 probe measured it as a
    no-op on all four fixtures, but probed each in one configuration and
    missed both golden loads that actually repaginate. `video_test_flat`
    moves only its canonical-XML hash and its load-warning ORDER (the
    engraving is byte-identical; a new `<sb>` shifts Verovio's seeded id
    sequence), and `complex3_hidden` goes from 20 systems to **21 —
    exactly its encoded set**. The hidden load had been silently losing
    an encoded system break on `main`, so the movement is the damage
    being repaired, not new. Both baselines re-captured in the fixing
    commit, the golden suite's own protocol.

    CLAUDE.md rule 7(a) says the never-clip repagination
    "keeps the system breaks, re-derives page breaks". It does not:
    `core/score/musicxml_rewrite.py:_repaginate` strips ALL encoded
    `new-page` attributes before asserting its own plan, and a measure
    whose only break marker was `new-page="yes"` loses its system break
    with it. Both fixtures have such measures — testscore encodes m5 and
    m13 that way, bigband1 m12 and m20.

    Pre-existing Phase 10R behaviour, and latent until now for a precise
    reason: complex3 is the only fixture that repaginates at baseline,
    ALL twenty of its breaks are page-encoded, and `plan_page_breaks`
    happens to re-derive exactly the same twenty positions — so the
    strip-and-re-assert is a no-op in effect. M5 is the first feature
    that changes system heights and can therefore make the plan diverge
    from the encoded set. Forcing a break at testscore's m19 repaginates
    and merges systems 1+2 and 3+4 as a side effect; on bigband1,
    forcing at m3 takes 9 systems to 8 rather than 10 for the same
    reason (the spike recorded the count, brief §3.3 C1, without
    identifying the cause).

    Every M5 mechanism is correct on top of it — the forced break
    survives the retry, the page count stays owned rather than clipped,
    and the beat authority does not move — so this was flagged rather
    than fixed inside a milestone whose charter is a layout-intent edit.

    Likely fix, small but golden-touching: before stripping, promote
    each encoded `new-page="yes"` to an explicit `new-system="yes"` on
    the same measure, so the system break survives the page-break
    re-derivation. Needs a golden re-run on complex3 (where it should be
    a no-op) and a decision on whether a repagination is allowed to
    change system content at all.

17. **Left-side retractable layout zone** (deferred at M5.7, 2026-07-28).
    **CLOSED 2026-07-28 (M6.6/M6.7)** — built as the re-home this entry
    specified, once M6's page toggle made it three actions. It is a
    re-home structurally, not just in intent: `ui/layout_zone.py`'s
    buttons take the Score menu's QAction objects as their
    `defaultAction`, so label, enabled state, status tip and trigger come
    from ONE object and the two surfaces cannot diverge; the zone syncs
    nothing of its own, and the menu keeps every action. It adds no
    document field, no command and no engraving input — the overrides
    readout (`ui/panels/break_overrides.py`) clears an entry with the
    same `mode=None` the toggle already sends. The existing `saveState`
    pair persists the third dock with no new code, and `_STATE_VERSION`
    did not need bumping (measured, D10).

    A collapsible panel down the left of the stage collecting the
    layout/engraving affordances: today's two system-break actions
    ("Toggle System Break Here", "Move to Previous System"), and
    page-break authoring when it lands. Today they live in the Score
    menu with the other layout choices (D1), which is right while there
    are two of them and wrong once there are six — break authoring is
    the kind of work you do in a pass down a score, and a menu round
    trip per edit is the wrong shape for that.

    Deliberately deferred until more than one action needs a home: a
    zone with two buttons in it is a worse Score menu. When it is built
    it is an **M1-style re-home of existing commands, not new
    semantics** — the policy is already pure (`core/editing/breaks.py`),
    the QActions already exist and are already re-inserted per load by
    `ui/parts_menu.py`, and `ui/break_action.py` already owns the
    enable/label sync. The zone would host the same QActions; nothing
    below the UI changes, exactly as a stage context menu would not
    (D1's own note).

    Candidate **M6 pairing with page-break authoring**, which ROADMAP
    deferred until M5 proved the pattern. Two features that want the
    same home and share a seam are cheaper together than apart.

## Staff groups (bracket bug fix, 2026-07-29)

18. **`condense_groups` and `staff_groups` are validated against
    different part orders.** `_validated_groups`
    (`core/project/commands/layout.py:23`) checks a staff group against
    the part order the document was loaded with, but `_apply_condense`
    runs BEFORE `_inject_part_groups` at the prep seam
    (`musicxml_prep.py:315`) and physically removes absorbed parts from
    the `<part-list>`. So a condense group that swallows a part named by
    a staff group passes command validation and then raises
    `ValueError: staff group names unknown part 'P2'` mid-load. Both
    sets are authorable in one `ApplyScoreSetup`, and a saved project
    can carry the pair. There is no cross-validation and no test.

    Found while fixing the bracket-over-hidden-staves crash, which had
    the same shape: a seam-level `ValueError` reaching an unguarded
    re-engrave. That guard (`main_window._on_document_changed`) now
    turns this into a visible "re-engrave failed: …" instead of a
    silent no-op, which is why this is a backlog item and not a bug.
    The real fix is to validate the staff groups against the
    POST-condense part order — one shared helper, since the two
    commands already share `ApplyScoreSetup`.

## Stage navigation (2026-07-30)

19. **The inline text editor does not follow the view.**
    `ui/text_edit.py` places the editing field once, mapping the item's
    scene rect through `mapFromScene` at open time
    (`_place_editor`-style code around line 208). Nothing re-anchors it
    afterwards, so zooming or scrolling while a field is open leaves the
    field behind while its text moves.

    This is not new — drag-panning had the same effect since M3.1 — but
    two-finger scrolling makes it far easier to trigger by accident, so
    it is worth paying. The fix is small: give `StageView` a signal for
    "my transform or scroll offset changed" (emit it from `zoom_by`,
    `scroll_by`, and `scrollContentsBy`), and have `text_edit`
    re-place an open editor from it. Deliberately left out of the
    navigation change to keep that diff about navigation.

## Labels (M7, 2026-07-30)

20. **The Score Setup dialog cannot edit a condense group once the score
    is condensed.** MEASURED while building M7's condensed-label route.
    The dialog is handed `LoadedScore.parts`, which is
    `engraved.prepared.parts` — the POST-condense part list. So after
    condensing P1+P2, the order it validates against is
    `(P1, P3, P4, …)`, the group it is editing still names
    `(P1, P2)`, and `_validated_condense_groups` raises
    `CommandError: condense group names unknown part 'P2'`.
    `AppState.execute` reports and swallows it, so renaming a condense
    group in the dialog silently does nothing. The same list is also why
    the dialog cannot offer P2 as a member of a NEW group.
    M7 needed the fix for its own route and took the narrow one:
    `editing.flat_part_order` rebuilds the score's order from the
    condensed one plus the groups — the exact inverse of
    `_apply_condense`, which keeps each group's first part in place and
    drops the rest. The dialog should use it too, but that is a wider
    change (Score Setup, Staff Groups and Part Names all take the same
    tuple) with its own blast radius, so it is not M7's to make.

    The better fix, if it is worth the load cost, is for `ScoreLoader` to
    retain the FLAT part order from a second `musicxml_prep.prepare`
    (measured 14 ms on testscore, 349 ms on complex2 — noise against a
    load that already takes 0.6 s to 20 s) and hand THAT to every dialog.
    Then no caller has to reconstruct anything, and reconstruction cannot
    go wrong on a stale group (rule 5) the way `flat_part_order` can.
    Related: item 18, the same family of "validated against the wrong
    part order" bug.

## Grid alignment (2026-07-30)

21. **A repeated pass gets subdivision ticks but no barlines.** The lane's
    grid takes its bars from `MeasureInfo`, which holds one entry per
    document-order measure, so the bar at a repeat end carries a
    `quarter_length` covering the whole second pass (measured on
    complex3: ordinal 37 spans 12.0 for a 4/4 bar, because
    `provider._engrave_prepared` keeps first-pass starts only —
    `setdefault` plus the `measure_by_id` guard drops the `-rend<k>`
    expansion clones). The pass offset is a whole number of quarters, so
    the beat ticks across it are still real beats and dragging them is
    correct; only the interior barlines and their numbers are missing.
    Pre-existing — today's measure grid has always drawn it this way.

    The fix, if it is wanted: strip the `-rend<k>` suffix in the provider,
    map the base id back through `mei.measure_by_id`, and carry the extra
    pass starts on `MeasureTimeline` as derived data (rule 5, no schema
    bump). It touches the beat-authority seam, so it deserves its own
    decision rather than riding along.

22. **The lane's mode, grid step and Flatten/Keep-shape are not
    persisted.** They are view state by design (rule 5), so they reset to
    Tempo / Bars / Flatten every launch. If that gets annoying they
    belong in `window_state` with the dock geometry, not in the project
    file.

23. **No snapping a dragged line to the audio.** The obvious next want is
    for a barline to snap to a transient under it. We have peaks, not
    onsets, so this is a real piece of work (onset detection, plus a
    modifier to defeat it), not a tweak.

24. **`commands/timing.py` now does three jobs** (tempo events, taps,
    swing) in ~300 lines. The next timing command should split it first.

25. **A lock outside the score is inert and invisible.** Locks are beats,
    so re-loading a score with fewer measures leaves any lock past the
    new end with nothing to draw and nothing to anchor. It is inert
    rather than wrong — the same treatment a stale break override gets —
    but there is no readout saying so. If it bites, the layout zone's
    "Deleted" readout is the precedent to copy.

26. **Locks constrain tick drags only.** The Offset field, a tempo-point
    drag in Tempo mode and a `.tempo` re-import all move locked beats;
    only the last of those clears the locks. Solving the map against the
    locks instead would make them a real constraint, which is a much
    bigger change than it sounds and probably the wrong one — the user
    reached for a more direct tool.

27. **Does Tempo mode still earn its place?** (Marcus, 2026-07-30, on
    first use of the Ticks lane: "I'm not sure if we even need the tempo
    view anymore.") Everything it does now has a replacement — dragging
    a line beats dragging a tempo point, and the Tempo field aimed at a
    selected line replaces editing a point's bpm. What would go with it:
    `ui/lane_tempo.py`, the Lane combo, `AddTempoEvent`/`MoveTempoEvent`/
    `RemoveTempoEvent`'s only UI surface (the commands themselves stay —
    the strip and tap derivation use them). Left in for now so he can
    live with the new one first.

28. **Ink with a colour of its own does not follow the page ink.**
    (Opened 2026-08-02 with page colours.) `fill_tracks_color`
    (`render/items.py`) asks what the SVG SOURCE said: absent or black
    means "the default, written out" and follows the page; a real colour
    is a deliberate choice and is kept. So a deliberately-coloured piece
    of ink stays its own colour on a recoloured page. Today that is one
    thing on one fixture — testscore's lyricist credit at `#c0c0c0`,
    which is light grey and still perfectly readable on a dark page —
    so nothing is actually broken. It would bite if a score authored
    something DARK, which would then vanish against dark paper.
    Fixing it means deciding what an authored colour means when the user
    has recoloured the page, and that answer also governs part tints and
    per-element overrides, so it is a real design question rather than a
    predicate change. Left until a score actually shows the problem.

## Deferred (from docs/history/PHASES.md "Later")

Continuous-scroll presentation; glow (needs perf spike); audio-to-score
auto-alignment provider; custom engraving provider; MIDI input; richer
effect editor; arbitrary-exporter MusicXML robustness (Dorico robustness
advanced in Phase 11 — see above). (In-app editable score texts — item
5 — graduated to Phase 9, 2026-07-12.)
