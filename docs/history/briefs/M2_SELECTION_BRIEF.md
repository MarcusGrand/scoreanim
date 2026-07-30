# M2 planning brief — Selection (click-to-select on the live stage) (2026-07-24)

Written by a planning session, 2026-07-24, against ROADMAP.md's M2
milestone (the scope authority — what M2 IS; this brief is how it gets
built). Goal, from the roadmap: click any element on the stage — during
playback or paused — to select it: it highlights, and the inspector's
Selection panel shows its musical identity. This is the foundation
BACKLOG 9 and the layout-override slots have waited for since Phase 4/5.

**Boundaries (roadmap, restated as law for this build):**

- **Selection ONLY.** No editing, no nudging, no styling from the
  selection — all M3. No document mutation exists in this milestone at
  all: selection is transient UI state, so rule 8 (undoable commands)
  is not triggered — there is nothing to undo. `core/` gains exactly
  one pure module (the hit-priority policy); commands, ProjectDoc,
  serialization, and the render pipeline are untouched.
- **Single selection only.** Multi-select is out; revisit if M3 needs
  it.
- Click-to-seek on the waveform is untouched; the stage keeps
  drag-to-pan.
- No monoliths: selection logic lives in its own modules (map in §2),
  never bolted onto `main_window.py`.

## 1. What the code gives us today (verified against the tree, 2026-07-24)

The render layer was built for this milestone; the three advertised
hooks all check out, and the audit found four real wrinkles the roadmap
design didn't know about. Numbered so tasks can cite them.

1. **ElementItem carries identity + bbox** (`render/items.py`):
   `identity`, `bbox`, `anchor`, `system` are constructor state, page ==
   scene == item-local coords. Confirmed.
2. **GroupItem deliberately does not grab child events** — it is a
   plain QGraphicsItem with empty `paint()`, not a QGraphicsItemGroup,
   exactly so children stay individually hit-testable and we walk UP to
   the parent. Confirmed. **Wrinkle (a):** the default
   `QGraphicsItem.shape()` returns `boundingRect()` as a path, and
   `GroupItem.boundingRect()` is `childrenBoundingRect()` — so the
   PARENT itself hits anywhere in its children's united bbox. A
   staff-lines element spans its whole system; every click on a page
   would return it (and every other bbox-overlapping parent) as a
   candidate. Resolution (task M2.3): override `GroupItem.shape()` to
   return an empty QPainterPath — parents become hit-transparent, hits
   come only from real ink children (QGraphicsPathItem shapes include
   pen stroke, so thin stems/staff lines stay clickable), and the
   controller walks child → parent. Nothing else consumes GroupItem
   shape (no scene selection flags, no collision use) — verified.
3. **Scene coords == page coords** (`render/scene.py` docstring and
   construction — one scene per page precisely so click-to-select needs
   no offset math). Confirmed.
4. **Wrinkle (b) — the gesture fight the roadmap anticipated:**
   `StageView` uses `ScrollHandDrag`, and in that drag mode the view
   consumes mouse events for panning — the scene never sees clicks, so
   scene-side `mousePressEvent`/`itemAt` approaches are dead on
   arrival. Resolution: view-level click detection — record the press
   position, and on release with displacement ≤
   `QApplication.startDragDistance()` treat it as a click and emit the
   scene position. Pan behavior is byte-for-byte unchanged (a
   sub-threshold drag never panned visibly anyway). **No modifier key
   needed** — the roadmap's rubber-band-behind-modifier fallback is not
   required.
5. **`scene.items()` returns only visible items**, so elements hidden
   via `LayoutOverride.hidden` (tempo-overlay originals) drop out of
   hit-testing for free. A fully clipped `RevealPathItem` (unrevealed
   spanner) is still `isVisible()` and still hits — correct: its
   floor-opacity ghost is on screen, and selecting a not-yet-revealed
   spanner is legitimate. Edge case, accepted: at floor 0 the ghost is
   invisible ink and a click there can select "nothing you can see".
6. **Stage texts are `ElementItem(identity=None)`** (title/composer/
   lyricist, tempo overlays). No musical identity → nothing for the
   Selection panel to report. Ruled here: **identity-less items are not
   selectable in M2** (the parent walk skips them). Flagged as an M3
   seam — M3's double-click-to-edit needs to hit stage texts and will
   add its own path for them.
7. The white paper rect and the M2 highlight overlay are top-level
   items, not ElementItem children — the parent walk drops them
   naturally. No special-casing.
