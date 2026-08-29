# ScoreAnim — Patterns

The idiom book: how this codebase solves problems, distilled from work
that was measured before it was built. When you are about to touch one
of these seams, ride the idiom; deviating from one is a flag-and-stop,
not a judgment call. The full reasoning is in ARCHITECTURE, and the
original measurements are in `docs/history/`. Keep entries short and
plainly worded. When a session makes a mistake a one-line entry here
would have prevented, add the line.

## Idioms

**The prep-seam pass** — engraving-affecting user intent becomes a
rewrite of the canonical MusicXML BEFORE Verovio, never a render-side
patch. `musicxml_prep.prepare()` orchestrates the pass order (reasons
commented); `musicxml_rewrite.py` holds the passes. New intent = a new
pass: sparse delta keyed by stable identity, never stripping encoded
data (`_repaginate` is the one deliberate exception, page attrs only).
Precedent: groups (P8), part texts (P9), condense (P12), breaks (M5/M6),
stem flips (2026-08-03).

**The `_applied_*` diff re-engrave** — `ScoreLoader` caches every
engrave input; `needs_reengrave(doc)` diffs; `_on_document_changed`
routes execute/undo/redo through that one gate. A new engraving input
costs: cache field + diff clause + `load()` parameter + assignment.
Re-engraving commands run via `execute()`, never `preview()` (measured
0.25–1.3 s per re-engrave).

**Fat-apply commands** — one gesture = ONE undo entry (rule 8). A
gesture touching several entries/fields WIDENS an existing command
(`ApplyScoreSetup`, `SetElementStyle.segments`, `SetSystemBreak`,
`SetPageBreak.also_system`); a macro/compound command does not exist and
should not. `describe()`: one entry names itself; several say "change X".

**Pure policy in core** — decisions are data tables + pure functions in
`core/` (adapter `kinds.py`, selection tiers, `core/editing/*`),
headless-tested on synthetic inputs. A branch on a kind or effect NAME
inside an evaluator/applier is the smell (rule 6). Corrections are data
(a tier value, a measured boolean), not new branches.

**A property that reaches only some ink carries its gate on the item** —
core decides who is eligible, the scene or a driver writes the answer
onto `ElementItem`, and the property applier does nothing but obey it.
`scale_pivot`/`scale_cap` (no pivot, no scale) and `can_glow` (no halo,
no glow) are the two; both keep `render/properties.py` a table of
one-line writes with no policy in it. Three separate scope lists exist
now and they are deliberately not one list: `STATIC_KINDS` (a denylist —
does this animate at all), `TINTED_KINDS` (does a part tint reach it)
and `GLOWING_KINDS` (an ALLOWLIST — is this a note). The test of whether
such a list is really the one switch is a scope change costing one
frozenset: widening the glow from head-and-accidental to the whole note
on 2026-08-06 cost that plus two test expectations, nothing else.

**A control's tooltip, and the reason it is dead** — every interactive
control goes through `ui/tips.py`. `describe(widget, text)` writes the
sentence it shows while it is live and parks it on the widget itself;
`describe_action(action, text)` adds the action's own shortcut in the
platform's notation, read off the QAction so it cannot go stale;
`gate(widget, enabled, reason)` replaces `setEnabled` wherever the
reason for graying is not already on screen, and swaps the tooltip for
that reason. `tips.label(text, field)` makes a form label say what its
field says. A live number field goes through `LiveField.set_enabled`,
which keeps the never-gray-a-field-being-typed-in guard in one place.
Reasons that several panels give (no score, no selection, nothing to
undo) are constants in `tips.py`; a reason belonging to one control is
written where the control is. `tests/test_tooltips.py` walks a real
window and fails on a control with nothing to say — so the pass cannot
quietly rot. The box itself is two other files: the three `TIP` tokens
and the `QToolTip` rule give it a light ground and near-black text (the
one surface in the app that runs the other way), and
`ui/tip_placement.py` takes its horizontal placement off Qt — the box
starts at the pointer and runs right, sliding left only far enough to
fit, where Qt would flip it to the other side of the pointer.

**Spike-first, whole-pipeline** — uncertain Verovio/music21 behavior
gets a script in `spikes/` before integration; spikes are kept as
library documentation. Measure through the WHOLE pipeline (monkeypatch
`prepare`/`plan_page_breaks`), not the pass in isolation — M6's spike
caught a silent loss an isolated test could never see.

