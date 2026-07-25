# M4 Effects planning brief — the pop you can actually use (2026-07-24)

Written by a planning session, 2026-07-24, against ROADMAP.md's M4
milestone (the scope authority; this brief is how it gets built). M4 is
**pulled forward ahead of M2** (M2 is in flight on its own branch); it
needs only M1, which is closed and tagged. Branch **`beta/m4-effects`**
off the same base M2 used (`main` @ 70a99a6); expect one small merge in
`ui/inspector.py` (both milestones edit the dock's sections — the
ROADMAP anticipated exactly this).

Goal, from the roadmap: effects become a first-class, tunable,
*global-by-default* system with a proper UI home — and pop becomes
shapeable: how strong (amplitude), how long (settle), whether it lasts
the note's own value, and when it peaks (peak offset).

**Boundaries (restated as law for this build):** rule 6 — timescale and
trigger shift are scalar/data INPUTS to the one evaluator; the moment
anyone writes `if effect.name == "pop"` in `element_state`/`Envelope`/
the applier, stop. Rule 5 — params are intent; note durations are
derived every load and never stored. Rule 1 — no Qt in `core/`. Rule 12
— durations come from the engraved timemap, never a music21
re-derivation and never inferred from the next onset. ARCHITECTURE §5 —
export inherits everything through the shared `AnimationInputs` seam
(`schedule` + `style` + the timing args); **touching
`render/export.py` is a flag-and-stop**. No monoliths — the Effects
panel is its own module under `ui/panels/`, the duration lookup its own
core seam.

## 0. Findings — the flag-and-stop investigations, resolved

Both items the ROADMAP marked flag-and-stop were investigated first
(2026-07-24, probes run against the real fixtures). Neither is a stop.

### F1. Note duration source — the timemap HAS durations; the adapter discards them

The engraved timemap exposes per-element durations today: every
`renderToTimemap` entry carries `off` and `restsOff` arrays symmetric
to the `on`/`restsOn` the adapter already consumes. The adapter
(`core/engraving/verovio/provider.py:250-255`) reads only the on-side
and throws the off-side away. Probed on testscore: **all 500 note-ons
have a matching off; all 114 rest-ons too**; grace notes carry their
fractional length (0.0586 beats); durations are exact timemap qstamp
deltas on the same performance axis as every onset (rule 12 — one
axis, zero new authorities).

The tie question resolves cleanly: **a tied notehead's `off` is its
OWN notated end, not the chain end** (probed: start on=13.5 off=14.0,
continuation on=14.0 off=15.0). That is precisely what
grow-with-playhead needs — each re-notated continuation notehead
(which fires at its own onset since the 2026-07-22 ruling) relaxes
over its own segment.

So: **no next-onset inference anywhere** (the trap the ROADMAP named —
wrong across rests, chords, voice splits — never arises), and no stop.
The work is: capture `off_by_id` next to `onset_by_id`, expose
`EngravedScore.note_durations: Mapping[ElementId, Beats]` (a new
mapping, NOT a field on `ElementIdentity` — the golden serializer pins
explicit fields, so goldens stay byte-identical), and resolve
element-level durations in a dedicated core seam (M4.2).

**Seconds path confirmed:** duration-in-seconds is computed inside
`AnimationApplier.set_timing` as `resolve_seconds([onset, onset+dur])`
deltas — the ONE swing-aware seam (`core/timing/swing.py:76`). The
window (`ui/main_window.py:186`) already calls
`playback.set_timing_config(...)` → `applier.set_timing` on EVERY
document change — the same document-changed pass a floor-opacity
commit rides — so durations re-time on bpm/swing change with zero new
wiring.

### F2. Transition window — measured; accept the conservative window, add a two-line guard

`Effect.duration` currently gives the applier one cached window
`[trigger, trigger + duration]` (`render/animate.py:_apply_window`:
one bisect at `t − d_max`, then re-evaluate every timed trigger up to
the cursor). Per-element timescaling makes the true window
`duration × timescale`. Measured cost at 60 fps / 120 bpm — elements
re-evaluated per frame, with note-value ON (per-element windows = the
note's own length; `d_max` = longest note ≈ 2.0–2.25 s on these
fixtures):