8. **Wrinkle (c) — `ElementIdentity` has no `measure` field**, but the
   roadmap's readout ("kind, part, measure, voice, onset") wants one.
   The id grammar carries it: musical ids are
   `{part}:m{ordinal}:s{staff}:…`, scaffold `score:m{ordinal}:{kind}:{seq}`,
   continuation segments `{source-id}:seg{k}` (the `:m` of the START
   measure — right for a spanner), while grpsym/divider
   (`score:sys{n}:…`) and page furniture (`score:p{n}:…`) genuinely
   have none (verified in `core/engraving/verovio/identity.py`). M5
   already plans to read the barline's ordinal "from the barline's
   ElementId", so a pure id-parse helper is the sanctioned route — it
   lands in core now (task M2.1) and M5 reuses it. Ordinal, not
   printed number (adapter item 12); the panel can show the printed
   number too by looking the ordinal up in `AppState.measures`.
9. **Wrinkle (d) — system mode:** the scene under the view is the full
   PAGE; the letterbox mask is `drawForeground`, view-level. Masked-out
   ink from a neighbouring system is invisible to the user but fully
   hittable in the scene. Resolution: the view gates clicks — when a
   band is active (`_band` set), a click outside it is a
   deselect-click, never a hit. The gate lives in `StageView` (the only
   object that knows the band), so the controller stays mode-blind.
10. The inspector's Selection section is a placeholder QLabel behind
    `sections["selection"]` — `set_content()` is the swap-in point.
    Offscreen Qt-widget tests are established precedent
    (`test_inspector.py`, `test_app_state.py`, `test_render_scene.py`,
    `QT_QPA_PLATFORM=offscreen`), so M2's ui pieces get real tests, not
    just the core policy.
11. Re-engrave rebuilds every ElementItem (`MainWindow._install` adopts
    fresh scenes; `_reengrave` runs inside `_on_document_changed`
    BEFORE the sync passes). `_install` is therefore the one clearing
    hook that covers fresh loads AND re-engraves;
    `AppState.reset_document` covers project opens. Selection clears at
    both (roadmap: "cleared on re-engrave since items rebuild") — even
    though musical ids usually survive a re-engrave, re-resolving is
    M3+ polish, not M2 scope.

## 2. Design (module map + recorded recommendations)

New modules — each one job, all well under the ~400-line ceiling:

```
core/selection/
  __init__.py
  policy.py            PURE hit-priority policy: HitCandidate,
                       pick(candidates), measure_ordinal_of(element_id).
                       Imports STATIC_KINDS from core.animation.schedule
                       (the kind-policy authority) and nothing Qt-ish.
ui/
  selection.py         SelectionController: candidate collection
                       (scene.items → parent walk → HitCandidates),
                       policy call, AppState update, highlight overlay
                       add/remove.
  selection_panel.py   Inspector Selection section body: identity
                       readout rows, observes selection_changed.
```

`StageView` grows the click gesture + band gate and one signal;
`AppState` grows the selection slot + signal; `Inspector` swaps the
placeholder for the panel; `MainWindow` wires controller ↔ view ↔
state in its composition-root role (a few lines, no logic).

**Recommendations recorded for Marcus's confirmation before build
(defaults if unchallenged):**

- **D1 — gesture:** click = press/release under `startDragDistance()`;
  pan unchanged, no modifier key (§1.4).
- **D2 — selection SURVIVES page flips** (roadmap says decide and
  pin): scenes are all retained and the overlay lives in its element's
  page scene, so survival is the zero-cost behavior; the panel keeps
  reporting the selection while you browse other pages, matching every
  DAW/notation editor. Flip back and the highlight is still there.
  Clearing instead would cost extra code.
- **D3 — selection state = `ElementIdentity | None` on AppState**
  (frozen core dataclass, like the `measures` runtime state it sits
  next to; signal `selection_changed`). Storing the full identity, not
  just the id, means the panel needs no resolver plumbing and a stale
  id can never be re-looked-up after items rebuild. Never persisted,
  never in ProjectDoc.
- **D4 — measure readout** parses `:m{ordinal}:` from the ElementId
  (pure helper, §1.8); elements without an `:m` segment show "—".
- **D5 — stage texts unselectable in M2** (§1.6), revisited by M3.
- **D6 — highlight = one QGraphicsRectItem overlay** on the element's
  `bbox` (slight padding), cosmetic pen (constant width at any zoom),
  high zValue, added to the element's page scene on select, removed on
  deselect — an overlay item, never a repaint of the element, so it
  cannot fight animation opacity, tinting, or reveal clipping. Export
  builds its own private ScoreScenes (`render/export.py`), so export
  frames structurally cannot contain it (the stage_view-mask
  precedent); task M2.4 pins that anyway.
- **D7 — Esc deselects at the view level** (`StageView.keyPressEvent`
  when a selection exists), not a window-global shortcut, so Esc keeps
  its normal meaning in dialogs and inspector fields.

Hit-priority policy (per roadmap): among overlapping candidates,
**smallest bbox area wins; at (near-)equal size animated ink beats
scaffold — but scaffold IS selectable** (barlines are M5's handle;
clicking a bare barline selects it because nothing smaller competes).
Deterministic total order: `(area, is_scaffold, element_id)` with
`is_scaffold = kind in STATIC_KINDS` — the lexical id tail makes the
pick permutation-independent. Empty candidate list → None (deselect).