**Flag-and-stop** — when reality contradicts a doc, a ruling, or a
brief, stop and surface it; never silently deviate or work around.
Applies to code hygiene too (a module about to bloat).

**Goldens discipline** — `tests/goldens/` pins fixture loads
byte-for-byte. Unmodified fixtures stay byte-identical at every commit.
Deliberate movement: `SCOREANIM_UPDATE_GOLDENS=1` re-capture, committed
WITH the change that caused it and a note on why the movement is right.

**Schema bump checklist** — bump `PROJECT_VERSION`, extend
`_READABLE_VERSIONS`, continue the bump comment block, ask the
read-gate question (needed only when a missing key must NOT mean the
default look — v4 was the only one so far; a sparse map whose missing
key means "none" needs no gate). Tests: an old file loads with
unchanged look; a version-restricted reader REFUSES the new file (the
strict-by-version gate is the point of bumping). New-schema test
projects stay separate from alpha's.

**Ordinal keys** — break-shaped intent is keyed by the document ordinal
of the measure that STARTS the new system/page (what `<print>` means);
the UI converts (barline in measure N → target N+1). Ordinals are
adapter ordinals, never printed measure numbers (pickup scores differ).

**Selection context is derived, once** — read
`AppState.selection.measure_ordinal` / the selection's part; never
re-parse the element id at a call site, never infer from geometry
(hidden staves and condensing perturb geometry; the id grammar does not).

**The id grammar** — `P{part}:m{ord}:s{n}:v{n}:{kind}:{seq}` for
part-scoped ink; `score:m{ord}:…` measure-scoped (barlines);
`score:p{page}:…` page-scoped (shifts under repagination — accepted,
rule 7(a)). `:seg{k}` marks spanner continuation segments; the family
(source + segments) is one musical object — fan overrides out via
`core/editing/segments.py`, one undo entry.

**The self-checking join** — when the only way to connect two of
Verovio's outputs is ORDER, pair them in order and then confirm each
pairing against something both sides independently carry (M7: a drawn
part label against the label text its `staffDef` holds —
`core/engraving/verovio/label_parts.py`). Refuse the pairings the
confirmation does not vouch for and warn; downstream then sees a missing
value, which disables an action, instead of a confident wrong one, which
would rename the wrong instrument. Two rules keep it honest: a count
mismatch refuses the whole group, because order means nothing between
sequences of different lengths; and where two orderings are both
plausible, accept only the one the confirmation fully supports. Measure
the ordering before trusting it — M7's first version assumed staff order
and placed 0 of video_test's 7 labels, because a multi-staff part's label
is drawn first.

**Strict vs app path** — `load_detailed(strict=True)` (pytest and
doctor default) raises on unknown SVG classes; the app path degrades to
a warned static element. bigband1 raises strict (`gliss`) — spikes and
tests against it use the app path. Triage for any new export:
`python -m scoreanim.tools.check_score`.

**Warning codes** — load issues are flag-and-continue `LoadWarning`s,
counted in the status bar. "Your override wrote nothing" (stale-inert)
and "the app overruled you to keep the guarantee" (e.g.
`page-break-repaginated`) are DIFFERENT codes — they ask different
things of the user. Inert sets are computed from what a pass actually
wrote, never re-derived elsewhere.

**Docks and shared QActions** — new dock: the `Inspector` template
(`setObjectName` for saveState identity, `NoDockWidgetFeatures`, one
allowed area, `toggleViewAction()` into the View menu; the single
`saveState`/`restoreState` pair covers all docks, no new persistence).
A second surface for an action hosts the SAME QAction object
(`defaultAction`), so label/enabled/status-tip/trigger cannot diverge.

**The split-first commit** — when a module must split (≈400-line
ceiling or two jobs), the split is its OWN commit with no feature code
and byte-identical goldens, BEFORE the feature lands (M3.0, M5.0, M6.0).

**Delete is a hide, never a rewrite** — deleting an element is for
engraving and cosmetic cleanup ONLY. It hides ink through
`LayoutOverride.hidden` (a render-side mask, not an engraving input, so
nothing re-engraves), changes no timing and no other element, and is
always restorable — by undo, or from the layout zone's "Deleted"
readout, which is the only way back once the ink is unclickable. What
may be deleted follows from that sentence: marks ON the music (texts,
slurs, hairpins, dynamics), never the music itself and never scaffold.
The set lives in `core/editing/deletion.py`; adding a kind to it means
arguing the sentence still holds.

