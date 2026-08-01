# ScoreAnim — Worklog

**NOW:** `beta/f-system-pulse` is where the work is. It is
`beta/system-groups` with `beta/f-follow-volume` merged into it — the
system group items on one side, the recording's live loudness on the
other — and both halves are still waiting on Marcus's eyes in the
running app. Under `beta/f-follow-volume` sit `beta/f-swell-effect`,
`beta/f-pop-per-note`, `beta/f-volume-duration` and
`beta/f-volume-response`; between them the two volume branches moved the
schema to **v11**, so a project saved from any of them will not open on
`main`.

`main` carries `beta/live-fields` (`ffd0ac8`, no tag), confirmed
in the app: every number field previews as you type. It brought
`beta/shell-layout` with it — the openers on the toolbar, the grid
controls under the lanes, tap tempo gone. Schema is still v10, so a
project saved from `main` will not open on `v0.2-beta.6`.
`beta/f-trackpad-gestures` is merged in too, so the stage navigation is
back: pinch to zoom, two-finger scroll to move.
`beta/f-drop-effect` is merged as well (`3c60723`, no tag), and it
brought `beta/f-fade-effect` with it: the fade, drop and slide effects,
and effects that run together ("drop+fade"). Merged on Marcus's word
without the usual app run first — worth a look in the running app.
`fix/bracket-hidden-staves` is the only other branch still unmerged.

Open question from grid-align, still open: whether Tempo mode still
earns its place now that the Tempo field aims at the selected line.

One dated line per session, newest first. Every session reads this file
at start and appends its line at close. Keep entries to one or two
lines — history lives in git and `docs/history/`.

---

- 2026-08-01 — **Every system is one object now**
  (`beta/system-groups`, UNMERGED, off `main`): a structural change with
  no visible half. Each element whose system is known hangs off a
  `SystemGroupItem` for its (page, system) (new `render/system_group.py`,
  90 lines); stage texts and page furniture stay top-level. The group
  paints nothing, is hit-transparent by the same empty `shape()` the
  per-element parents already use, and carries NO transform until
  something scales it — so every child keeps the scene coordinates it
  had. The seam for the next step, with no caller: `set_system_scale`
  turns the system around the centre of its own ink, frozen once at
  build (a nudge must not drag that point), 1.0 exactly identity, and it
  re-derives descendant reveal clips, because a scale springs the M3.2
  cached-inverse trap from the other side. The one real risk was paint
  order — synthesis appends slashes and stray ties after the systems
  they belong to, so grouping moves that tail earlier relative to other
  systems on the page. Measured: **21 pages over testscore, video_test
  and complex1 render bit-identically** before and after
  (`tools/render_page_png.py`, sha256). Goldens never moved (they pin
  the core Layout, not the Qt scene), full suite green. Checked in the
  real window offscreen: click-select still lands on the notehead and
  tints it, a nudge still previews and commits 20/−10. Unproven under a
  human's eye. **`render/items.py` is at 430 lines** — it was over the
  ceiling before this and it is still the next split.