## 3. Tasks

### M2.0 — Hit census spike

`spikes/hit_census.py`: offscreen (`QT_QPA_PLATFORM=offscreen`), build
`ScoreScenes` for testscore and complex3, run `scene.items()` at known
ink positions (a notehead, a slur's mid-curve, a barline, a staff line,
a part label) with and without the `GroupItem.shape()` override, with a
small tolerance rect (~3 view px mapped to scene units) and without.
Print candidate lists (eid, kind, bbox area). Confirms §1.2's shape
pollution and calibrates the tolerance; findings to `spikes/NOTES.md`.

**Verify:** run the spike; with the shape override the notehead click's
candidate list contains the notehead/stem family and NOT the
staff-lines or paper items; without it, staff lines pollute every list.
Keep the numbers in NOTES.md.

### M2.1 — Pure hit-priority policy (core)

`core/selection/policy.py`: frozen `HitCandidate(element_id, kind,
area)`; `pick(candidates) -> ElementId | None` implementing the order
in §2; `measure_ordinal_of(element_id) -> int | None` parsing the
`:m{ordinal}:` segment (handles `{part}:m…`, `score:m…`, `…:seg{k}`,
and returns None for `score:sys…`/`score:p…` ids). Type hints, no Qt.

**Verify:** new `tests/test_hit_priority.py`, headless: notehead beats
staff lines (smaller area); notehead beats barline; bare barline is
picked when alone (scaffold selectable); animated beats scaffold at
equal area; permutation of the input list never changes the pick;
empty list → None; `measure_ordinal_of` pinned on real id shapes from
§1.8 including a `:seg` id and a `score:sys` id. `pytest
tests/test_hit_priority.py tests/test_no_qt_in_core.py` green.

### M2.2 — Selection state on AppState

`AppState` gains `selected: ElementIdentity | None` (property),
`set_selection(identity | None)` (no-op when unchanged), and
`selection_changed = Signal()`. `reset_document()` clears it. Transient
only — no ProjectDoc field, no serialization touch, no command.

**Verify:** extend `tests/test_app_state.py` (offscreen precedent):
set → signal fired, `selected` holds the identity; setting the same
value again fires nothing; `reset_document` clears and fires. Full
`pytest tests/test_app_state.py` green.

### M2.3 — Click gesture + candidate collection

(a) `render/items.py`: `GroupItem.shape()` returns an empty
QPainterPath (§1.2 resolution; one method, commented with the why).
(b) `StageView`: press/release click detection (D1), band gate (§1.9 —
a click outside an active band emits the deselect signal, not a
position), Esc handling (D7); new signals
`clicked(scene_pos: QPointF)` and `deselect_requested()`.
(c) `ui/selection.py` `SelectionController`: on `clicked`, collect
candidates — `scene.items(tolerance_rect)`, walk each hit item's
ancestry to its ElementItem, skip identity-None parents (D5), dedupe by
element id, build `HitCandidate`s from `item.bbox` — call
`policy.pick`, resolve the winning item's `identity`, and
`app_state.set_selection(...)`; a policy None or `deselect_requested`
clears. The controller is bound to the current `ScoreScenes` via
`bind_scenes(scenes | None)` (the `DocumentSync.bind_scenes` pattern);
`MainWindow._install` rebinds it (which also clears selection — §1.11).

**Verify:** new `tests/test_selection.py`, offscreen, on a real
testscore load: `candidates_at` a known notehead position returns the
expected family and `pick` selects the notehead; a click on empty
paper clears; a hidden element (set via `set_element_hidden`) stops
hitting. Interactive: `python -m scoreanim testdata/testscore.musicxml`
— click noteheads/slurs/barlines and watch the status bar (temporary
print is fine until M2.5); drag still pans; wheel still zooms.

### M2.4 — Highlight overlay (live scenes only)

`SelectionController` owns one overlay QGraphicsRectItem (D6): on
`selection_changed`, remove any existing overlay from its scene, and if
something is selected add the overlay at the element's padded bbox to
that element's page scene. Removed on deselect, dropped wholesale on
`bind_scenes` (fresh scenes never contain it). Export purity is
structural (private export ScoreScenes) — pinned anyway.

**Verify:** in `tests/test_selection.py`: after select, exactly one
overlay item exists in the right page scene and it is not in
`scenes.items` (never addressable as an element); after deselect, zero.
Export pin: with a live selection active, a rendered export frame is
byte-identical to the frame with no selection (reuse the
`tests/test_export.py` harness). Interactive: select during playback —
highlight sits on the element while animation runs over it; playback
timing undisturbed.