**The lane-mode seam** — the timeline lane hosts modes: the host owns
what they share (axis mapping, measure grid, playhead, seek, wheel) and
each mode owns its drawing and its gestures, getting first refusal on
every event and returning False to let the host's click-to-seek have it.
A mode cancels its own preview in `deactivate()` when the user switches
away. Colours and paddings live in `ui/lane_style.py` so a mode never
imports the host back.

**Locks are the anchors, derived once** — what holds still during a grid
drag is the user's locks (`TimingConfig.locked_beats`), never something
inferred from barlines or stray tempo events. The view and the command
both ask `core/timing/retime.lock_anchors`, so the clamp and the result
cannot disagree — which is the only way a lock could end up inside a
span that gets re-spaced. A lock stores only its beat; the second is
derived (rule 5). It anchors tick drags and nothing else: the Offset
field, a tempo-point drag and a `.tempo` import all move locked beats,
and the last of those clears the locks outright.

**A number field previews as you type** — the DEFAULT for every spinbox
that edits the document (Marcus, 2026-07-31). The user has to look at
the result to know whether the number is right, so the result has to be
on screen while they are still typing it. `ui/live_field.py` owns the
wiring: keyboard tracking on, `valueChanged` → `preview`,
`editingFinished` → `commit`, so the whole typing session is ONE undo
entry, and Qt withholds `valueChanged` for text that does not validate
in range, so a half-typed number never previews. Each field supplies one
`edit(value) -> Command | None`, used by BOTH the preview and the
commit, so the two cannot ask for different things. The host keeps its
fields in a `live_fields` tuple — that is what holds them alive, and
`tests/test_live_field.py` scans it, so a spinbox added without one
fails the suite.

Four things this costs, all load-bearing and all handled by the helper:
the no-op guard reads `AppState.committed`, because `doc` hands the
field back its own preview and it would then never commit; the resync
skips its `setValue` while the edit is live, because `preview` emits
`document_changed` and comes straight back to rewrite the text under the
cursor (`blockSignals` stops a re-commit, not that); "am I previewing"
is `live AND doc is not committed`, so an undo or a project load takes
the field back instead of leaving it on a number nothing is showing; and
a resync must never DISABLE a live field, because disabling drops focus
and focus-out commits. One field is live at a time — reaching another
spinbox moves focus, and focus-out ends the first edit. A shortcut does
not move focus, so Cmd-S writes `committed`, and an undo mid-edit takes
the unfinished edit with it.

**A drag on a canvas is that same contract with a mouse**
(`ui/envelope_editor.py`, 2026-08-04). Press, then every mouse-move
previews and the release commits ONE undo entry — same reasons, same
four costs, same one `edit()` behind both halves. Two things a canvas
adds. It is the widget that has to refuse a resync mid-gesture (a
picture cannot be "focused", so nothing else stops the preview coming
back and redrawing under the hand). And a handle CLAMPS LIVE against
its neighbours, so what the user sees stop is what the document gets:
the pure half (`core/editing/envelope_drag.py`) runs every result
through the same clamp the consumer uses, which makes an illegal value
unreachable rather than corrected afterwards.

Three exclusions, and only three. An engraving input never previews —
anything `ScoreLoader.needs_reengrave` diffs runs through `execute()`
only (0.25–1.3 s per re-engrave). A modal dialog's fields never preview:
the dialog owns its own OK/Cancel, and a preview would outlive a Cancel.
And checkboxes and combos are not in scope — they have no half-typed
state, so they already commit atomically.

**A duration change must not steal the window** — with no audio bound
the time axis's duration is the SCORE's length, so every tempo edit
changes it, including each preview frame of a drag. `TimeAxis` re-fits
only when the window is showing everything AND no gesture holds it;
`AppState.preview` takes the hold and `execute`/`cancel_preview` release
it, so no view has to remember. Both halves are needed — keeping a
zoomed window alone still yanks the common case (no audio, fully zoomed
out) on every mouse-move.

**Two beat domains at the tick seam** — a grid tick is a MUSICAL beat; a
tempo event's `position` is a SWING-WARPED beat (`seconds_at` consumes
warped beats). Locks are musical too. Anything crossing between them converts:
ticks and locks warp on the way to a pixel, event positions unwarp
(`swing_unwarp`) on the way to being compared with them. Get this wrong and everything looks right at
ratio 0.5 and drifts the moment swing is on.

