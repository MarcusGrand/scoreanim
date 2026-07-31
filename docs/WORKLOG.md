# ScoreAnim — Worklog

**NOW:** `main` carries `beta/live-fields` (`ffd0ac8`, no tag), confirmed
in the app: every number field previews as you type. It brought
`beta/shell-layout` with it — the openers on the toolbar, the grid
controls under the lanes, tap tempo gone. Schema is still v10, so a
project saved from `main` will not open on `v0.2-beta.6`.
`beta/f-trackpad-gestures` is merged in too, so the stage navigation is
back: pinch to zoom, two-finger scroll to move.
`fix/bracket-hidden-staves` and `beta/f-fade-effect` are the branches
still unmerged.

Open question from grid-align, still open: whether Tempo mode still
earns its place now that the Tempo field aims at the selected line.

One dated line per session, newest first. Every session reads this file
at start and appends its line at close. Keep entries to one or two
lines — history lives in git and `docs/history/`.

---

- 2026-07-31 — **A fade effect** (`beta/f-fade-effect`, UNMERGED): ink
  rises from the ghost floor to full over a duration, easing out.
  `Easing` gained EASE_OUT and EASE_IN, and `value_at` now looks the
  curve up in a table instead of testing for LINEAR, so the next curve
  is one entry. The effect itself is one registry entry plus its knobs —
  no evaluator, applier or schema change, which the applier tests on the
  real fixture check. Two Marcus calls on the panel: every effect's
  length is now **Duration** with "Entire note value" beside it on the
  same row (the alternative to typing one), and an effect's options only
  show while something resolves to that effect — each preset's block is
  a named heading plus its rows, hidden as a unit. Reset clears pop and
  fade together in one undo step. The panel is at 379 lines: split the
  knob blocks out before adding a third effect.
- 2026-07-31 — **Every number field previews as you type** — the new
  default (`ui/live_field.py`), not the Tempo field's special case:
  Offset, Swing, Amplitude, Settle, Peak offset and Floor opacity all
  show the result on every keystroke and still commit as one undo entry.
  A test scans each host's `live_fields`, so a spinbox added without the
  helper fails the suite. Two things it turned up: a resync must never
  gray out a live field (disabling drops focus, and focus-out commits),
  and Cmd-S was writing the preview instead of the committed document —
  fixed. PATTERNS rewritten; unproven in the app so far.
- 2026-07-30 — **The Tempo field previews as you type**: the ticks move
  on every digit instead of waiting for the click outside, so you can
  see whether a tempo fits the recording while you are still setting it.
  It runs the drag's own preview/commit pair, so the typing session is
  still one undo entry. Two gotchas, now in PATTERNS: the no-op guard has
  to read the new `AppState.committed` (`doc` hands the field back its
  own preview, and it would never commit), and the resync has to skip
  the `setValue` mid-edit or it rewrites the number under the cursor.
- 2026-07-30 — **Ticks is the default lane**, and the Tempo field now
  aims at the selected line: click a line, type a tempo, and it sets the
  tempo from there to the end and releases the locks after it
  (`SetTempoFrom`). That is the tempo line's whole job, so Marcus may
  retire Tempo mode — kept for now. Cosmetics: the padlock is centred on
  a locked BARLINE with the line breaking around it, and locked
  subdivisions get the orange and the weight but no badge.
- 2026-07-30 — **Grid alignment round 2**: double-click a line to LOCK
  it (thick, orange, padlock); locks are the only drag anchors and they
  persist (schema v10, `locked_beats`, beats only — the second is
  derived). A drag now evens the span from the previous lock out to one
  tempo and locks the line it placed, so aligning left to right holds;
  Pin/Ripple became Flatten / Keep shape. Also fixed the view jumping
  out mid-drag — three causes, the real one being that with no audio the
  axis re-fits to the score's own changing length on every preview
  frame. Opened BACKLOG 25-26.