### M2.5 — Selection panel in the inspector

`ui/selection_panel.py`: QFormLayout readout — Kind, Part (part_name,
falling back to PartId), Staff, Voice, Measure (ordinal via
`measure_ordinal_of`, plus the printed number from `AppState.measures`
when they differ), Onset (beats), Extent (for spanners), and the raw
ElementId in a selectable, dimmed row (the debugging handle). Shows
"Nothing selected" when cleared. Observes `app_state.selection_changed`
only — no scene access, no window access. `Inspector` swaps the
placeholder for it (constructor takes `app_state` it already has).

**Verify:** new `tests/test_selection_panel.py` (offscreen): set a
synthetic ElementIdentity on AppState → row texts match; clear → the
empty state returns. Interactive: click a notehead — the panel shows
kind/part/measure/voice/onset; click a slur — extent appears; click a
barline — measure shown, onset "—".

### M2.6 — Lifecycle sweep

Wire and pin the edges: selection clears on re-engrave (toggle Hide
Empty Staves with a live selection — no stale overlay, panel empties),
on project open, and on new-score load (all via §1.11's two hooks —
verify each path, don't assume); selection SURVIVES page flips and
mode switches per D2 (flip away and back — overlay still there; enter
Systems mode — a selection on another system stays held, its overlay
simply masked); clicks outside the band in system mode deselect
(§1.9); Esc deselects (D7).

**Verify:** offscreen test for the re-engrave clear (execute
`SetHideEmptyStaves` on a loaded window — precedent in
`tests/test_score_loader.py` / window tests); the rest is a scripted
interactive checklist run on bigband1 (hide-empty-staves fixture) —
record it in the session log.

### M2.7 — Exit run + close-out

The roadmap's exit, verbatim, on testscore AND complex3: click a
notehead, a slur, a hairpin, a barline, a part label — each selects,
highlights, and reports correct identity in the inspector (part label:
per D5 an engraved part label is identity-bearing TEXT — it selects;
measure/onset show "—" where minted onset-less); playback continues
undisturbed with a live selection; selection survives page flips (D2,
pinned). Full suite + goldens green. Docs close-out per the
established pattern (§5). Merge `beta/m2-selection`, tag
`v0.2-beta.2`.

**Verify:** `pytest` fully green; the interactive checklist above
performed and noted; ROADMAP M2 marked CLOSED with the rulings
recorded; tag pushed.

## 4. Exit criteria (from ROADMAP.md, restated)

- On testscore and complex3: notehead, slur, hairpin, barline, part
  label — each selects, highlights, and reports correct identity in
  the inspector.
- Playback continues undisturbed with a live selection.
- Selection survives page flips (D2 — survives; pinned in M2.6).
- Hit-priority policy headless-tested (M2.1).
- Full headless suite, goldens, and live oracle green at close.

## 5. Suggested .md changes (during the build, per the usual close-out)

- ROADMAP.md: M2 CLOSED block with the D1–D7 rulings as decided.
- ARCHITECTURE.md §7: selection in the AppState sentence is already
  promised ("document + playhead + selection") — add the as-built
  paragraph: transient ElementIdentity on AppState, view-level click
  gesture, core hit-priority policy, overlay-item highlight, export
  purity. §3: note `GroupItem.shape()` override if it lands.
- CLAUDE.md: package-layout tree gains `core/selection/`,
  `ui/selection.py`, `ui/selection_panel.py`. No rule amendments —
  M2 touches no rules.
- BACKLOG.md: BACKLOG 9 (element-override editing UI) updated —
  selection half done, editing half lands M3. Note the M3 seams
  flagged here: stage-text hit path (D5), selection re-resolve after
  re-engrave (§1.11), `:seg` fan-out decision (roadmap M3).

## 6. Prompts to paste into Claude Code

One session per prompt, /clear between.

### Prompt 1 — build

    Read CLAUDE.md, docs/ARCHITECTURE.md, docs/ROADMAP.md (M2), and
    docs/briefs/M2_SELECTION_BRIEF.md. My rulings on D1–D7 are
    recorded in the brief [amend here if any changed]. Build M2 task
    by task (M2.0 through M2.6) on branch beta/m2-selection: spike
    first and verify the brief's §1 findings rather than trusting
    them, headless tests as you go, every existing fixture's pinned
    behavior unchanged, commit per task, flag-and-stop when reality
    disagrees with the brief.

### Prompt 2 — exit + close-out

    M2 tasks are built and committed on beta/m2-selection. Run the
    M2.7 exit per docs/briefs/M2_SELECTION_BRIEF.md: full pytest
    including goldens and the live oracle; then walk me through the
    interactive checklist (testscore + complex3 + the bigband1
    lifecycle sweep) so I can verify selection behavior myself. Then
    close out the docs per the brief's §5, merge to main, tag
    v0.2-beta.2.
