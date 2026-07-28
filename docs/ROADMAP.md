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
| M6 | **Pages** | Page-break authoring on the M5 pattern, plus the left layout zone that finally gives break authoring a home. |

Dependency shape: M1 first (every later control lands in its chrome).
M2 before M3 and M5 (both act on a selection). M4 needs only M1 and can
be pulled earlier if a break is wanted between selection work. M6 needs
M2 for the selection, M5 for the whole pattern it repeats (stored
sparse intent, prep-seam rewrite, pure toggle policy, fat-apply
command, D8/D9 re-anchor and selection restore) and M1 for the dock
shape its layout zone copies.

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

**CLOSED 2026-07-25** (built M2.0–M2.7 on `beta/m2-selection` per
`docs/briefs/M2_SELECTION_BRIEF.md`). The brief's §1 audit was
re-verified against the tree and held in every particular; its
recommendations D1–D7 were all taken as written:

- **D1 gesture** — click = press/release under `startDragDistance()`;
  pan byte-for-byte unchanged, **no modifier key needed**.
- **D2 page flip (the decision the exit asked to pin)** — the
  selection **SURVIVES**. Scenes are per-page and retained and the
  overlay lives in its element's own page scene, so survival is the
  zero-cost behavior; clearing would have cost extra code. Matches
  every DAW/notation editor, and M3 wants it (flip away, come back,
  still editing what you picked). Pinned at controller and window
  level.
- **D3** selection = `ElementIdentity | None` on AppState;
  **D4** measure parsed from the id; **D5** stage texts unselectable;
  **D6** overlay item highlight; **D7** Esc at view level.

Two rulings the build added, both forced by the M2.0 census
(`spikes/hit_census.py`, findings C/D) measuring the roadmap's own
hit-priority rule on testscore and complex3:

- **The order is `(not exact, tier, area, element_id)`,** not
  area-then-scaffold. "Smallest bbox area wins" picks the wrong
  element twice. (a) A stem's authored `Rect` has **w = 0**, so its
  area is 0 and a stem beats the notehead it hangs off — clicking a
  note selected its stem. Ranking ink that genuinely CONTAINS the
  click ahead of mere tolerance neighbours fixes it. (b) A system
  barline's bbox spans the staves it joins, so it is **larger** than
  one staff's STAFF_LINES, and both are scaffold — so "animated beats
  scaffold" cannot separate them and area alone handed **every barline
  click to the staff**, which would have left M5 with no handle.
  STAFF_LINES therefore get their own backdrop tier and rank last
  among equals. Both corrections are DATA (a tier table, a measured
  boolean), not branches on a kind name. Accuracy clicking elements on
  their own ink, area-only → tiered on complex3: notehead 37→74%,
  staff lines 20→90%, hairpin 87→100%, barline 96→100%; never worse on
  any kind of either score, and every element is reachable.
- **A click tolerance is mandatory, not a nicety** — at tol=0 thin ink
  returns nothing at all. 6 page units (~3 view px at fit zoom).

Two fixes the build made outside the brief's scope, both real:
`SelectionController` had guessed the clicked page by `sceneRect`
containment, but every page scene shares one rect, so clicks on page
2+ searched page 1 (the complex3 hairpin selected nothing);
`StageView.clicked` now carries the scene. And the inspector body
became **scrollable** — the new Selection section pushed the dock's
minimum height past the test screen, and sections keep accruing
controls, so the dock must never dictate the window's minimum height.

Exit finding to carry into M3: `ui/main_window.py` is now at **399
lines**, exactly the no-monoliths ceiling. M2 added only wiring; M3
must split the composition root before adding to it (BACKLOG).

**Amendment 2026-07-27 — reopened before merge (M2.8).** Two rulings
change M2's shipped behavior, so M2 is not closed for good until they
land. Both are recorded here as INTENT; the mechanisms they force are
decisions to be measured, not assumed, and get written up only once
they are made.

- **Selection is object-first, with implicit measure and part**
  (now CLAUDE.md rule 13). This does not overturn D3/D4 so much as
  widen them: the containing measure was already parsed from the id,
  and the owning part joins it, as one structured selection context
  rather than three unrelated fields. A measure is never itself a
  selection target. Barlines remain selectable as objects — the M5
  handle the tiering in this milestone exists to protect.
