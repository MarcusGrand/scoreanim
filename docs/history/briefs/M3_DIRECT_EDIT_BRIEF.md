# M3 — Direct edit: build brief

Scope authority is `docs/ROADMAP.md` §M3. This file is how it gets
built. Written after the audit and the two spikes, before any feature
code.

Status: **built M3.0–M3.4, 2026-07-27.** All four decisions in §4 were
ruled by Marcus as recommended; §6 records what was built and the one
thing that could not be. Suite 858 passed / 1 xfailed, goldens
byte-identical.

---

## 0. Baseline

- `beta/m3-direct-edit`, branched off `main` at the M2 merge (8e06f7d,
  tagged `v0.2-beta.2` covering M4 + M2).
- Suite at branch point: **773 passed, 1 xfailed**.
- After M3.0: **787 passed, 1 xfailed**; goldens byte-identical.

## 1. M3.0 — BACKLOG 9b, paid (commit 0030616)

`ui/main_window.py` 399 → **312** lines. Two seams, both the ones 9b
named:

- **`ui/view_router.py`** — presentation routing. The window held the
  position state (`_page`, `_system`, `_band_by_system`, `_applied_mode`)
  and six methods over it. Bound per load via `bind()`, the
  `DocumentSync`/`SelectionController` idiom. `MainMenus` grew
  `set_position(text, can_prev, can_next)` so the router never reaches
  for the three readout widgets the chrome owns.
- **`ui/parts_menu.py`** — the three part-shaped dialogs. Score Setup,
  Staff Groups and Part Names were window methods guarding on a
  window-held `_parts` tuple, reached through three `Callable`s passed
  down from the window's constructor. `rebuild()` is already called with
  the parts on every load, so the data and its dialogs now live
  together; the window holds neither.

**The fourth opener stayed put, and 9b's own criterion is why.** 9b says
"into the components that own their data". `open_texts_dialog`'s data is
the *current engraved layout* (`animation_inputs.layout` → `page_content_top`
for the band, plus the `text_class == "tempo"` elements). No component
owned that at M3.0; the window did. M3.1 gave it one — `ui/text_edit.py`
holds the layout for in-place editing, so the dialog moved there and 9b
is fully paid.

New coverage: `tests/test_view_router.py`, 12 stub-based tests
(clamping, mode dispatch, follow gating, page-coherence in system mode,
clear-band-before-show ordering). The routing had no direct tests while
it was window methods.

## 2. What already exists (audit)

Feature 1 routes into commands that all exist: `SetPartText` (part
labels, prep-seam re-engrave), `AddTempoOverlay` / `RemoveTempoOverlay`
(hide the engraved TEXT + add a replacement stage text, one undo step),
`EditStageText` (title/composer/lyricist and any existing overlay).

Feature 3 routes into `SetElementStyle(element_id, ElementStyle | None)`
— already sparse-doc correct (an empty style pops the entry), already
serialized, already applied by `apply_style_colors` (fresh scenes) and
`DocumentSync.sync_styles` (live diff). "Clear overrides on selection"
is `SetElementStyle(eid, None)`.

Feature 2 has **no** command. `LayoutOverride.dx/dy` are schema slots
carrying the comment "no editing UI yet"; the only consumer of the
dataclass is `.hidden`, via `apply_hidden_overrides` (export) and
`DocumentSync.sync_hidden` (live), and `apply_hidden_overrides`'
docstring says so verbatim: "Consumes ONLY .hidden — dx/dy remain
unconsumed schema slots." So `SetLayoutOverride` is a **new command
class**. The roadmap's M3 section names it explicitly, so it is
sanctioned by the spec rather than invented here — but it is new, and
that is stated rather than glossed.

## 3. Measurements

### 3.1 The reveal-clip spike (`spikes/nudge_reveal.py`)

The roadmap required this before building nudge. The mechanism is in
`RevealPathItem.set_clip_right`, which takes a **scene** x (the reveal
edge) and maps it into the path child's local coordinates through the
inverse of its scene transform — **cached on first use**. Moving the
parent `ElementItem` with `setPos` changes that transform.