| fixture | status quo (0.25 s settle) | single `d_max` window, no guard | + per-trigger expiry guard |
|---|---|---|---|
| testscore (89 trig / 1 425 items) | mean 10 · max 74 | mean 78 · max 167 | mean 34 · max 98 |
| bigband1 (186 / 4 094) | mean 19 · max 80 | mean 143 · max 274 | mean 25 · max 127 |
| complex3 (526 / 16 967) | mean 26 · max 176 | mean 217 · max 541 | mean 98 · max 342 |

Verdict: the ROADMAP's recommendation is **accepted with one
amendment**. Even the unguarded worst case (541 `setOpacity`/
`setScale` calls per frame) would hold 60 fps — but `d_max` scales
with the longest note in SECONDS (a whole note at 60 bpm is 4 s; a
long-held pad note more), so the unguarded mean grows with repertoire.
The amendment is two lines: `_apply_window` already stores per-trigger
`self._durations`; extend the loop's existing `> 0.0` check to also
skip triggers whose window has expired
(`trigger_s[i] + durations[i] >= min(t, t_prev)` — the `min` keeps the
one final settle evaluation that pins the resting state). One bisect,
one loop, the applier keeps its shape; cost becomes proportional to
elements genuinely mid-transition (≈ polyphony), not to `d_max`.

One real structural consequence found here: **negative peak offset
makes the window two-sided** (F3). An effect shifted earlier than its
trigger must evaluate BEFORE the cursor crosses the trigger, so the
window pass gains a forward bound: triggers in
`(cursor, bisect(t + lead)]` where `lead = max(0, −min_shift)` also
re-evaluate. Same arithmetic, no new structure; `element_state` at
`t < trigger + shift` yields the envelope's `initial` (floor), so
early evaluation is naturally a no-op until the shifted step.

### F3. Peak offset — trigger shift confirmed, made uniform for both signs

The ROADMAP's recommendation (signed shift of the trigger, not signed
`t_rel` keyframes) is **confirmed**, with one deliberate deviation: the
ROADMAP's literal text implements positive offset as envelope data
(appear on the beat, scale ramps to peak afterward) and negative as a
trigger shift. That mixed model makes the knob mean two different
things on either side of zero — at +100 ms the note appears ON the
beat and swells late; at −100 ms everything moves early. This brief
makes it a **uniform signed trigger shift for both signs**: the whole
effect — opacity step and scale peak together — moves early or late as
one unit. Rationale: the knob's real job is perceptual sync trim for
video overlay (visual accents often need to lead the audio slightly);
a uniform shift is one implementation (a per-effect scalar the kernel
subtracts), works for every current and future effect, and never
changes meaning at zero. The envelope-ramp positive variant is a
different visual (a swell after the attack) — if that is ever wanted
it is a new preset, not this knob.

