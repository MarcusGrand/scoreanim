# ScoreAnim — Beta roadmap

The numbered-phase era is over. Phases 0–12, Phase R, and the
live-timing epic are the **alpha**: the app loads real Dorico exports
(solo through 36-part orchestral), animates them correctly against a
recording, and exports deterministically. `docs/PHASES.md` is frozen as
the alpha build history — read it for how anything was built; never add
to it.

Beta work is organized as **named milestones**, in order, in this file.
The discipline is unchanged from the phase era: one milestone at a
time, every task ends with a concrete verification, exit criteria
close a milestone, flag architecture problems instead of silently
deviating. All CLAUDE.md rules stay in force; where a milestone needs a
rule amendment, the amendment is drafted here and applied to CLAUDE.md
in the session that builds it (with the ruling date), the established
pattern.

## Versioning & conventions

- Tag the current state `v0.1-alpha` before starting M1 (one tag, on
  `main` after the live-timing epic merges).
- Each milestone closes with a tag: `v0.2-beta.1` (M1), `v0.2-beta.2`
  (M2), … The running app version string can read the latest tag.
- **Brief per milestone**: before building a milestone, a planning
  session expands it into `docs/briefs/<MILESTONE>_BRIEF.md` (the
  PHASE11_BRIEF/PHASE12_BRIEF pattern) with the full task breakdown.
  This file stays the scope authority — what a milestone IS; the brief
  is how it gets built.
- The golden suite (`tests/goldens/`), the live oracle, and the full
  headless suite must be green at every milestone close. UI milestones
  add headless tests for every piece of pure logic they introduce
  (selection model, hit-priority policy, break-override injection).
- **No monoliths (CLAUDE.md working-style rule, Marcus 2026-07-24).**
  Every milestone leaves modules small and single-responsibility; a
  file nearing ~400 lines is split along a real seam before the
  milestone closes. New UI is composed of focused widgets/modules from
  the start, not grown into one window class — M1 sets the pattern by
  decomposing `main_window.py`.

## Development setup — running alpha alongside beta

The frozen alpha stays runnable in its own folder via a git **worktree**,
so beta development never disturbs a working build. One repository, two
checked-out folders sharing the same history.

One-time setup (native terminal, from `~/Documents/scoreanim`):

```
git worktree add ../scoreanim-alpha v0.1-alpha   # frozen alpha, sibling folder
cd ../scoreanim-alpha
python3.11 -m venv .venv && source .venv/bin/activate   # your Python 3.11+
pip install -e .
python -m scoreanim        # the frozen alpha — always runnable
```

Day to day:

- `~/Documents/scoreanim` (branch `main`, feature branches `beta/mN-*`)
  — beta development.
- `~/Documents/scoreanim-alpha` (detached at `v0.1-alpha`) — the frozen
  alpha; run it, never commit to it.
- Each folder has its **own `.venv`**, so a beta dependency change can't
  affect the alpha.
- Beta bumps the project schema (M4 → v7, M5 → v8 — the plan said
  v6/v7, but hide_empty-staves-on-first-system took v6 on 2026-07-24
  before M4 landed; brief F4). The alpha build
  **refuses to open a newer project file by design** (strict-by-version
  gate), so keep separate test projects for beta work.

Each milestone merges to `main` and tags `v0.2-beta.N`. Advancing the
alpha to a newer frozen baseline later is a retag + `git worktree`
move, but usually the alpha just stays put.

## Milestone overview

| # | Name | One-liner |
|---|------|-----------|
| M1 | **Shell** | Professional chrome: inspector dock + lower zone, labeled parameter fields, menu reorganization. No new features. |
| M2 | **Selection** | Click-to-select on the live stage: hit-testing, selection state, highlight, identity readout. |
| M3 | **Direct edit** | Double-click text editing in place; drag-to-nudge (consumes dx/dy); per-element style overrides from selection. |
| M4 | **Effects** | Effects panel: global default effect ("pop for everything"), tunable pop amplitude / settle / peak offset / note-value relax, floor + reveal controls rehomed. **Pulled forward — runs alongside M2.** |
| M5 | **Breaks** | System-break authoring: select a barline, toggle a system break; prep-seam re-engrave. |

Dependency shape: M1 first (every later control lands in its chrome).
M2 before M3 and M5 (both act on a selection). M4 needs only M1 and can
be pulled earlier if a break is wanted between selection work.

---

## M1 — Shell (UI reorganization)