- 2026-08-01 — **A swell follows the recording**
  (`beta/f-follow-volume`, UNMERGED, off `beta/f-swell-effect`): a
  "Follow volume" box in the Swell block, off by default. With it on a
  note's size tracks how loud the recording is WHILE IT SOUNDS — a
  crescendo grows it, a diminuendo shrinks it — instead of playing one
  frozen average. The shape changes to suit: a plateau instead of a
  hump, 10 % up / 75 % hold / 15 % back (Marcus's call), where the hold
  is what the live volume plays on and the tail is the snap-back that
  lands the note at exactly its engraved size as the next one arrives.
  Follow forces the note-value stretch on — a fixed 0.8 s window cannot
  track a whole note — and the panel shows that box checked and grayed
  rather than lying about it (new `Check.forced_by`, five lines in the
  shared knob module); Peak grays too, since the top is a stretch now,
  not a point. Three layers, each one small: a third reading in
  `intensity.py` (`intensity_at`, off the ~90 ms level of the pyramid
  the cache already built, interpolated between bins — no new sums), one
  more `Effect` flag beside `settle_to_note_value`, and one choice in
  the applier between the live gain and the average. The flag comes out
  of `derive_windows`, which already walks every effect of every item,
  so the lookup is once per trigger per frame and the peak reference is
  cached on the seams that move it. **`render/animate.py` went 409 →
  367 first**, as its own commit: reveal was never trigger-driven, so
  the index, the warning, the curves and the edge cache moved to
  `render/reveal_driver.py`; it lands back at 398. No schema change, no
  golden movement. Measured on testscore.wav
  (`spikes/follow_volume.py`): across a dotted half the reading runs
  0.40–0.71 and the biggest jump between two frames is 0.13, so it
  breathes without flickering. Checked end to end in the real window
  with the recording loaded — the note holds between 1.36× and 1.46×
  and lands on exactly 1.0. Unproven under a human's eye.
- 2026-08-01 — **A note swells over its own length**
  (`beta/f-swell-effect`, UNMERGED, off `beta/f-pop-per-note`): a fifth
  effect, and the first one about a note's LENGTH instead of its
  arrival. The note is already on the page at its engraved size, grows
  to 1.4× and eases back down to exactly where it started, timed to its
  notated value — a whole note swells across its bar, an eighth is a
  quick breath. Pure preset data (rule 6): one registry entry plus four
  knobs, and nothing in the evaluator, the applier, the compose table or
  the schema. Up on EASE_IN and down on EASE_OUT — gentle away from
  rest, softly back to it — which puts a brief point at the top; both
  ends land exactly on 1.0, so no note is ever left oversized.
  `settle_to_note_value` defaults ON here, the only preset it does, and
  the existing per-element timescale stretches the whole authored shape
  at once, so the top keeps its place inside the note however long the
  note is (Peak, shown as a per cent of the way through). The two
  interactions asked about needed no code and are now pinned: pop+swell
  multiplies into a dip-then-swell, and the volume response modulates a
  swell like any other scale departure. Checked end to end through the
  applier on testscore — a dotted half tops out at +0.75 s where an
  eighth was home at +0.25 s. No schema change, no golden movement;
  unproven under a human's eye in the running app.
- 2026-08-01 — **Every notehead pops in its own place**
  (`beta/f-pop-per-note`, UNMERGED, off `beta/f-volume-duration`): a
  chord's heads used to share one pivot — the centre of the whole stack
  — so the outer ones slid sideways as they grew. Each head now turns
  around its OWN centre, and the ink hanging off it follows the head it
  belongs to: a stem stands on the head at its foot, a flag and tremolo
  strokes ride the stem, an accidental or dot takes the nearest head.
  133 of testscore's 252 note groups are chords, so this is most of the
  fixture. Two Marcus calls with it: **beams never scale** (they appear
  with their note at engraved size — a beam belongs to several notes, so
  any pivot is a compromise), and a **stem stops at its beam**. The stem
  ceiling is a new pure module (`core/animation/stem_caps.py`), a
  geometric stem↔beam join like the ledger dashes', carried on the item
  as `scale_cap` and clamped in one `min()` in the applier. Measured:
  the beam's far edge sits ~3% of a stem's length past its tip, so a
  beamed stem thickens where a flagged one pops with its head; 101 of
  252 stems are capped and none overshoots. The ceiling took two goes —
  a first cut read the beam's BOX and stems grew straight through
  tilted beams (28 of testscore's 38 beams are tilted), so it now reads
  the beam's drawn outline at the stem's own x, across the stem's whole
  width, through a new pure `svg_geom.path_outline`. The same pass found
  a second one on video_test: a beam one staff up was close enough to
  claim an unbeamed stem, so a beam is now this stem's only where the
  tip is drawn INSIDE its ink. Checked over 8 fixtures, flat and with
  staves hidden: 3244 capped stems, zero overshoot, zero beamed stem
  without a ceiling. Applies to EVERY scale
  effect, not just pop, so under drop the heads enter at 3× while the
  beam sits still — deliberate, and it reverses the beam half of the
  2026-07-31 ruling. Rendered rest vs peak and looked at it
  (`spikes/pop_pivot.py`); unproven under a human's eye in the running
  app. No schema change, no golden movement. **`render/items.py` is at
  432 lines** — it was already over the ceiling before this, and it is
  the next split.
- 2026-08-01 — **The gain follows each note's own length**
  (`beta/f-volume-duration`, UNMERGED, off `beta/f-volume-response`): the
  volume response reads a note's whole notated duration instead of the
  moment it starts, and the gain is per ELEMENT, not per trigger — two
  notes on the same beat with different lengths now pop by different
  amounts. Averaging is on ENERGY (mean of rms squared, then the square
  root), one running total per call so each window costs a subtraction.
  Ink with no notated length — dynamics, texts, rests — falls back to
  the old attack reading through a zero-length window, so nothing loses
  its gain. No schema change, no new settings, `peak_reference`
  untouched. Split first as its own commit: the window arithmetic moved
  to a pure `core/animation/windows.py` (`derive_windows` for the settle
  stretches, `audio_windows` for these), which is what kept animate.py at
  409 rather than 450 — still AT the ceiling, and the reveal-index wiring
  in `__init__` is the next seam if it has to come down. `trigger_gains`
  is gone; `window_gains` is the one None contract. Measured on
  testscore.wav (`spikes/volume_response.py`, now prints both readings):
  the average reads **0.80× the attack** over the 1159 elements with a
  length, the spread widens at the quiet end (0.040–1.00 → 0.011–1.00),
  and the busiest frame's largest pop goes 1.24 → 1.15 where it used to
  go 1.24 → 1.34. So it is gentler AND leans quiet — recalibration is
  Marcus's call after he looks at it.
- 2026-08-01 — **Animation strength follows the recording**
  (`beta/f-volume-response`, UNMERGED): a loud beat pops harder, a quiet
  one more subtly. One derived scalar per trigger — the loudest rms bin
  in a window that leans forward onto the attack (−25/+75 ms), over the
  95th percentile of the bins that carry any sound. A percentile, not
  the maximum, or one stray transient flattens every real note; only
  sounding bins, or a silent tail makes quiet music read as loud
  (`core/animation/intensity.py`). The gain scales the FINISHED state
  about the compose table's neutral — SCALE and the two offsets only.
  Opacity is never modulated and never will be: a quiet note still has
  to become fully visible. Gain 1.0 returns the state by an early
  return, not by arithmetic, so amount 0 is bit-identical to before.
  Three settings (Amount, Quiet, Loud) in a sparse `style.volume`,
  **schema v11** — no read gate, a missing key is the response off.
  Live and export share one seam (`AnimationApplier.set_audio`), pinned
  by a test that walks both. The live path reads the peaks on
  `finished`, not `progress`: a half-decoded file's reference is wrong
  and moves every tick. Panel first: `PresetKnobs` became `KnobGroup`
  with a pluggable store, so the Volume response block rides the same
  live fields instead of a second copy. Measured on testscore.wav:
  intensity spreads 0.04–1.00 over 89 triggers, and the busiest frame's
  largest pop goes 1.23 → 1.34 (`spikes/volume_response.py`). Checked
  end to end in the real window offscreen; unproven under a human's eye
  so far. **`render/animate.py` is at 415 lines** — over the ceiling,
  and due a split before anything else lands in it.
- 2026-08-01 — **Effects combine** (same branch): a note can drop AND
  fade, picked with a second "Combine with" dropdown. The stored intent
  stays ONE name — the parts joined by "+" — so no schema bump, and an
  old build opening "drop+shimmer" still drops. Envelopes are never
  merged (two eased curves cannot be merged exactly at their
  keyframes): each part keeps its own tracks, shift and timescale, runs
  through the same kernel, and the RESULTS combine property by property
  in a new pure table (`core/animation/compose.py`). Opacity takes the
  MIN, not a product — every opacity envelope starts at the document
  floor, so multiplying would put a combined ghost below the floor
  Marcus set; scale multiplies, offsets add, all commutative. The
  applier now holds a tuple of effects per element and a timescale for
  each. The property appliers moved to `render/properties.py` first, as
  its own commit (animate.py was at 370). Rendered drop+fade and
  slide+fade to PNG and looked at them; unproven in the running app so
  far.
- 2026-07-31 — **A slide effect** (same branch): notes travel in to their
  place from a direction you pick — Direction in degrees (0 from above,
  clockwise), Distance, Duration and Bounce. Unlike drop it needed two
  NEW animatable properties, `OFFSET_X`/`OFFSET_Y` in scene units, so it
  is three layers, not one: the properties, the applier, the preset. The
  trap was the position: the document's nudge already owned it, so
  `ElementItem` now stores the nudge and the animated offset apart and
  derives `setPos(doc + animated)` — a nudged note slides to its nudged
  place and neither writer clobbers the other (ARCHITECTURE §M3.2). The
  angle becomes two track values inside `build_presets`, once per
  document change, so the evaluator never hears the word "direction".
  Default distance 120 page units — just clear of the note's own staff
  and inside the gap to the next one (rendered and looked at; at 200 the
  note arrives sitting on the staff above). Known compromise, and it
  shows: a beam slides on its first note's trigger, so a later note in
  the group comes in with its stem while its beam is already resting —
  the stem hangs unattached for a moment. Worse here than under drop,
  because a scale keeps the ink roughly where it belongs.
- 2026-07-31 — **A scale moves the whole note** (same branch): a drop or
  a pop used to grow the head and leave the stem behind. Head, stem,
  flag, beam, accidental, dots and articulations now turn around one
  point — the centre of the note's own heads — so the note arrives as
  one object. Ledger lines are the exception: ruled at staff size, they
  keep it, and only fade. The grouping is the key `durations.py` already
  uses (part, staff, voice, quantized onset), so nothing new is stored
  and the adapter is untouched; a beam's onset is its first note's,
  which is what makes the beam fall in with the note it starts on while
  the rest of its group drop onto it. Policy in a new pure module
  (`core/animation/scale_groups.py`), render only applies it: no pivot,
  no scale.
- 2026-07-31 — **A drop effect** (`beta/f-drop-effect`, UNMERGED): notes
  land on the page like a stamp — each one enters at three times its
  size and part-way solid, then shrinks and goes fully solid over
  0.35 s, with a small bounce as it lands. No new property and no
  applier change: it is the existing scale and opacity, so the effect is
  preset data plus one curve, `EASE_OUT_BOUNCE` (the standard piecewise
  bounce, which ends exactly on its target — that is what leaves every
  played note at its engraved size). Knobs: start size, duration,
  bounce. The panel was split first, as its own commit: a preset's knobs
  are now a table entry built by `ui/panels/effect_knobs.py`, and
  `effects_panel.py` went 379 → 232 lines. Stems and beams still appear
  without the stamp — the same compromise pop makes, since scale only
  reaches anchored ink.
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