**Stated plainly, as the ROADMAP demands: at a negative peak offset
the note also BECOMES VISIBLE that early.** The floor→1.0 opacity step
rides the same shift, so at −100 ms every note appears 100 ms before
the beat. This goes in the panel tooltip verbatim ("Shifts the whole
pop, including when the note appears"). If Marcus ever wants
appearance-on-beat with a pre-swell on the floor ghost, that is signed
`t_rel` and a real model change — out of M4, flagged per the ROADMAP.

Mechanics: `Effect` grows `trigger_shift: float = 0.0` (data, like
`Envelope.initial`); the kernel evaluates
`(t − trigger − effect.trigger_shift) / timescale`. Shift is absolute
seconds — applied BEFORE the timescale division, so ±100 ms means
±100 ms regardless of note length. The applier's page/system cursor
bisects the UNSHIFTED trigger seconds, so **page turns and view-follow
do not move**; spanner reveal edges (edge-driven, not
trigger-driven) also stay put — at the knob's ±500 ms range the skew
between a shifted notehead and its unshifted slur is accepted and
recorded here. UI name is **"Peak offset"** (never plain "offset" —
the transport already owns that word).

### F4. Schema — v6 is taken; M4 bumps to v7

Contact with reality: the ROADMAP (and the prompt for this brief) say
"schema v6", but **v6 already shipped** — `hide_first_system` consumed
it on 2026-07-24 (`serialize.py:49-54`, which itself notes "the
ROADMAP's 'M4 → v6' plan shifts by one"). M4 is therefore a **v7**
bump: `default_effect` + `effect_params` in the `"style"` block.
Folding into v6 instead was considered and rejected: v0.2-beta.1 is a
TAGGED build that reads v6 — it would load an M4 file, silently drop
both new keys, and destroy them on the next save. That is the exact
failure the v2 bump exists to prevent; the bump keeps every older
build refusing loudly. Read side: v5/v6 files load with
`default_effect=None` (→ "appear") and `effect_params={}` — unchanged
look, no read gate. M5's "v7" in the ROADMAP shifts to v8 (noted for
the close-out).

### Minor findings

- **F5 — per-part effect submenu.** The ROADMAP drops the Score-menu
  per-part effect radio group once the panel exists. The panel covers
  the DOCUMENT default only, so after M4 a per-part effect deviation
  is still honored and round-tripped (part rules are untouched) but
  not authorable until M3's Selection panel. Accepted per the
  ROADMAP; recorded so the capability gap is deliberate. The color
  submenu stays.
- **F6 — rests are excluded from note-value scaling.** A rest's
  trigger is retrospective (fires when its silence resolves —
  schedule rule 4), so stretching its settle by its nominal length
  would animate past the ink's own span. The duration-resolution seam
  simply omits rests (and everything else without a
  same-onset trigger: displaced sigs, minted onset-less furniture);
  omitted elements get timescale 1.0. Policy lives in the seam
  (M4.2), never in the evaluator.
- **F7 — timescale definition.** `timescale_e = dur_seconds(e) /
  effect.duration` (guarded `dur > 0`, `effect.duration > 0`; absent
  → 1.0). Consequence worth liking: with note-value on, an element's
  transition window IS its note length; an eighth shorter than the
  authored settle settles FASTER (the ROADMAP's "an eighth pops and
  settles at once"); graces flick (0.03 s). No extra clamps.

## 1. Current state — the touch surface

- `core/animation/presets.py` — `_POP_SCALE = 1.25`, `_POP_SETTLE_S =
  0.25` module constants; `build_presets(floor)`; `effect_for` fails
  soft. Amplitude/settle become params of `build_presets` — the
  ROADMAP's "pure preset data" claim holds for these two.
- `core/animation/effect.py` — `Envelope`/`Effect`/`element_state`
  kernel (state.py). Grows `trigger_shift` + `settle_to_note_value`
  as Effect DATA and a `timescale` scalar arg on `element_state`.
- `core/animation/style.py` — `StyleRules.resolve`: element > part >
  None. Gains `default_effect`, `effect_params`, and the default in
  the resolution chain.
- `core/animation/schedule.py` — `TriggerSchedule` gains
  `duration_by_element` (default empty — synthetic tests untouched).
- `render/animate.py` (277 lines) — window machinery per F2/F3;
  timescales recomputed in BOTH `set_timing` (tempo/swing moved) and
  `_resolve_effects` (params/effects moved) via one private helper.
  Stays under ~400.
- `render/export.py` — **untouched** (the flag). All new data rides
  `AnimationInputs.schedule` and `style`, both already passed.
- `core/project/serialize.py` + `commands.py` — v7, two new commands.
- `ui/inspector.py` + new `ui/panels/effects_panel.py`;
  `ui/parts_menu.py` loses the effect radio group.
- `ui/score_loader.py` — passes durations into the schedule build.

## 2. Design — settled parts (per ROADMAP, confirmed against code)

- **Resolution order**: element override > part rule > **document
  default** > "appear". `StyleRules.default_effect: str | None = None`;
  `resolve()` substitutes it where both element and part are silent.
  Unknown stored name fails soft via `effect_for` (an old build
  opening a newer project degrades, never crashes).
- **Params storage**: `StyleRules.effect_params: Mapping[str,
  Mapping[str, Any]]` — sparse `{preset: {key: value}}`. Pop's keys:
  `"scale"` (default 1.25), `"settle"` (seconds, 0.25),
  `"peak_offset"` (seconds, 0.0), `"note_value"` (bool, False).
  Unknown presets/keys round-trip byte-untouched (stored raw, written
  back verbatim — the effect-name precedent). Consumption clamps
  (settle ≥ 0.01 s, scale ∈ [0.1, 10], peak_offset ∈ [−0.5, +0.5]);
  the command validates only type/finiteness so future presets reuse
  it unchanged.
- **Commands**: `SetDefaultEffect(name | None)`;
  `SetEffectParam(preset, key, value)` (value `None` deletes the key,
  empty param dicts drop — the `_merge_rule` sparse idiom). Spinboxes
  commit on `editingFinished` with the epsilon no-op guard — one
  command per user gesture, exactly the existing pattern (there is no
  per-tick drag stream to coalesce; the ROADMAP's "coalescing" is
  satisfied the way every spinbox already satisfies it).
- **Undo story, per knob**: every control is one command → one undo
  step; undo/redo/load arrive via the window's document-changed pass →
  `playback.set_style` re-resolves presets + windows + refreshes, and
  the panel resyncs with the blockSignals idiom
  (`sync_from_document`). A settle/note-value undo retimes windows
  identically because windows are re-derived, never cached across
  style changes. Nothing new is invented: the floor-opacity commit
  path, verbatim.
- **Export**: params ride `style`, durations ride
  `inputs.schedule` — `FrameRenderer` constructs the same applier
  from the same arguments. Zero exporter edits, pinned by test.
- **Panel** (`ui/panels/effects_panel.py`): the *Appearance & Effects*
  section's body becomes this widget — Effect dropdown (enumerates the
  registry), Amplitude, Settle (s), "Animate entire note value"
  checkbox, Peak offset (ms in the UI, seconds in the doc), plus the
  existing Floor opacity + Sweep rows which move in with it.
  QFormLayout labeled rows, M1 conventions.

## 3. Tasks

Branch `beta/m4-effects`. Commit per task; app launches and `pytest`
stays green after every task.

- **M4.1 Adapter: capture timemap offs.** `provider.py` reads
  `off`/`restsOff` into `off_by_id` beside `onset_by_id`
  (`records._LoadState` gains the field); the identity chain that
  stamps onsets also computes per-element `duration = off − on`, and
  `EngravedScore` grows `note_durations: Mapping[ElementId, Beats]`
  (notes AND rests; absent id → no entry). Goldens: byte-identical
  (serializer is explicit-field — verified before writing this brief);
  do NOT regenerate. Files: `verovio/provider.py`, `verovio/records.py`,
  `verovio/identity.py`. **Verify:** new
  `tests/test_adapter_durations.py` — on testscore: a plain quarter’s
  duration is 1.0; a grace is fractional (< 0.1); each tied notehead
  carries its OWN segment length; on pickup_min: pickup-bar durations
  are the engraved (short) ones, not nominal; goldens unchanged
  (`pytest tests/test_golden_layouts.py`).
- **M4.2 Duration-resolution seam:** new `core/animation/durations.py`
  — `resolve_durations(layout, mapping, note_durations, measures) →
  Mapping[ElementId, Beats]`. Noteheads: own entry. Attachments
  (stems/flags/accidentals/articulations/dots/beams): the max duration
  of their (part, staff, voice, quantized-onset) group — the
  schedule's rule-3 key, via the shared `quantize_beats`. Synthesized
  SLASH: the measure span ÷ slash count; BAR_REPEAT: its measure span
  (the trailing event-less bar rides `MeasureInfo.quarter_length`'s
  notated floor — rule 12's one exception, already handled upstream).
  Rests, sig kinds, onset-less: omitted (F6). `TriggerSchedule` gains
  `duration_by_element: Mapping[ElementId, Beats]` with an empty
  default; `build_trigger_schedule` accepts and stores it. Files:
  `core/animation/durations.py` (new), `schedule.py`,
  `core/animation/__init__.py`. **Verify:** headless
  tests with synthetic layouts (chord group inherits its longest
  member; attachment inherits; rest omitted; slash/bar-repeat spans);
  existing schedule tests pass unmodified (default keeps arity).
- **M4.3 Effect model + presets:** `Effect` gains `trigger_shift:
  float = 0.0` and `settle_to_note_value: bool = False` (frozen
  fields, data only); `element_state(trigger_seconds, effect,
  t_seconds, timescale=1.0)` evaluates
  `(t − trigger − shift) / timescale`. `build_presets(floor,
  params=None)`: pop built from merged+clamped params (F7 ranges);
  `PRESETS` stays the param-less default registry. Files: `effect.py`,
  `state.py`, `presets.py`. **Verify:** extended
  `tests/test_presets.py` / `test_animation.py` — amplitude/settle
  land in the envelope; peak_offset lands in `trigger_shift`; unknown
  param keys ignored; `timescale=2` halves the evaluated `t_rel`;
  `Effect.duration` unchanged by shift.
- **M4.4 StyleRules + resolution:** `default_effect` +
  `effect_params` fields; `resolve()` chain element > part > default.
  Files: `style.py`. **Verify:** headless — part rule beats default;
  default beats "appear"; None default preserves today's behavior;
  `takes_part_color` untouched (TINTED_KINDS scope unchanged — clefs
  still black while popping).
- **M4.5 Commands + schema v7:** `SetDefaultEffect`, `SetEffectParam`
  (sparse-delete semantics); `PROJECT_VERSION = 7`, readable 1–7;
  serialize `default_effect` (omit when None) + `effect_params`
  (raw round-trip). Files: `commands.py`, `serialize.py`,
  `core/project/__init__.py`. **Verify:** `tests/
  test_project_commands.py` + serialize tests — v5 and v6 files load
  with unchanged look; save→load round-trips an UNKNOWN preset's
  params byte-for-byte; undo restores the prior param; a param set to
  None disappears from the saved JSON.
- **M4.6 Applier: windows + timescales.** `_resolve_effects` builds
  presets from `(floor, effect_params)`; per-item timescales and
  per-trigger effective windows
  (`shift + effect.duration × timescale`, max over items) recomputed
  in one private `_recompute_windows()` called from both `set_timing`
  (durations→seconds through `resolve_seconds` at
  `[beats, beats + dur]`) and `_resolve_effects`; `_apply_window`
  gains the F2 expiry guard and the F3 forward `lead` bound;
  `_apply_trigger` passes per-item timescale into `element_state`.
  Page/system cursor stays on unshifted trigger seconds. Files:
  `render/animate.py` (audit line count — split a `windows.py` helper
  out if it nears ~400). **Verify:** extended
  `tests/test_animate_apply.py` — with note-value on, a 4-beat note is
  mid-scale at t = +1.0 s where an eighth has settled; scrubbing
  backward through a stretched settle equals a fresh `refresh`
  (statelessness); negative shift: element visible before its trigger,
  page cursor unmoved; bpm change re-times the stretch (same
  scene state as a fresh build at the new tempo).
- **M4.7 Loader wiring + export pin:** `score_loader.py` calls
  `resolve_durations` and passes the map into
  `build_trigger_schedule`; nothing else moves (`AnimationInputs`
  arity unchanged — schedule carries the data). **Verify:**
  `git diff --stat render/export.py` is EMPTY (the §5 flag, made a
  check); extended `tests/test_export.py` — a frame exported with
  amplitude 2.0 / note-value on / peak offset −100 ms matches the live
  applier's `refresh` state at the same t (the existing sync-test
  shape).
- **M4.8 Effects panel:** new `ui/panels/__init__.py` +
  `ui/panels/effects_panel.py` (~150 lines): Effect dropdown +
  Amplitude + Settle + note-value checkbox + Peak offset (ms), plus
  Floor opacity and Sweep moved in from `inspector.py`;
  `sync_from_document` with the blockSignals idiom; inspector embeds
  the panel and delegates its resync; `parts_menu.py` drops the
  per-part effect radio group (F5 — color submenu stays). Files:
  `ui/panels/*` (new), `ui/inspector.py`, `ui/parts_menu.py`,
  `ui/main_window.py` (sync dispatch only). **Verify:** offscreen
  tests (`test_inspector.py` pattern): each control commits exactly
  one command with the right payload; resync never re-executes
  (undo-stack depth unchanged); tooltip on Peak offset states the
  early-visibility consequence; `wc -l` — every touched `ui/` module
  < ~400.
- **M4.9 Exit run-through + close-out.** §4 checklist on real
  fixtures; docs close-out (§6); merge to `main`; tag the next free
  `v0.2-beta.N` (M2 may or may not have merged first — take the next
  number at merge time). **Verify:** full `pytest` (goldens, live
  oracle, no-Qt-in-core) green on the merge commit.

## 4. Exit criteria (ROADMAP's, restated as the checklist)

- [ ] Fresh document: choose "pop" in the panel — every part pops with
  no per-part setup.
- [ ] Raise amplitude, halve settle — visible live AND in an exported
  clip.
- [ ] Toggle "animate entire note value" on a mixed-duration score
  (video_test or complex3): a whole note visibly relaxes over its full
  length while an eighth settles at once; both stay correct after a
  tempo change.
- [ ] Peak offset ±100 ms: the peak moves relative to the beat (and at
  −100 ms the early appearance is the documented, tooltipped
  behavior).
- [ ] Save/reload round-trips v7; a v5 AND a v6 file load with
  unchanged look; unknown effect_params survive a save/load cycle.
- [ ] Undo steps through each knob individually (default effect,
  amplitude, settle, note-value, peak offset — five knobs, five
  steps).
- [ ] Exported frames match the stage at every setting (M4.7 pin +
  eyeball).
- [ ] Suite green: goldens byte-identical, live oracle, no-Qt-in-core;
  no `ui/` or touched module ≥ ~400 lines.
- [ ] Merged to `main`, tagged.

## 5. Contact-with-reality flags (recap, for Marcus's review)

1. **Schema v7, not v6** (F4) — ROADMAP written before
   `hide_first_system` took v6. M5 shifts to v8.
2. **Peak offset is a uniform trigger shift both signs** (F3) —
   deviates from the ROADMAP's positive-as-envelope reading;
   consequence (early visibility at negative offset) stated in the UI.
3. **The conservative window gets a per-trigger expiry guard** (F2) —
   measured 2× mean saving, two lines, no shape change.
4. **Per-part effect authoring goes save-file-only until M3** (F5).
5. **Rests don't stretch** (F6) — policy in the duration seam.

## 6. Suggested .md changes (during the build, per the close-out pattern)

- CLAUDE.md rule 6 amendment (draft, apply with the build ruling):
  *"Amendment (M4, 2026-XX-XX): an effect may carry scalar data the
  applier consumes generically — a per-element timescale (note-value
  settle, duration from the engraved timemap per rule 12) and a signed
  trigger shift (peak offset). Both are inputs to the one evaluation
  kernel; neither is a branch on an effect's name."*
- ROADMAP: M4 marked closed; findings F2–F4 rulings recorded; M5's
  schema note updated to v8.
- ARCHITECTURE §3: `element_state` signature + Effect fields;
  §5: durations ride TriggerSchedule through AnimationInputs.
- CLAUDE.md package layout: `ui/panels/`, `core/animation/durations.py`.
- BACKLOG: per-part effect authoring gap (until M3); pre-swell-on-
  floor-ghost variant if ever requested.

## 7. Prompts to paste into Claude Code

One session per prompt, /clear between.

### Prompt 1 — build

    Read CLAUDE.md, docs/ARCHITECTURE.md, docs/ROADMAP.md (M4), and
    docs/briefs/M4_EFFECTS_BRIEF.md. M4 Effects is planned; build it
    task by task (M4.1 through M4.8) on branch beta/m4-effects off
    main: commit per task, pytest green and the app launching after
    every task. Hard rules from the brief: no effect-name branches in
    the evaluator or applier; render/export.py untouched (M4.7 checks
    it); durations only from EngravedScore.note_durations; goldens
    byte-identical. Flag-and-stop where reality disagrees with the
    brief.

### Prompt 2 — exit + close-out

    M4 Effects is built on beta/m4-effects. Run the M4 exit: full
    pytest (goldens, live oracle, no-Qt-in-core); the brief §4
    checklist interactively (fresh doc → pop globally; amplitude/
    settle live + export; note-value on video_test with a tempo
    change; peak offset ±100 ms; v5/v6/v7 load matrix; five-knob undo
    walk); the module-size audit. Close out the docs per §6, then stop
    for my review before merging and tagging.