On `testscore`, slur `P1:m1:s1:v1:slur:0` (w = 53.1), edge pushed to the
element's midpoint:

| case | clip lands at scene x | error |
|---|---|---|
| unmoved | 609.17 | +0.00 |
| nudged (+30, −12), stale cache | 639.17 | **+30.00** |
| same, cache invalidated first | 611.10 | +1.93 (clamped, see below) |

**The error is exactly dx.** The spanner reveals as if the playhead were
dx further right than it is.

With the cache invalidated, the local clip moves by exactly −dx and is
completely y-independent:

| nudge | local clip moves | want |
|---|---|---|
| (+10, 0) | −100.0000 | −dx/scale = −100 |
| (−10, 0) | +100.0000 | +100 |
| (0, +20) | 0.0000 | 0 |
| (0, −20) | 0.0000 | 0 |

(child transform is a pure uniform 0.1 scale — m12 = m21 = 0. The +1.93
residual in the table above is the clip clamping to the path's own left
edge at that displacement, i.e. "fully hidden", not a coordinate error.)

Revealed fraction with a correct inverse: home 0.494 → **0.230** nudged
+15 in x, **0.758** nudged −15 in x, **0.494** nudged −20 in y.

Two consequences:

- **`HAIRPIN` is in `REVEALED_KINDS`** (with `SLUR` and `TIE`).
  Excluding `REVEALED_KINDS` from `NUDGEABLE_KINDS` would delete the
  roadmap's own primary target *and* its exit criterion ("drag a hairpin
  20px up and export").
- **A pure-y nudge is unaffected even with the bug** (0.494 → 0.494),
  and the exit criterion is y-only. So the exit criterion would pass
  either way; the x case is what is actually at stake.

Nothing in the app moves items today, so the cache is correct as
shipped. This is a latent constraint nudging would trip, not an existing
defect.

### 3.2 The `:seg` grammar (`spikes/seg_fanout.py`)

Segments are minted in one second pass as
`f"{source.element_id}:seg{acc.seg_index}"` with
`identity = replace(source, element_id=...)` — everything but the id is
inherited. Sources are restricted to `_SPANNER_CLASSES` (the FINDING-5
fix; before it, stems minted `:seg1` ids). `_ID_TAG` is
`{k: k.name.lower() for k in ElementKind}` and there is no `SEG` kind, so
a base id ends `:<kindtag>:<digits>` and a `:seg<digits>` suffix can only
come from the continuation pass.

Four invariants, audited on every fixture that loads:

| fixture | elements | broken spanners | segments | nested | orphan | identity mismatch |
|---|---|---|---|---|---|---|
| testscore | 1686 | 7 | 7 | 0 | 0 | 0 |
| video_test | 4635 | 45 | 49 | 0 | 0 | 0 |
| complex1 | 3491 | 8 | 8 | 0 | 0 | 0 |
| complex3 | 20312 | 56 | 56 | 0 | 0 | 0 |

Source kinds are only ever `TIE`, `SLUR`, `HAIRPIN`. Families are almost
always 2 (source + `:seg1`); `video_test` has four 3-member families —
e.g. `P1:m34:s1:v0:hairpin:0` + `:seg1` + `:seg2`, a hairpin crossing
three systems.