- 2026-07-30 — **Grid alignment** (`beta/grid-align`, UNMERGED): the lane
  gets a Ticks mode where the grid lines are drag handles, at Bars / 1/4 /
  1/8 / 1/8T / 1/16, with Pin or Ripple (Alt flips it). Solved back into
  tempo events — no new document field, no schema bump. Anchors are the
  nearest barline or tempo point, NOT the neighbouring ticks (those choke
  a 1/16 drag). New pure `core/timing/grid.py` + `retime.py`, one command
  `AlignBeat`, `swing_unwarp`, and the lane split into host + modes first.
  Opened BACKLOG 21–24.
- 2026-07-30 — Docs slimmed for lightweight working. The milestone
  ceremony and the two-track process are retired: one track now, no plan
  gate, ask first only for a schema bump, a golden re-capture, or a rule
  change. CLAUDE.md cut 355 → 244 lines (rules keep their short form;
  the long form moved to the new `docs/RULES.md`). ROADMAP, PHASES and
  the briefs moved to `docs/history/` and are out of the read path. The
  session protocol is now WORKLOG only, everything else on demand.
- 2026-07-30 — `beta/f-trackpad-gestures`: stage navigation is now the
  ordinary desktop set — pinch zooms, two-finger scroll moves the view,
  Cmd/Ctrl+wheel zooms, no drag-panning (so, a plain arrow cursor).
  Repeals the M2 "pan is unchanged" ruling in ARCHITECTURE §7. Qt's
  scrollbars are off because they reserve space (measured); a fading
  hint is painted instead. Opened BACKLOG 19. Merged into `main`.
- 2026-07-30 — **Part labels**: the adapter now joins a part label to its
  staff (document order over labelled staves, self-checked against the
  label text), so double-clicking a staff label renames the part —
  BACKLOG 14 closed. A condensed label edits its condense group instead.
  Found and measured a case the spike had missed: a multi-staff part
  hangs its label on the `<staffGrp>` and Verovio draws those FIRST
  (`spikes/label_group.py`). Goldens moved in three fields on label rows
  only. Opened BACKLOG 20. Merged `7ffc3bb`, tagged `v0.2-beta.6`.
- 2026-07-29 — Staff-label direct edit requested → flag-and-stop (it
  moved goldens). Spiked it instead: the MEI-id hypothesis is dead
  (0/129), order-over-labelled-staves is exact (129/129). BACKLOG 14
  updated with the measurement.
- 2026-07-29 — `beta/f-delete-elements`: delete = hide, for engraving
  cleanup only. Del/Backspace on the stage + Edit menu, texts/slurs/
  hairpins/dynamics only, restorable from the layout zone's new
  "Deleted" readout. Rides `LayoutOverride.hidden`; no schema bump, no
  re-engrave. Break commands split out of `layout.py` first. Also fixed
  a tint gap it surfaced (black-filled texts never took the selection
  colour). Merged `38ed04a`, no tag.
- 2026-07-29 — Docs: two-track process encoded, PATTERNS.md and this
  file created, CLAUDE.md slimmed (rules untouched). *(The two-track
  process was retired on 2026-07-30.)*
- 2026-07-29 — `fix/bracket-hidden-staves`: a bracket over hidden staves
  no longer kills the re-engrave; re-engrave failures are now visible in
  the UI instead of silent no-ops. Opened BACKLOG 18 (condense vs staff
  groups cross-validation). UNMERGED.
- 2026-07-28 — **Page breaks CLOSED**: page-break authoring (`plan`
  composition with never-clip, combined `_apply_breaks` pass, schema v9)
  + the left layout zone. Merged `bf3a824`, tagged `v0.2-beta.5`.
  BACKLOG 16, 17 closed.
- 2026-07-28 — **System breaks CLOSED**: system-break authoring, Move to
  Previous System (fat `SetSystemBreak`), schema v8. Merged `d912040`,
  tagged `v0.2-beta.4`.
- 2026-07-27 — **Direct edit CLOSED** (`v0.2-beta.3`): in-place text
  edit, drag-to-nudge, per-element style. Part-label rename unbuilt
  (BACKLOG 14). Selection re-closed after the tint rework.
- 2026-07-25 — **Effects** and **Selection CLOSED**, merged together
  (`v0.2-beta.2`).
- 2026-07-24 — **Shell CLOSED** (`v0.2-beta.1`). Alpha frozen at
  `v0.1-alpha`.