**Goal.** The window grows professional chrome, taking the tried-and-
tested layout of Dorico/Cubase/Final Cut: the stage stays central; a
**right-hand inspector dock** holds collapsible, labeled panels; a
**lower zone** formalizes the timeline area (transport strip + the
waveform and tempo lanes). Menus reorganize around it. **No new
capabilities** — every existing action, command, and shortcut keeps
working; this milestone only re-homes them. That constraint is what
makes it safe to do first.

**Design.**

- **Inspector** (QDockWidget, right, closable/floatable, View-menu
  toggle) with collapsible sections:
  - *Playback & Sync* — Tempo (bpm), Offset, Swing, plus the
    Follow/Systems toggles. Every field is a **QFormLayout row: a
    plain label ("Swing") outside a clean editable box** — this
    retires the prefix-in-the-spinbox look (`setPrefix("swing ")`)
    everywhere. Same commit-on-editingFinished command wiring as
    today; only the widgets move.
  - *Appearance & Effects* — Floor opacity, Sweep (reveal mode), and
    the M4 effect controls when they land. Part colors stay in the
    Parts menu for now (M3 moves per-element styling here).
  - *Selection* — empty placeholder ("Nothing selected") until M2
    fills it.
- **Lower zone**: transport strip (play, time, slider, tap controls)
  above the waveform + tempo lane. Both lanes stay visible and
  stacked — they share the time axis on purpose (tapping while
  watching the waveform); do not tab them apart. The zone is
  collapsible as a whole.
- **Menus**: File (open/save/export) · Edit (undo/redo, Texts…) ·
  View (fit, prev/next, inspector/lower-zone toggles) · Score
  (Score Setup…, Staff Groups…, Part Names…, Hide Empty Staves —
  the current Parts menu, renamed, keeping the per-part color/effect
  submenus until M3/M4 re-home them) · Playback (play, follow,
  audio/tempo import).
- QSettings persists window/dock geometry (UI state, not document
  state — rule 5 untouched).

**Boundaries.** Commands, AppState, core/, render/ are untouched.
This is `ui/main_window.py` decomposition: the monolith splits into
`ui/inspector.py`, `ui/transport.py` (strip + lower zone), and a
thinner window. Widgets observing the document keep the exact
block-signals/diff idiom of `_on_document_changed`.

**Exit criteria.** Every alpha feature reachable and functioning in
the new chrome (interactive run-through: load complex2, tint a part,
tap, change swing/bpm/floor/offset from the inspector, undo through
all of it, export). Window layout survives restart. Full suite green.

**CLOSED 2026-07-24** (built M1.0–M1.9 on `beta/m1-shell` per
`docs/briefs/M1_SHELL_BRIEF.md`; tagged `v0.2-beta.1` at the merge).
Chrome rulings recorded during the build (Marcus, 2026-07-24): the
lower zone is a **bottom QDockWidget**, not a splitter pane (matches
the inspector; `toggleViewAction()` lands in the View menu; one
`saveState` pair persists both docks); the **top toolbar stays,
slimmed** to ◀ page-label ▶ · Fit; and **time fields (Tempo, Offset,
Swing) live on the transport strip** with the transport they
configure, so the inspector's *Playback & Sync* holds only the
Follow/Systems toggles. The window decomposed further than the design
sketch above (nine `ui/` modules — see ARCHITECTURE §7); none is over
~400 lines. Exit finding, fixed in M1.9: the Phase 12.4
Score-Setup-on-open trigger had gone dead when Phase 12.5's
scale-to-fit started rescuing formerly-overflowing loads; it now fires
on `scaled-to-fit` too.

---

## M2 — Selection (click-to-select on the live stage)

**Goal.** Click any element on the stage — during playback or paused —
to select it: it highlights, and the inspector's Selection panel shows
its musical identity (kind, part, measure, voice, onset). This is the
foundation BACKLOG 9 and the layout-override slots have been waiting
for since Phase 4/5; the render layer was built for it (ElementItem
carries identity + bbox; GroupItem deliberately does not grab child
events; scene coords == page coords).

**Design.**