**A per-frame reading stays a pure function of t** — anything the
applier looks up every frame (the recording's live loudness,
`intensity_at`) takes `(cache, t)` and nothing else, or `apply_at`
walking to a time and `refresh` jumping there stop agreeing. What is
expensive but constant — the peak reference, a percentile over every
bin — is worked out on the seams that can move it (`set_audio`,
`set_style`, `set_timing`) and handed in as an optional argument that
never changes the answer. Pin it with a scrub-equivalence test AND the
export/live parity test; the two catch different mistakes.

**A knob another knob forces on** — when core decides a flag regardless
of what the document says (follow forces swell's note value), the panel
says so rather than staying silent: `Check.forced_by` makes
`KnobGroup.param` read True, so the box shows checked and grayed and
everything downstream of it (the duration that grays out) follows for
free. The document is never written to — core stays the one authority.

**One theme, one place for a colour** — `ui/theme/palette.py` names
every colour the chrome uses; `ui/theme/theme.py` turns them into the
Fusion style, a QPalette and one app-wide QSS string, applied once in
`app.py` before any window exists. A widget never sets a colour on
itself: a painting view (waveform, lanes, stage letterbox) imports the
token, and anything QSS can reach is styled by class or by object name
(`SectionHeader`, `ZoneHeading`). A new colour = a new name in
`palette.py`. The one exception is a colour the DOCUMENT owns — page
ink, a part colour, a style swatch — which comes from the document, not
from the theme.

**One icon, every state it needs** — `ui/theme/icons.py` vendors Lucide
SVGs and returns a QIcon that already carries all three looks: text
colour off, accent on (a checked action), dim disabled. Tinting works
because a Lucide file paints itself in `currentColor`, which we swap for
a token before Qt sees the file — so a caller never picks a colour and
nobody ships a second file for a second state. The QIcon holds a pixmap
rendered at each size the app asks for at 1x AND 2x (`TOOLBAR_SIZE`,
`BUTTON_SIZE`), because a stroke drawing goes soft the moment Qt
resamples it. Give the ICON to the shared QAction, not to the button:
the menu item and every button then pick it up, and a flip (play →
pause) is one `setIcon` on the action. An icon-only button has no label,
so the tooltip carries the name — and for an action that renames itself
(the break toggles) the tooltip follows the rename for free, as long as
nothing calls `setToolTip` on it.

**Two hit paths, on purpose** — selection resolves rule-13 OBJECTS;
double-click-to-edit has its own resolver that also reaches stage
texts. Stage texts are editable but never selectable (they carry no
measure/part). Do not merge the paths.

## Traps (each of these has already cost a debugging session)

- **The applier's pre-roll time is `-inf`.** `AnimationApplier._t`
  starts at `float("-inf")` and `set_audio`/`set_style`/`set_timing` all
  call `refresh(self._t)`, so anything reading the clock inside the
  apply path sees it before it ever sees a real second. Test `t < 0`
  FIRST, before any arithmetic — `int(-inf * bins_per_sec)` raises.
- **All prepare() calls carry all intent.** `load_detailed` re-prepares
  on the repagination and scale-to-fit retries; every intent map must be
  threaded through every call, pinned by test — a map dropped from one
  retry silently loses user edits exactly when the score is hardest.
- **Two passes racing on one XML element** produce arbitrary precedence
  and false inert warnings. One combined pass that visits each element
  once, with precedence stated in code (`_apply_breaks`).
- **music21 inter-measure accounting is never trusted** (rule 12): it
  pads pickups, ignores repeats, rounds half-beat bars, self-diverges
  between parts. Everything rebases onto the engraved timemap.
- **Cached inverse transforms go stale when items move** —
  `RevealPathItem` caches scene→local; invalidate on `setPos` or the
  reveal edge is off by exactly dx. The glow sprite caches the same
  thing for the same reason (2026-08-06), so an element's children are
  now plural: anything that adds a THIRD child kind to `ElementItem`
  has to take the reveal edge too, or its ink stands ahead of the
  playhead.
- **A clip is clamped to the clipped item's own bounds**, so two
  children cut at one scene x can report different local edges — the
  halo's box is the ink's plus the blur margin, so it keeps the true
  edge where the narrower path has already clamped to its left side.
  Compare clips in SCENE coordinates or the two look like a bug.
- **Vacuous pins**: a test sampling state that cannot change passes
  forever (M2.7's "playback undisturbed" sampled a downbeat notehead).
  Guard non-vacuity: pick samples that MUST differ, fail if they don't.
- **"No-op at baseline" must be probed in the configurations the
  goldens pin** — BACKLOG 16's fix was measured a no-op on four default
  loads and still moved two goldens (hidden/flat variants repaginate).
- **Zero-area authored rects exist** (a stem's Rect has w = 0), so any
  area/size heuristic needs an exactness tier first.
- **Dorico exports the WRITTEN score's stem directions** while we
  engrave concert pitch (rule 9). Transposing moves notes across the
  middle line and `<stem>` does not follow, so 6.5-34.3 % of unbeamed
  single-voice stems arrived on the wrong side — about seven times
  denser in transposing parts. `_normalize_stem_directions` drops the
  element and lets Verovio decide. Expect the same class of bug from any
  other engraving attribute Dorico writes as an absolute.
- **A note event's index is not its notehead's index.** A chord is one
  event sharing one stem, and a whole note draws no stem at all — so a
  stemless event must consume no `seq` or every key past it points one
  note too far. `spikes/stem_dirs.py` measures the correspondence
  (991/991 scopes).
- **Changing what is drawn can move `scaled-to-fit`.** Stem directions
  change a system's height, which changed the fitted scale by one per
  cent on two fixtures and moved 100 % of their golden rows. A one-line
  visual change is not a small golden diff.
- **Dorico encodes page breaks page-only**: `new-page="yes"` with no
  `new-system`. new-page IMPLIES a system break — clearing or stripping
  it destroys the system break too unless promoted/asserted.
- **`QMainWindow.saveState` covers docks, not inner splitters** — lane
  splitters need their own persistence if wanted.
- **An untimed `showMessage` buries the status bar's own widgets.** A
  temporary message hides every non-permanent widget on the bar and
  shows them again when it expires — so a message with no timeout never
  expires, and the hint bar (D3) never comes back. Every status message
  goes through `HintBar.message`, which supplies the timeout;
  `tests/test_hint_bar.py` pins that nobody adds a bare call back. The
  swap is also invisible on a window that was never shown: Qt only
  hides a widget it can see, so a test of it has to `show()` first.
- **A widget parented to a scrolling viewport rides the scroll.**
  `QGraphicsView.scrollContentsBy` calls `viewport()->scroll(dx, dy)`,
  and `QWidget::scroll` moves that widget's CHILDREN along with the
  pixels — so floating stage chrome parented there slides off the
  screen the first time the user two-finger scrolls (D2, found in the
  app). It goes on the VIEW instead, beside the viewport, placed
  against `viewport().geometry()` and raised. Watch the viewport's own
  Enter/Leave/Resize with an event filter from there — and note the
  viewport's Leave and the view's are different moments: chrome lying
  over the viewport takes the pointer off IT while the view still has
  it.
- **A stage key must not become a window shortcut** if another widget
  already handles that key. Qt matches shortcuts BEFORE the key reaches
  the focused widget, so a window-level Delete silently eats the tempo
  lane's point deletion. Stage keys use
  `WidgetWithChildrenShortcut` + `view.addAction(...)` (Delete), or the
  view's own `keyPressEvent` (Esc, arrows) — never `window.addAction`.
- **Break edits legitimately change element sets**: system-start
  restatement furniture (clef/key per part) and courtesy signatures
  appear/vanish; `ledger_lines` seq ids re-use across re-layout (id
  re-use, not retiming). Don't read these diffs as regressions —
  `score_end` and the trigger count are the invariants that must hold.
- **Selection clears on `bind_scenes`** unless re-resolved; measure- and
  part-scoped ids survive break edits, so restore via
  `scenes.items.get(eid)` (M5's D9 machinery) rather than re-clicking.
- **git via the Cowork device bridge leaves stale `.git/index.lock`**
  (it cannot unlink); if a commit is blocked, remove the lock in a
  native terminal.
- **A `QScrollArea` with `widgetResizable` squeezes its content past
  the content's own minimum**, and Qt then cuts the text inside — with
  the horizontal bar switched off there is not even a way to scroll to
  what was cut. A widget's minimum stops the layout AROUND it, not the
  scroll area that owns it. Hand the minimum back up:
  `panel_style.lock_min_width(scroller, body)`, called once the dock's
  body is built.
- **A panel that hides rows must measure itself while it is whole.** A
  preset's block of options hides when nothing is using it, so a
  minimum width taken after the first resync is the minimum of whatever
  happens to be showing. `EffectsPanel` takes its width before the
  first `sync_from_document`, when every row is still on screen.
