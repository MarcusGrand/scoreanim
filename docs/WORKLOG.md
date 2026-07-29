# ScoreAnim — Worklog

**NOW:** `beta/f-delete-elements` built and green, awaiting Marcus's
check in the app + merge to main. No tag.

One dated line per session, newest first. Every session reads this file
at start and appends its line at close. Keep entries to one or two
lines — history lives in git, ROADMAP, and the briefs.

---

- 2026-07-29 — `beta/f-delete-elements`: delete = hide, for engraving
  cleanup only. Del/Backspace on the stage + Edit menu, texts/slurs/
  hairpins/dynamics only, restorable from the layout zone's new
  "Deleted" readout. Rides `LayoutOverride.hidden`; no schema bump, no
  re-engrave. Break commands split out of `layout.py` first. UNMERGED.
- 2026-07-29 — Docs: two-track process encoded (ROADMAP §"Process — two
  tracks"), PATTERNS.md and this file created, CLAUDE.md slimmed
  (rules untouched).
- 2026-07-29 — `fix/bracket-hidden-staves`: a bracket over hidden staves
  no longer kills the re-engrave; re-engrave failures are now visible in
  the UI instead of silent no-ops. Opened BACKLOG 18 (condense vs staff
  groups cross-validation). UNMERGED.
- 2026-07-28 — **M6 Pages CLOSED**: page-break authoring (`plan`
  composition with never-clip, combined `_apply_breaks` pass, schema v9)
  + the left layout zone. Merged `bf3a824`, tagged `v0.2-beta.5`.
  BACKLOG 16, 17 closed.
- 2026-07-28 — **M5 Breaks CLOSED**: system-break authoring, Move to
  Previous System (fat `SetSystemBreak`), schema v8. Merged `d912040`,
  tagged `v0.2-beta.4`.
- 2026-07-27 — **M3 Direct edit CLOSED** (`v0.2-beta.3`): in-place text
  edit, drag-to-nudge, per-element style. Part-label rename unbuilt
  (BACKLOG 14). M2 re-closed after the M2.8 tint rework.
- 2026-07-25 — **M4 Effects** and **M2 Selection CLOSED**, merged
  together (`v0.2-beta.2`).
- 2026-07-24 — **M1 Shell CLOSED** (`v0.2-beta.1`). Alpha frozen at
  `v0.1-alpha`.
