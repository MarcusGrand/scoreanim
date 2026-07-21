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

## Deferred (from PHASES.md "Later")

Continuous-scroll presentation; glow (needs perf spike); audio-to-score
auto-alignment provider; custom engraving provider; MIDI input; richer
effect editor; arbitrary-exporter MusicXML robustness (Dorico robustness
advanced in Phase 11 — see above). (In-app editable score texts — item
5 — graduated to Phase 9, 2026-07-12.)
