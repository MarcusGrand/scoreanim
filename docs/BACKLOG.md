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
2. **m. 19 guitar slash notehead renders wrong** (stack of strokes instead
   of a slash). Priority: medium, cosmetic.
3. **"Swing ♩ = 120" renders with a tofu box** before the note glyph.
   Priority: low, cosmetic.
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

## Deferred (from PHASES.md "Later")

Continuous-scroll presentation; glow (needs perf spike); audio-to-score
auto-alignment provider; custom engraving provider; MIDI input; richer
effect editor; arbitrary-exporter MusicXML robustness; in-app editable
score texts with layout shift (item 5 above).