- **The highlight tints the selected object's own ink (orange for
  now); the bbox outline goes away.** This SUPERSEDES D6, and it gives
  up two properties the overlay bought for free. (a) The overlay could
  not fight animation opacity, part tinting, or a spanner's reveal
  clip; a tint on the element competes with all three, and M4 is
  merged, so a selected note can be mid-pop with an effect driving its
  color. (b) Export purity was structurally free — export builds its
  own `ScoreScenes` and could not see a separate item; a tint has no
  such shape and must be re-proven at the same strength, non-vacuity
  guard included. A third constraint arrives with M3: a user who
  color-overrides an element orange must still be able to see that it
  is selected.

**M2.8 as built (2026-07-27).** Both rulings landed; the mechanisms
below were measured first and written after. One correction to the
intent above: it says an effect may be "driving its color", but
`_PROPERTY_APPLIERS` maps exactly two properties, `opacity` and `scale`.
No effect drives color at all — color reaches an element only from
StyleRules. The tint therefore competes with animation **opacity**,
**authored color**, and the spanner **reveal clip**.

The two decisions the amendment left open, now pinned:

- **Clicking empty staff space DESELECTS** (supersedes the M2.0
  backdrop reachability goal). Nothing downstream could act on a
  STAFF_LINES selection anyway: it is in `STATIC_KINDS` so it never
  animates, absent from `TINTED_KINDS` so no color override can reach
  it, and rule 13 names the barline as M5's only handle. The old
  behaviour was not even consistent — probing points inside staff
  rectangles picked STAFF_LINES on 17.5% of testscore probes but 73.5%
  of complex3's, tracking rastral size rather than intent. It was also
  STEALING clicks from real objects, since exactness is the first key
  and an exact staff-line hit outranked a notehead the click merely fell
  within tolerance of; 6 testscore and 15 complex3 probes now resolve to
  the object instead (complex3 KEY_SIG 34→43, METER_SIG 16→24).
  Mechanism is `is_selectable`, a table like the tier — which itself is
  unchanged, so a barline drawn across a staff still wins.
- **The implicit measure and part are PANEL-ONLY.** No stage treatment.
  Giving derived context its own ink would make it look chosen, which is
  the one thing rule 13 forbids, and a faint measure box would
  reintroduce exactly the rectangle being deleted — as the only
  rectangle on screen it would read as a selection.

The compositing rule that answers the animation collision, plus the
opacity floor, the ghost-lift, and the authored-color fallback that
implement it, are recorded in ARCHITECTURE §7. Export purity is
re-proven there too, on a different argument than M2.4's, with the
non-vacuity guard replaced by one matched to the tint.

Two things the change also surfaced. M2.7's "playback undisturbed" pin
had been passing **vacuously**: it sampled the first notehead, which
triggers on the downbeat, so the element sat at opacity 1.0 at every
sample. It now picks a notehead the samples straddle and fails if they
do not. And `ui/main_window.py` needed **zero** lines — its four
selection lines are construction and wiring — so it is still at 399 and
the BACKLOG 9b split is still M3's to do.

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
  **Inherited from M2.8:** the element key is `selection.obj.
  element_id`, and the selection-vs-authored-color problem is already
  solved — `ElementItem` composes authored color under the transient
  tint (never through `set_color`, which the DocumentSync diff cache
  owns), and a user who colors an element the selection orange still
  sees it selected via the fallback color. M3 adds a writer for the
  authored channel; it must not add a second writer for the tint.

**Exit criteria.** Rename a staff label by double-clicking it (score
shifts to fit, undo restores); edit a system text in place; drag a
hairpin 20px up and export — the exported frame matches the stage;
nudge, restyle, and clear-overrides on single elements, all undoable,
full suite green.

**CLOSED 2026-07-27 except one route** (built M3.0–M3.4 on
`beta/m3-direct-edit` per `docs/briefs/M3_DIRECT_EDIT_BRIEF.md`). Four
decisions were measured and then ruled by Marcus; the measurements are
in the brief §3 and in `spikes/nudge_reveal.py` / `spikes/seg_fanout.py`.

