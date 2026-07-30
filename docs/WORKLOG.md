# ScoreAnim — Worklog

**NOW:** Part labels rename by double-click, which closed the last piece
of the direct-edit work. `main` is clean and unpushed. Two branches are
still unmerged and independent: `beta/f-trackpad-gestures` and
`fix/bracket-hidden-staves`.

One dated line per session, newest first. Every session reads this file
at start and appends its line at close. Keep entries to one or two
lines — history lives in git and `docs/history/`.

---

- 2026-07-30 — Docs slimmed for lightweight working. The milestone
  ceremony and the two-track process are retired: one track now, no plan
  gate, ask first only for a schema bump, a golden re-capture, or a rule
  change. CLAUDE.md cut 355 → 244 lines (rules keep their short form;
  the long form moved to the new `docs/RULES.md`). ROADMAP, PHASES and
  the briefs moved to `docs/history/` and are out of the read path. The
  session protocol is now WORKLOG only, everything else on demand.
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