- **Hit-testing**: view click → `scene.items(pos)` → walk to the
  parent ElementItem. A **pure hit-priority policy** in core decides
  among overlapping candidates (smallest bbox wins; animated ink
  beats scaffold at equal size — but scaffold IS selectable: barlines
  are M5's handle). Headless-tested with synthetic candidate lists.
- **Selection state lives on AppState** (transient — never in the
  document, never persisted; cleared on re-engrave since items
  rebuild). Signal: `selection_changed`.
- **Highlight**: a selection overlay item (bbox outline) added to the
  scene on select, removed on deselect — an overlay item, not a
  repaint of the element, so it cannot fight animation opacity or
  tinting. Export scenes are a separate ScoreScenes instance and
  never see it (the stage_view mask precedent).
- Esc / click-empty deselects. Click-to-seek on the waveform is
  untouched; the stage keeps drag-to-pan (selection is click, pan is
  drag — mirror the standard editor distinction; if the two gestures
  fight, rubber-band pan behind a modifier key is acceptable, flag
  it).
- Multi-select is OUT of M2 (single selection only; revisit if M3
  needs it).

**Exit criteria.** On testscore and complex3: click a notehead, a
slur, a hairpin, a barline, a part label — each selects, highlights,
and reports correct identity in the inspector; playback continues
undisturbed with a live selection; selection survives page flips (or
clears cleanly — decide and pin). Hit-priority policy headless-tested.

---

## M3 — Direct edit (the selection does something)

**Goal.** The graphical-editor feel: double-click text to edit it in
place, drag things to nudge them, restyle one element from its
context. All three route into machinery that already exists — this
milestone builds UI affordances, not new document semantics.

**Design.**

- **Double-click text edit in place.** A QLineEdit overlay positioned
  on the item's scene rect, committing on Enter/focus-out, Esc
  cancels. Routing by what the element is (all existing commands):
  - part label (`text_class "label"`) → the part-name override path
    (text_overrides → prep-seam re-engrave, Phase 9.3);
  - tempo mark (`text_class "tempo"`) → AddTempoOverlay (Phase 9.2);
  - stage texts (title/composer/lyricist) → EditStageText (9.1);
  - other engraved TEXT (system text, rehearsal marks…) → the
    overlay mechanism generalized from tempo marks — same
    hide-plus-replacement shape, one undo step. (The Texts… and Part
    Names… dialogs remain as the list view of the same commands.)
- **Drag-to-nudge** — finally consumes `LayoutOverride.dx/dy`. Drag a
  selected element (primary targets: dynamics, hairpins, texts;
  policy set `NUDGEABLE_KINDS`, start narrow) → live preview via item
  `setPos` → on release ONE undoable `SetLayoutOverride(eid, dx, dy)`
  (deltas in page coordinates, keyed by musical ElementId — override
  staleness stays the accepted rule 5 trade). Render applies dx/dy on
  scene build + on document change (diff idiom); export's
  `apply_hidden_overrides` grows into `apply_overrides` covering
  dx/dy so live and export cannot diverge. Arrow keys = 1-unit nudge,
  Shift for coarse. A reveal-clipped spanner moved in x interacts
  with its clip edge — spike first, and if it misbehaves, exclude
  REVEALED_KINDS from NUDGEABLE_KINDS in v1 and flag.
- **Per-element style from selection** (closes BACKLOG 9): the
  Selection panel gains color + effect controls writing
  `SetElementStyle`; "Clear overrides on selection" (the cheap reset
  rule 5 demands). Decision to make at the brief: on a cross-system
  spanner the override targets one `…:seg<k>` — the panel should fan
  out to all segments of the source (recommended), pin it by test.

**Exit criteria.** Rename a staff label by double-clicking it (score
shifts to fit, undo restores); edit a system text in place; drag a
hairpin 20px up and export — the exported frame matches the stage;
nudge, restyle, and clear-overrides on single elements, all undoable,
full suite green.

---

## M4 — Effects (the pop you can actually use)

**Status — CLOSED (built 2026-07-25 on `beta/m4-effects`, M4.1–M4.8
per docs/briefs/M4_EFFECTS_BRIEF.md; awaiting Marcus's interactive
exit run and the merge/tag).** The build's rulings, where reality
amended this section (details in the brief §0/§5):

- **F1/durations**: the engraved timemap's `off`/`restsOff` arrays are
  the duration source — `EngravedScore.note_durations`, resolved to
  animated elements by the `core/animation/durations.py` seam, carried
  as `TriggerSchedule.duration_by_element`. No next-onset inference
  anywhere; a tied notehead stretches over its OWN segment. Rests do
  not stretch (retrospective triggers).
- **F2/window**: the conservative per-trigger window was accepted PLUS
  a two-line expiry guard (measured ~2× mean saving); cost tracks
  elements genuinely mid-transition.
- **F3/peak offset**: a UNIFORM signed trigger shift for both signs
  (deviating from this section's positive-as-envelope reading) — the
  whole effect moves as one unit, so at −100 ms the note also appears
  that early (tooltipped verbatim). Page/system cursors stay on
  unshifted seconds. The positive-side envelope swell, if ever wanted,
  is a new preset, not this knob.
- **F4/schema**: v7, not v6 (v6 was taken); v5/v6 files load with
  unchanged look; unknown presets/params round-trip byte-identically.
- **F5**: the per-part effect submenu dropped as planned — per-part
  effect rules remain honored/round-tripped but unauthorable until
  M3's Selection panel (BACKLOG).

**Status — pulled forward, re-scoped (2026-07-24).** Moved ahead of
M2/M3 at Marcus's request and widened with three new controls
(amplitude, note-value relax, peak offset). The dependency note above
already sanctioned the move: M4 needs only M1, and it lands in
`core/animation/` + the Appearance & Effects panel while M2 lands in
hit-testing + the Selection panel — near-disjoint, so the two branches
can run concurrently. Branch `beta/m4-effects` off the same base M2
used; expect one small merge in the inspector-dock container.

**Goal.** Effects become a first-class, tunable, *global-by-default*
system with a proper UI home — and pop becomes shapeable: how strong,
how long, and *when* it peaks.

### Design — the settled parts

- **Global default effect** (the "pop applies to all staves" ask):
  resolution order becomes element override > part rule > **document
  default** > "appear". `StyleRules.default_effect` (stored intent,
  schema **v6**; missing key defaults to None → "appear", so no read
  gate). `SetDefaultEffect` command. The panel's Effect dropdown sets
  it; per-part deviations remain possible (Parts menu / part rules)
  but are no longer the only path.
- **Amplitude / intensity**: `_POP_SCALE` (1.25 today) becomes
  document intent. Pure preset data — `build_presets(floor)` grows to
  `build_presets(floor, params)` and nothing downstream notices.
- **Settle speed**: likewise `_POP_SETTLE_S` (0.25 today) — the
  LINEAR keyframe's `t_rel`. Pure preset data.
- **Storage**: `StyleRules.effect_params`, a sparse
  `{preset_name: {param_key: value}}` map (schema v6 alongside
  `default_effect`). Params an unknown future preset doesn't consume
  round-trip untouched — the effect-name precedent. One command class,
  `SetEffectParam(preset, key, value)`, coalescing on drag the way the
  existing spinbox commits do.
- Floor opacity and Sweep (already in the panel from M1) group
  visually with these. The per-part effect submenu drops out of the
  Score menu once the panel covers it.

### Design — the two that need a ruling first

The original M4 text claimed "the evaluator and applier change not at
all." **That is no longer true** and the claim is withdrawn here.
Amplitude and settle speed are still pure data; the two below are not.
Both are flag-and-stop items for the brief — surface them, do not
work around them.

- **"Animate entire note value"** (settle lasts the note's own
  duration: a whole note relaxes slowly, an eighth pops and settles).
  Envelopes are keyed on `t_rel` seconds and one `Effect` is one fixed
  shape shared by every element, so this needs a **per-element time
  scale**. Recommended shape: the kernel looks up
  `(t - trigger) / timescale` instead of `t - trigger`, with
  `timescale = 1.0` when the toggle is off — a multiply, not a branch,
  so rule 6 survives. (Alternative to name and reject or accept: mint
  bucketed effect variants keyed by quantized duration — no signature
  change, but quantization is visible and the window problem below is
  unchanged.) Three consequences to settle in the brief:
  1. `Effect.duration` currently defines the applier's single cached
     transition window `[trigger, trigger + duration]`. With per-
     element scaling the real window is `duration * timescale`.
     Recommended: keep ONE window, computed conservatively as
     `duration * max_timescale`; short notes re-evaluate past their
     settle into a no-op state. Cheap, and the applier keeps its
     shape. Measure it before accepting.
  2. **Where does note duration come from?** Rule 12 — the engraved
     timemap is the beat authority — so durations come from there, not
     from a music21 re-derivation. First thing to check: whether the
     timemap exposes durations or only onsets. If only onsets, say so
     and stop rather than inferring duration from the next onset in
     the voice (wrong across rests, chords, and voice splits).
  3. Duration in seconds is tempo-dependent: it must route through the
     one swing-aware `resolve_seconds` seam and re-time on bpm/swing
     change, on the same retime path a floor-opacity commit uses.
- **Peak offset** (max pop before or after the onset). The two signs
  are not symmetric:
  - *Positive* (peak lands after the beat) is pure envelope data:
    scale ramps 1.0 → peak at `t_rel = offset` → 1.0 at
    `offset + settle`. All keyframes stay ≥ 0; `duration` grows by
    `offset` and already handles it.
  - *Negative* (peak before the beat) needs `t_rel < 0`, which the
    envelope model does not represent — `initial` covers everything
    before the first keyframe, and `duration` as max-`t_rel` would
    misreport the window. Recommended: implement offset as a signed
    shift of the **trigger**, not of the keyframes — the whole effect
    (opacity step and scale peak together) moves early or late, every
    keyframe stays ≥ 0, and "the pop happens ahead of the beat" is
    what it looks like. The cost, which must be stated in the UI: at a
    negative offset the note also *appears* that much early. If what's
    wanted instead is appearance-on-beat with a pre-swell on the floor
    ghost, that is signed `t_rel` and a real model change — flag it,
    do not assume it.
  - UI naming: the transport already has an "offset" (audio sync).
    This one is **"Peak offset"** in the Effects panel so the two
    never read as the same knob.

### Invariants to hold

Rule 5 — params are intent; note durations are derived and never
stored. Rule 6 — a timescale scalar is an input, not a branch; the
moment anyone writes `if effect.name == "pop"` inside the evaluator,
stop. Rule 1 — no Qt in `core/`. Rule 12 — durations from the engraved
timemap. No-monoliths — the Effects panel is its own module under
`ui/panels/`, and the duration lookup is its own seam, not a limb
grafted onto the applier. ARCHITECTURE §5 — this work legitimately
edits `core/animation/`, but the timescale must ride the shared
`AnimationInputs` seam so export inherits it with **zero** exporter
edits; needing to touch the exporter is the flag.

**Exit criteria.** Fresh document: choose "pop" in the panel — every
part pops with no per-part setup. Raise amplitude, halve settle, and
see it live and in export. Toggle "animate entire note value" on a
score with mixed durations: a whole note visibly relaxes over its full
length while an eighth settles at once, and both stay correct after a
tempo change. Set peak offset ±100 ms and see the peak move relative
to the beat. Save/reload round-trips v6 (and a v5 file loads with
unchanged look); undo steps through each knob individually. Suite
green, exported frames match the stage at every setting.

---

## M5 — Breaks (system-break authoring)

**Goal.** Select a barline, toggle "System break", and the score
re-engraves with the break — the app's first *layout-intent* edit.

**Design.**

- **Document**: `system_break_overrides` (schema **v8** — M4 took v7,
  2026-07-25; the "folded bump" option is gone since M4 shipped
  alone): a sparse map of measure
  ordinal → FORCE_BREAK | SUPPRESS_BREAK. User intent only; the
  resulting layout re-derives (rule 5). Keyed by measure ordinal
  (adapter item 12), never printed number.
- **Prep seam**: the overrides rewrite `<print new-system>` on part 1
  of the canonical MusicXML before Verovio — upstream of
  repagination/hide/condense/scale-to-fit, which then operate on the
  edited break set exactly as they do on encoded breaks today. The
  Phase 8/9/12 injection pattern; ids for unaffected measures are
  minted from musical position and survive (pin by test).
- **UI**: barline selected (M2 made scaffold selectable) → context
  menu / Score menu "Toggle system break here", ordinal read from the
  barline's ElementId. `SetSystemBreak` undoable command; re-engrave
  via the `_applied_*` diff, the hide-empty-staves shape.
- **CLAUDE.md rule 7 amendment (draft — apply with the build
  ruling):** *"Amendment (M5, 2026-XX-XX): the honored system-break
  set is the encoded breaks ⊕ the user's in-app break overrides
  (doc.system_break_overrides, applied at the prep seam). Still never
  window reflow: an edited break set is an engraving input like a
  part rename."*

**Exit criteria.** On bigband1: force a break mid-way — the system
splits, downstream repagination stays sane, animation and reveal
edges are correct on both new systems; suppress an encoded break —
systems merge; both undo cleanly; save/reload reproduces; goldens for
unmodified fixtures unchanged. Suite green.

---

## Explicitly not in beta scope

Unchanged from the alpha backlog (`docs/BACKLOG.md` is still the live
list): single-wavefront sweep (BACKLOG 8 — its own design round),
per-region swing UI (7), condensing sophistication (a2/divisi),
per-voice reveal (10), repeat-skipping recordings, glow,
auto-alignment, continuous scroll. Page-break authoring (as opposed to
system breaks) is deliberately deferred until M5 proves the pattern.