**M3.0 — BACKLOG 9b paid first, as its own commit.** `main_window.py`
399 → 312 lines (317 after M3's own wiring). Both seams are the ones 9b
named: `ui/view_router.py` took the presentation routing, and
`ui/parts_menu.py` took the three part-shaped dialogs — it was already
handed the parts they need on every load, so the data and its dialogs
now live together and the window holds neither. The fourth opener,
Texts…, moved at M3.1 to `ui/text_edit.py`, which owns the engraved
layout it reads. `tests/test_view_router.py` gives the routing the
direct coverage it never had as window methods.

**R1 — D5 stands; double-click has its own hit path.** The two gestures
ask different questions: selection asks which rule-13 OBJECT was picked,
and an object carries a measure and a part, which a stage text has
neither of. So stage texts remain unselectable while being editable.
This is load-bearing rather than tidy — the moment a tempo mark is
overlaid the thing on screen IS a stage text, so without it you could
never re-edit a replacement you had just created.

**R2 — fix the reveal-clip cache, keep HAIRPIN nudgeable.**
`NUDGEABLE_KINDS = {DYNAMIC, HAIRPIN, TEXT}`. The spike found the
interaction the roadmap suspected, but not where it guessed:
`RevealPathItem` maps the reveal edge from a SCENE x through an inverse
scene transform it caches on first use, so a moved element revealed as
if the playhead were dx further right — the error is exactly dx (+30.00
for a +30 nudge). Invalidating on move makes the local clip track
exactly −dx and stay y-independent, measured at ±10 in x and ±20 in y.
Two things this settles: excluding `REVEALED_KINDS` would have deleted
this section's own primary target, since HAIRPIN is one; and a pure-y
nudge is unaffected even unfixed, so the exit criterion above would have
passed either way and could not have caught it.

**R3 — the `:seg` fan-out happens** (this section's recommendation,
confirmed against the grammar). Audited on four fixtures before ruling:
30124 elements, 116 broken spanners, zero nesting, zero orphans, zero
identity mismatch between a segment and its source, sources only ever
TIE/SLUR/HAIRPIN. It forced one thing this section did not anticipate:
a three-segment family written as three commands is three undo entries
for one gesture, so `SetElementStyle` gained a `segments` field — the
"fat apply" idiom `ApplyScoreSetup` already names, not a new command.

**R4 — M4's F5 closes here.** Per-part effect rules become authorable
again via a scope switch (this element / this part) on the same two
controls. It governs colour as well as effect, and disables itself on
score-level ink, which has no part.

**The part-label route is NOT built, and the reason is measured.** This
section routes a part label to the part-name override; `SetPartText` is
keyed by `PartId`, and the engraved label element has none. Verovio
emits labels as direct children of `<g class="system">` with no staff or
part ancestor, so the adapter mints them `score:p<PAGE>:text:<n>` with
`part=None` — and the goldens pin that null. Supplying the attribution
is an adapter change that moves goldens, which is outside this
milestone's "UI affordances, not new document semantics". The routing
policy is written and unit-tested; the end-to-end test asserts the
current limitation and fails the moment labels gain a part. **The first
exit criterion is therefore unmet** and carried as BACKLOG 14; the other
four are met, with "edit a system text in place" pinned on both engraved
text classes that are neither tempo nor furniture (`dir`, `reh`).

Multi-select stayed OUT, as M2 left it: neither restyle nor nudge
needed it to be usable, so no case was made.

---

## M4 — Effects (the pop you can actually use)

**Status — CLOSED (built 2026-07-25 on `beta/m4-effects`, M4.1–M4.8
per docs/briefs/M4_EFFECTS_BRIEF.md; merged to `main` together with M2
at `8e06f7d`, tagged `v0.2-beta.2`).** Because that tag covered two
milestones, the milestone→tag mapping in "Versioning & conventions" is
offset by one from here on: M3 closed as `v0.2-beta.3`, and M5 closes
as **`v0.2-beta.4`**. The build's rulings, where reality
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

**Status — CLOSED (built 2026-07-28 on `beta/m5-breaks`, M5.0–M5.7 per
docs/briefs/M5_BREAKS_BRIEF.md; interactive exit run passed, merged to
`main` at `d912040`, tagged `v0.2-beta.4`).** 960 passed / 1 xfailed,
goldens byte-identical. What was built and where reality differed is at
the end of this section.

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
  **Inherited from M2.8:** read the ordinal off
  `AppState.selection.measure_ordinal` rather than re-parsing the id —
  the derivation lives in one place (`core/selection/context.py`) and
  already returns None for the ids that genuinely have no measure. The
  barline handle is now the ONLY scaffold handle into a measure: the
  backdrop stopped being selectable at M2.8, so nothing else on a staff
  answers a click with a measure ordinal.
  **Inherited from M3 (2026-07-27):** (a) the re-engrave the break
  overrides trigger goes through **`ui/view_router.py`** now —
  `_reengrave` calls `router.show_current()`, so a forced break must
  leave the router's page/system position sane, and the router is where
  to look if it does not. (b) M3 needed no window-level split of its
  own; `main_window.py` is at 317 lines, so M5's wiring has room, but
  the same rule applies before it grows further. (c) If M5 ever wants
  one gesture to touch several document fields, the answer is the "fat
  apply" idiom — widen the command, as M3.3 widened `SetElementStyle`
  with `segments` — not a macro command, which still does not exist.
  (d) `Selection.measure_ordinal` is unchanged and still the property
  to read; M3 added no third caller of `measure_ordinal_of`, so BACKLOG
  9(c) is still open rather than resolved.
- **CLAUDE.md rule 7 amendment — APPLIED 2026-07-28** with the D7
  sentence the ruling added (a suppression clears a coincident encoded
  new-page, and pagination re-derives, so the page count is owned, not
  clipped). The drafted wording is now in CLAUDE.md rule 7; this bullet
  is kept as the record of where it came from.

**Exit criteria.** On bigband1: force a break mid-way — the system
splits, downstream repagination stays sane, animation and reveal
edges are correct on both new systems; suppress an encoded break —
systems merge; both undo cleanly; save/reload reproduces; goldens for
unmodified fixtures unchanged. Suite green.

**Fixture caveat (from M3, `spikes/seg_fanout.py`):** bigband1 does
NOT load under the strict path — `unknown SVG class 'gliss'` raises in
`load_detailed(strict=True)`, the pytest/doctor default. The app path
degrades it to a warned OTHER (rule 4 amendment), so the interactive
exit run is fine; headless tests and spikes against bigband1 must use
the app path (`strict=False`) or a fixture that loads strict.

**BUILT M5.0–M5.6, 2026-07-28** on `beta/m5-breaks` per
`docs/briefs/M5_BREAKS_BRIEF.md`. All eleven decisions (D0–D10) were
ruled as recommended, with two riders (D7's amendment sentence, and
D1's shortcut + reason-carrying disabled state); the measurements
behind them are the brief §3 and `spikes/system_breaks.py`. Suite 924
passed / 1 xfailed, goldens byte-identical throughout.

Where reality differed from the brief, or the build had to decide:

- **M5.0** paid D0 first, as its own commit: `musicxml_prep.py` 577 →
  326 lines, with the eight tree-rewriting passes moving to
  `core/score/musicxml_rewrite.py` (294). The specs keep their home, so
  the rewrite module takes them under `TYPE_CHECKING`; all eight are
  re-exported, so no import site changed.
- **`EngravedScore.system_of_measure` was exposed at M5.2, not M5.3** —
  M5.2's own verification asserts on it. The adapter had always built
  it and thrown it away; the golden serializer names its fields
  explicitly, so goldens did not move.
- **The trap is real but one path was free.** `load_detailed` calls
  `prepare()` three times, not four: the hide-unavailable retry
  re-engraves the SAME prep and so carries the overrides without being
  told. The repagination and scale-to-fit retries both re-prepare and
  had to pass `system_breaks` explicitly. All three are pinned, the
  deepest on `tall_system_min`, where a forced break survives a
  re-prepare that repaginates AND scales to fit.
- **`SystemBreak` gets no neutral twin.** The `*Spec` dataclasses are
  twinned across `core/project` ↔ `core/score`, but a two-valued
  vocabulary has no fields to twin and the layering already lets the
  document import `core/score` (the `PartId` shape). One enum, no
  conversion at the seam.
- **The action requires a BARLINE**, which the brief implies but never
  states as a disable case. Rule 13 names the barline as M5's only
  handle, and D2's arithmetic ("the break falls after measure N") only
  holds for the measure's right barline — a notehead sits in a measure
  but not at a break position. It is the fourth reason the disabled
  action can name.
- **D10 warns on "could not be applied at the seam", not "had no
  visible effect"** — the latter would need a second no-override load.
  So the pass reports the ordinals it wrote nothing for: an ordinal past
  the end, and a suppression whose encoded break has gone. Suppression
  became a stricter delta as a result — it writes only where there IS
  an encoded break.
- **D9 needed one thing the brief did not anticipate.**
  `AppState.set_selection` no-ops on an EQUAL identity and fires no
  signal — right for its own contract, and exactly wrong across a
  re-engrave, where the identity is unchanged but the item carrying the
  tint is a different object. The controller re-lights it explicitly
  rather than making AppState re-emit for everyone. **BACKLOG 9 seam
  (b) is closed**; seam (c) is still open, as M5 read
  `Selection.measure_ordinal` and added no third caller of
  `measure_ordinal_of`.
- **Finding, not M5's to fix (see BACKLOG 16).** `_repaginate` strips
  ALL encoded `new-page` attributes and re-asserts its own plan, so a
  system break encoded ONLY as `new-page="yes"` is destroyed whenever
  repagination fires and the re-derived plan differs from the encoded
  one. That contradicts rule 7(a)'s own wording ("keeps the system
  breaks"). It is pre-existing Phase 10R behaviour, latent because on
  complex3 — the only fixture that repaginates at baseline — the
  re-derived plan happens to match the encoded breaks exactly. M5 is
  the first feature that can change system heights and so make the two
  diverge: on testscore, forcing a break at m19 also merges systems 1+2
  and 3+4, whose breaks are encoded as page breaks. Every M5 mechanism
  works correctly on top of it (the forced break survives; the page
  count stays owned), so it is flagged rather than fixed inside a
  milestone whose charter is a layout-intent edit.
- **Minor finding.** testscore's FINAL barline is a heavy double bar,
  and a click at its bbox centre lands in the gap between the two
  rules, outside M2's 6-unit tolerance, so it resolves to nothing. An
  M2 hit-geometry nuance; harmless for M5, since D6 disables the action
  on the last measure either way.

**M5.7 — "Move to Previous System" — ruled in scope 2026-07-28**, after
the interactive exit run passed and before the merge, and built the same
day (brief §M5.7, decisions D11–D15). With a selection whose object
carries measure ordinal N, N and any earlier measures of its system move
onto the previous system. It is a COMPOSITION of the two shipped
primitives — SUPPRESS at the first measure of N's system, FORCE at N+1 —
so there is no new document field, no new prep-seam pass and no schema
change (still v8). The symmetric move-down already exists as the plain
FORCE toggle.

- **`SetSystemBreak` widened rather than a macro**: a third field `also`
  carries the extra `(ordinal, mode-or-clear)` entries into the same
  `apply()`, so one gesture is one undo entry (rule 8). Exactly the
  answer inheritance note (c) above names, and the third use of the
  fat-apply idiom after `ApplyScoreSetup` and `SetElementStyle.segments`.
  `describe()` follows the M3.5 rule — a composed write says "change
  system breaks"; the menu label is where the gesture names itself.
- **Each half prefers CLEARING an opposite override to writing a new
  one**, which keeps the document sparse and the gesture reversible: a
  FORCE is only ever written where nothing was encoded, so removing it is
  exactly enough to remove the break.
- **The measurement changed a decision.** Writing the FORCE half where a
  system already starts (N is its system's last measure) produces the
  identical layout but trips D10's `break-override-inert` warning,
  because the seam rewrites nothing over an encoded break. Omitting
  inert entries is therefore a correctness rule, not tidiness — pinned
  by a test that loads the gesture both ways.
- **The action reads ANY object's implicit measure**, not only a
  barline: rule 13 says selecting an object carries its measure, and
  move-up needs a measure rather than a break position. The barline
  stays the handle for the raw toggle, whose "after measure N"
  arithmetic is specific to a right barline. Disabled with a reason for
  the first system, no selection, an object carrying no measure, a stale
  ordinal, and (defensively) an empty entry set.
- **D8's re-anchor needed generalizing**: `_break_anchor` re-anchored
  only when exactly ONE ordinal changed, so a two-ordinal gesture would
  have silently stopped re-anchoring. It now takes the lowest of at most
  two changed ordinals — the merge half, which is where the moved music
  ends up. D9's selection restore is unchanged.
- Suite **960 passed / 1 xfailed**, goldens byte-identical. Verified end
  to end on bigband1's app path: moving a mid-system bar up leaves the
  remainder a system of its own, systems 3–9 untouched, and the warning
  set identical to the baseline load.

A left-side retractable **layout zone** — a panel collecting these
layout affordances, and page-break authoring when it lands — is
**BACKLOG 17**, deliberately deferred until more than one action needs a
home. It is a candidate M6 pairing with page-break authoring.
**Ruled into M6 on 2026-07-28**; see §M6 below.

---

## M6 — Pages (page-break authoring + the layout zone)

**CLOSED 2026-07-28** — ruled, built M6.0–M6.8, merged to `main` at
`bf3a824` and tagged **`v0.2-beta.5`**. Two halves in one milestone,
paired because they want the same home and share a seam: page-break
authoring, and the left layout zone BACKLOG 17 deferred until more than
one action needed one. `docs/briefs/M6_PAGES_BRIEF.md` §4 records the
thirteen decisions (D0–D12), all ruled as recommended; "As built" below
records where reality differed and what that changed.

**Goal.** Select a barline, toggle "Page break" — the score repaginates
with it, on exactly the machinery M5 built for systems. And the layout
affordances stop living in a menu: a retractable zone down the left of
the stage collects them, so break authoring can be done in a pass down a
score instead of a menu round trip per edit.

### Half 1 — page-break authoring

**Design.** The M5 pattern, repeated. Nothing below is a new kind of
thing; every bullet names its M5 twin.

- **Document**: `page_break_overrides` (schema **v9**) — a sparse map of
  measure ordinal → FORCE | SUPPRESS, keyed by the measure that STARTS
  the new page (the D2 convention, which is also what `<print
  new-page>` and `_repaginate`'s `break_measures` already mean). User
  intent only; the layout re-derives (rule 5). Ordinals, never printed
  numbers.
- **Prep seam**: a `new-page` rewrite in
  `core/score/musicxml_rewrite.py`, a sparse delta on the encoded set.
  Whether that is a second pass beside `_apply_system_breaks` or one
  combined pass over both maps is a brief decision — the two write the
  same `<print>` element, and the measurement bears on it.
- **Policy**: `core/editing/breaks.py` grows the page toggle — the same
  barline handle, the same N+1 arithmetic, the same enable rules (no
  selection / not a barline / no measure ordinal / last measure), the
  same three-step toggle sense (clear an existing override, else
  suppress where a page already starts, else force). Pure, no Qt,
  headless-tested on synthetic maps.
- **Command**: `SetPageBreak`, undoable, sparse (`mode=None` pops),
  arriving via `execute()` never `preview()` — the re-engrave cost is
  M5's. It carries the fat-apply shape so one gesture that must touch
  both override maps is still one undo entry (rule 8).
- **Warning**: a D10-style inert-override `LoadWarning`, counted in the
  status bar like every other — plus, if never-clip is allowed to
  overrule authored page intent (question 1), a way for the app to say
  so rather than fail silently.
- **Inherited whole from M5**: D8's re-anchor (`ViewRouter.show_measure`
  off the measure the edit touched) and D9's selection restore across
  the re-engrave. Both generalize to two override maps rather than
  being rebuilt.

**The three questions this half must MEASURE, not assume.** They are why
M6 gets a spike before it gets code, and they are the reason page-break
authoring was deferred at all rather than shipped inside M5.

1. **Composition with rule-7(a) repagination.** `_repaginate` STRIPS
   every encoded page break when it fires and re-derives its own plan.
   So a user FORCE written upstream of it is destroyed exactly when the
   never-clip guard engages, and a user SUPPRESS can create the overflow
   that engages it. Both directions get measured, and the milestone must
   propose what wins, with what warning. The likely shape — to be
   confirmed, not assumed — is that user page intent becomes an INPUT to
   the plan rather than a pass the plan overwrites.
2. **Collisions between the two override maps at one ordinal.** A page
   break implies a system start, and M5's D7 already couples the two
   attributes in one direction (a system SUPPRESS clears a coincident
   `new-page`). The four combinations get measured through the real
   pipeline, and the milestone proposes either a precedence rule at the
   seam or prevention at the policy level.
3. **Pass ordering, and the M5.2 trap times two.** Where the page
   rewrite sits relative to the system rewrite and to `_repaginate`, and
   the fact that all three `prepare()` calls in `load_detailed` must now
   carry BOTH override sets. M5 found one of the three free (the
   hide-unavailable retry re-engraves the same prep); that does not make
   the other two free twice.

Plus the §3.3 downstream sweep re-run for pages: scale-to-fit and
hide-empty-staves under forced and suppressed page breaks, warning sets
compared against baseline.

**Draft CLAUDE.md rule 7 amendment** (applied at build with the ruling
date — the M5.6 pattern; the never-clip precedence sentence is a draft
until the question-1 measurement is ruled):

> Amendment (M6, 2026-07-28): the honored PAGE-break set is the encoded
> page breaks ⊕ the user's in-app page-break overrides
> (`doc.page_break_overrides`), applied at the prep seam beside the
> system-break delta. Page breaks are the one layout input the app
> already OWNED before the user could author them — rule 7(a)'s
> never-clip repagination re-derives them whenever a system would
> overflow — so authored page intent is honored *within* that guarantee,
> not above it: a forced page break survives repagination, and a
> suppressed one is overridden, and warned, whenever honoring it would
> clip ink. Never-clip stays absolute; the page count stays owned.

### Half 2 — the layout zone

**Design.** BACKLOG 17, built as an **M1-style re-home of existing
commands, not new semantics**. A LEFT retractable dock on the M1 dock
pattern: `QDockWidget` with an `objectName` for `saveState` identity,
its `toggleViewAction()` in the View menu, persisted by the existing
`window_state.py` pair (which saves the whole `QMainWindow` state, so it
should cover a third dock without new persistence code — verify, and
consider whether `_STATE_VERSION` must bump so an existing stored layout
does not place the new dock badly).

v1 content is a re-home and a readout, nothing more:

- the system-break toggle, Move to Previous System, and the new
  page-break toggle — **the same QActions** the Score menu holds, so the
  panel and the menu drive the same commands and cannot diverge;
- a readout of the active break overrides (both maps, by ordinal) with a
  per-entry clear, which needs no new command: `mode=None` already pops
  an entry.

**Menu actions stay.** The Score menu keeps every action; the zone is a
second surface over the same controller (`ui/break_action.py`), exactly
as D1 said a context menu would be. Own module(s) under `ui/` — no
monoliths.

**Boundaries.** Half 2 adds no document field, no command, and no
engraving input. If it starts wanting one, that is the flag.

**Exit criteria.** On bigband1 (app path, the `gliss` caveat): force a
page break mid-score — the page splits, systems and reveal edges stay
correct on both pages, and `score_end` and the trigger count do not move
(rule 12: a page break is a layout choice). Suppress an encoded page
break — the pages merge, or never-clip overrides it *and says so*. Both
undo cleanly in one entry each; save/reload reproduces (v9); a v8
project loads with no overrides and an unchanged look. The layout zone
drives all three actions, mirrors their enabled state, lists the active
overrides and clears them individually. Goldens byte-identical for
unmodified fixtures. Full suite green.

**Fixture caveat, unchanged from M5.** bigband1 does not load strict
(`unknown SVG class 'gliss'`), so the interactive exit run is the app
path and headless tests/spikes against it must pass `strict=False`.

**BACKLOG 16 is M6's to rule on.** `_repaginate` destroying a system
break encoded only as a page break was flagged rather than fixed inside
M5, on the grounds that M5's charter was a layout-intent edit. M6's
charter is page breaks, the bug is in the page-break machinery, and
question 1 above cannot be answered cleanly around it. Whether M6 pays
it — as its own commit before any feature code, the M5.0 shape — is a
decision for the brief, with the golden impact measured first.

### As built (M6.0–M6.8, 2026-07-28)

All thirteen decisions were ruled as recommended and built that way.
Four places where reality differed are recorded here, because each
changed either a measurement or a line of code:

1. **BACKLOG 16 is NOT golden-free (M6.0).** The brief's F1 measured the
   promotion as a total no-op on all four fixtures, but probed each in
   ONE configuration — and neither of the two GOLDEN loads that actually
   repaginate was that configuration (complex3 is probed flat, its
   golden is hidden; video_test is not in F1's list at all). Two of the
   twelve goldens move, and both movements are the fix working:
   `video_test_flat`'s engraving is byte-identical, with only the
   canonical-XML hash and the load-warning ORDER changing (a new `<sb>`
   shifts Verovio's seeded id sequence; verified deterministic across
   three processes), and `complex3_hidden` goes from 20 systems to
   **21 — exactly its encoded set**, having been silently losing one
   encoded system break on `main`. Both baselines re-captured in the
   M6.0 commit, which is the golden suite's own protocol for a
   deliberate behaviour fix. The damage this repairs was live, not
   hypothetical.
2. **A suppression is not subtracted from the never-clip plan (M6.3).**
   D1 said "suppressed ordinals are dropped from it"; the ROADMAP
   amendment above said "a suppressed one is overridden, and warned,
   whenever honoring it would clip ink", and the spike's data could not
   tell the two apart (`plan ∩ suppressed` was empty in every measured
   row). It can now: the suppression is applied at the seam, so the
   planner measures the piled-up layout it produced and every break it
   emits is one it NEEDS. Dropping them cost bigband1 a 4-page plan for
   a 2-page one rescued by scale-to-fit at **40%**, and testscore's A6
   row **51%** — legal, unclipped, and much worse scores than the extra
   page. `plan_page_breaks` therefore takes `forced` only, and a
   suppression is honored wherever the planner does not need that break.
3. **Two brief measurements moved because the ruled D3 fix changed the
   input.** §3.1 A6 and §3.2 B2 were taken with the spike prototype,
   which cleared `new-page` alone and so destroyed two SYSTEM breaks; with
   those preserved, the same music needs three pages rather than two.
   The tests pin the new numbers and say why.
4. **`core/editing/breaks.py` split before the page half landed**, per
   §7's own watch — one module per document map (`breaks.py`,
   `page_breaks.py`) with the rule that couples them in
   `break_coherence.py`. `_STATE_VERSION` did NOT need bumping (D10
   measured, not assumed), so no user loses their window layout.

Suite **1042 passed / 1 xfailed** at M6.7, from 960 at the branch point;
goldens byte-identical for every unmodified fixture at every commit
after M6.0; no `ui/` module over ~400 lines.

---

## Explicitly not in beta scope

Unchanged from the alpha backlog (`docs/BACKLOG.md` is still the live
list): single-wavefront sweep (BACKLOG 8 — its own design round),
per-region swing UI (7), condensing sophistication (a2/divisi),
per-voice reveal (10), repeat-skipping recordings, glow,
auto-alignment, continuous scroll.

Page-break authoring **is no longer on this list**. It was deferred
until M5 proved the pattern; M5 proved it twice (the toggle and M5.7's
composition), and Marcus ruled it into **§M6 — Pages** on 2026-07-28,
paired with BACKLOG 17's layout zone.