(`bigband1` does not load under the spike's strict path — `unknown SVG
class 'gliss'`. That is the Phase 11 strict/app-path split, not a
fan-out finding; the app path would degrade it to a warned OTHER.)

**Conclusion: the family key is sound.** Strip one trailing
`:seg<digits>` to get the source; members are the source plus every id
matching `^<source>:seg\d+$`. This confirms the roadmap's
recommendation on the grammar — the remaining question in §4.3 is a
product question, not a feasibility one.

### 3.3 Stage texts and D5

`ScoreScenes._add_stage_texts` builds them as `ElementItem(identity=None)`
and registers them in `scenes.items` under `ElementId(text.element_id)`.
`SelectionController.candidates_at` skips `item.identity is None` — that
is D5, one line.

Stage texts are **both** the header block (title/composer/lyricist) and
every tempo overlay (`stage:overlay:<engraved id>`). So under D5 as it
stands, two of feature 1's four routes are dead ends: you could never
re-edit a title, and you could never re-edit a tempo overlay you had
just created, because in both cases the thing on screen is a stage text.

## 4. Decisions — proposed, then ruled

All four were ruled as recommended (Marcus, 2026-07-27). Kept in their
original form below, because the argument for each is the record of why
the ruling went the way it did.

### 4.1 Double-click and D5 (stop-and-ask)

**Proposal: D5 stands; double-click gets its own hit path.**

D5 governs SELECTION. Under rule 13 selection is object-first and
carries a measure and a part by derivation — a stage text has no part,
no measure and no onset, so it is not a selectable *object* in rule 13's
sense, and making it one would put something in `AppState.selection`
that the Selection panel cannot describe.

Double-click-to-edit asks a different question — "which editable text is
under the cursor" — and can have its own resolver over both engraved
TEXT elements and stage texts without either becoming a selection. The
gestures already differ at the view (`StageView` distinguishes press and
release; a double-click is a distinct event).

This needs one small mechanical addition: `scenes.items` is
`dict[ElementId, ElementItem]` with no reverse lookup, so the resolver
needs an item→id map (or the id stored on the item).

If instead you want stage texts genuinely selectable, that overturns D5
and I stop.

### 4.2 `NUDGEABLE_KINDS` and the reveal clip (stop-and-ask)

**Proposed set: `{DYNAMIC, HAIRPIN, TEXT}`** — exactly the roadmap's
three named targets.

Left out, and why: `NOTEHEAD`/`STEM`/`FLAG`/`BEAM`/`ACCIDENTAL`/
`LEDGER_LINES` are separate elements with separate ids, so nudging one
tears a note apart — compound-object dragging is not M3's problem.
`SLUR`/`TIE` are anchored to notes at both ends, so moving one
desynchronizes it from the notes it belongs to (and `TIE` is 66 of
testscore's 73 revealed elements — high blast radius, low value).
`STAFF_LINES`/`BARLINE`/`GROUP_SYMBOL`/`SYSTEM_DIVIDER` are scaffold,
and the barline is M5's handle. `CLEF`/`KEY_SIG`/`METER_SIG` are placed
by the engraver. `REST`/`MREST`/`SLASH`/`BAR_REPEAT` and
`LYRIC`/`CHORD_SYMBOL` are plausible later additions, deliberately not
v1.

The spike says the reveal clip does **not** make this unsafe — it
locates a one-line cache staleness and shows that invalidating the
inverse makes the clip exactly correct (−dx, y-independent). So the
options are:

- **(a) Fix the cache** — invalidate `_inverse` when the item moves —
  and keep `HAIRPIN`. Measured correct. The cache stays valid for every
  non-moved element, which is all of them today.
- **(b) Exclude `REVEALED_KINDS`** as the roadmap's fallback says. This
  drops `HAIRPIN`, leaving `{DYNAMIC, TEXT}`, and contradicts the M3
  exit criterion.

I recommend (a), and flag that it is an edit to `render/items.py` on the
applier's hot path, which (b) would avoid.

### 4.3 The `:seg` fan-out

**Proposal: fan out, per the roadmap's recommendation** — §3.2 shows the
family key is well-defined and the segments are the same musical object
(identity differs only in the id). Pinned by test either way.

The counter-argument, stated fairly: the panel already labels a segment
"Slur (segment 1)", so nothing on screen implies the whole spanner was
picked, and fanning out means one click writes N document entries where
the user pointed at one. Mitigation is that they undo as one command.

### 4.4 M4's F5 — per-part effect rules (flag, not absorb)

F5 left per-part effect rules honored and round-tripped but
**unauthorable**, waiting on this panel. `SetPartEffect` exists, and
under rule 13 the selection already carries its part — so the Selection
panel's effect control could offer an element/part scope switch and
close F5 for roughly the cost of a radio pair.

Flagging rather than absorbing, as instructed. It is in scope only if
you say so.

## 5. As built

All four §4 proposals were ruled as recommended (Marcus, 2026-07-27).
Multi-select stayed out: neither restyle nor nudge needed it, so no
case was made.

**M3.1 — text edit in place.** Three routes of four. Stage texts,
tempo overlays, and other engraved TEXT all work; "the tempo-overlay
mechanism generalized" cost nothing, because `AddTempoOverlay` never
looked at `text_class` and `seed_overlay_text` reads only
`glyph.texts[0]`, which every engraved TEXT has. Pinned on `dir` and
`reh` as well as `tempo`. Page furniture (`mNum`, `pgHead`, `pgFoot`)
is deliberately not editable in v1. `open_texts_dialog` moved here,
closing 9b's fourth seam.

**The part-label route could not be built** — see §6. This is the one
M3 exit criterion left unmet.

**M3.2 — drag-to-nudge.** `SetLayoutOverride`, absolute deltas, one
command per gesture (pinned with twenty mouse-moves that leave the
document untouched while the item visibly moves). `apply_hidden_
overrides` → `apply_overrides`; export parity pinned by rendering real
frames and comparing digests, including that clearing restores the
original bytes. The reveal-clip cache is invalidated and the last edge
re-pushed on move, pinned in local clip coordinates with a non-vacuity
guard that leaves the cache stale and requires the clip NOT to track.

**M3.3 — style from the selection.** Colour + effect + clear, element or
part scope (closing F5), `:seg` fan-out as one undo entry via
`SetElementStyle.segments`. Rule 13 pinned from M3's side: colouring an
element the selection's own orange leaves it visibly selected through
`SELECTION_ALT_COLOR`, and deselecting re-derives the plain authored
colour. "Clear style overrides" is style-only and says so — folding the
nudge in would cost a second undo entry or a command that does not
exist (BACKLOG 15).

## 6. What reality contradicted

One thing, and it is the reason feature 1 ships three routes rather than
four.

**A part label carries no part.** The roadmap routes a part label to the
part-name override path; `SetPartText` is keyed by `PartId`. Measured:
Verovio emits labels as direct children of `<g class="system">` with no
staff or part ancestor, so the adapter mints them
`score:p<PAGE>:text:<n>` with `part=None` — and `tests/goldens/` pins
that null (`"part": null` on every label element).

The UI cannot recover the part on its own. Geometry (match the label's y
to a staff) and ordinal position (labels in vertical order = parts in
score order) were both rejected: hidden staves and condensing perturb
both, and rule 13's whole point is that context comes from the id
grammar rather than from position. The right fix is attribution in the
adapter — plausibly through the MEI index, since the label's xml:id
should reach a `staffDef` — which is an adapter change that MOVES
GOLDENS, so it is outside a milestone whose charter is "UI affordances,
not new document semantics".

Carried as BACKLOG 14. The routing policy IS written and unit-tested,
and the end-to-end test asserts the current limitation in a form that
fails the moment labels gain a part.

## 7. The plan these were built to (kept for the record)

1. **M3.1** — text edit in place: the `QLineEdit` overlay + the text
   resolver (§4.1), routing to the four existing command paths. This is
   where `open_texts_dialog` gets its owning component (§1).
2. **M3.2** — `SetLayoutOverride` + the drag gesture (one command per
   gesture, arrow keys 1 unit / Shift coarse) + `apply_hidden_overrides`
   → `apply_overrides` and the live diff, pinned by an exported frame vs
   the stage after a nudge.
3. **M3.3** — Selection panel style controls: color, effect, clear
   overrides; the `:seg` fan-out per §4.3.
4. **M3.4** — docs: M3 rulings into ROADMAP, BACKLOG 9/9b closed or
   reduced to what remains, the drag/override and export-parity seams
   into ARCHITECTURE, M5 inheritance noted.

Invariants throughout: rule 8 (one undo entry per gesture), rule 5
(deltas are intent, engraved positions are not), rule 13 (M3 writes the
authored channel only — never a second writer for the transient tint),
no monoliths, goldens byte-identical.
