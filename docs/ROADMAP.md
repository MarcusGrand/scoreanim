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
- Beta bumps the project schema (M4 → v6, M5 → v7). The alpha build
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
| M4 | **Effects** | Effects panel: global default effect ("pop for everything"), tunable pop strength/speed, floor + reveal controls rehomed. |
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

**Goal.** Effects become a first-class, tunable, *global-by-default*
system with a proper UI home — the Appearance & Effects panel.

**Design.**

- **Global default effect** (the "pop applies to all staves" ask):
  resolution order becomes element override > part rule > **document
  default** > "appear". `StyleRules.default_effect` (stored intent,
  schema **v6**; missing key defaults to None → "appear", so no read
  gate). `SetDefaultEffect` command. The panel's Effect dropdown sets
  it; per-part deviations remain possible (Parts menu / part rules)
  but are no longer the only path.
- **Tunable pop**: pop strength (scale factor) and speed (settle
  seconds) become document intent — `StyleRules.effect_params`
  (sparse mapping, schema v6 alongside default_effect). Presets stay
  data (rule 6): `build_presets(floor)` grows to
  `build_presets(floor, params)`; the evaluator and applier change
  not at all. Labeled fields + sliders in the panel, live preview on
  commit (a retime, same cost as the floor spinbox today).
  Parameters an unknown future preset doesn't consume round-trip
  untouched (the effect-name precedent).
- Floor opacity and Sweep controls (already in the panel from M1)
  visually group with this. The per-part effect submenu entries drop
  out of the Score menu once the panel covers them.

**Exit criteria.** Fresh document: choose "pop" in the panel — every
part pops with no per-part setup; raise strength, halve speed, and see
it live and in export; save/reload round-trips v6 (and a v5 file loads
with unchanged look); undo steps through each knob. Suite green.

---

## M5 — Breaks (system-break authoring)

**Goal.** Select a barline, toggle "System break", and the score
re-engraves with the break — the app's first *layout-intent* edit.

**Design.**

- **Document**: `system_break_overrides` (schema **v7**, or folded
  into v6 if M4/M5 land in one bump — decide at the brief; the v3
  precedent favors one designed bump): a sparse map of measure
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
