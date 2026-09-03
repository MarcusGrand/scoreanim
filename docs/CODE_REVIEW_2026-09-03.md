# ScoreAnim — Code Review (2026-09-03)

Read-only review of the whole app: 218 modules, ~36k lines under
`scoreanim/`, plus the docs. Nothing was changed. Every finding below
was checked against the code, and the performance claims were measured
by loading the real fixtures headless (cloud Linux box, verovio 10.5 —
slower than your Mac, so treat times as relative, not absolute).

The short version: the architecture is sound and the rules in
CLAUDE.md are actually followed. Large scores do load — complex2 and
complex3 both PASS the score doctor. What makes them painful is (a) the
never-clip retry loop, which throws away two of every three engraves,
and (b) a per-edit retiming pass that costs a third of a second on
complex2. There are also nine confirmed bugs, one of which is a latent
crash on any score with a slash region.

---

## 1. How the app works

### 1.1 The layers

```
MusicXML (Dorico)
  │
  ├─ core/score/musicxml_prep.py   prepare(): parse once, run the rewrite
  │      passes, return a frozen PreparedScore (canonical XML string)
  │
  ├─ core/engraving/verovio/       Verovio engraves → SVG per page →
  │      decompose into RenderedElements with our own ElementId
  │      + MeasureTimeline (the ONE beat axis, rule 12)
  │
  ├─ core/score/model.py           music21 parses the same XML → ScoreModel;
  │      join.py pairs model notes with adapter note records
  │
  ├─ core/animation/schedule.py    every animated element gets one beat →
  │      TriggerSchedule (sorted rows of element ids per beat)
  │      reveal.py / glow_scope.py / windows.py derive the rest
  │
  ├─ render/scene.py               Layout → one QGraphicsScene per page,
  │      one ElementItem per element, one path/text item per primitive
  │
  ├─ render/animate.py             AnimationApplier.apply_at(t): bisect
  │      the trigger seconds, evaluate state(t) per item, write properties
  │
  └─ ui/                           MainWindow is the composition root;
         AppState holds the document + undo stack; PlaybackController
         owns the clock and the 16 ms tick; everything else observes
```

The currency between layers is `ElementId` (minted by the adapter,
never a Verovio id) and `Beats` on the engraved timeline. Rule 1 holds:
a grep for Qt under `core/` returns nothing.

### 1.2 Loading a score (the expensive part)

`VerovioEngravingProvider.load_detailed()` (`provider.py:103`) is the
entry. One engrave (`_engrave_prepared`, `provider.py:394`) does:

1. Re-parse the canonical XML twice more: `region_fill` puts invisible
   fill notes in slash/repeat bars, `system_hides` strips per-system
   staff hides. Each is a full parse + serialise.
2. `tk.loadData()`. Under hide-empty-staves (the default) it exports
   MEI, sets `scoreDef@optimize`, and loads a **second** toolkit.
3. `tk.getMEI()` again for `_MeiIndex`, and twice more for
   `_container_ns` — up to four MEI exports per engrave.
4. `renderToTimemap` → onset/offset per id, measure starts.
5. Per page: `renderToSVG` → `_PageDecomposer` walks the `<g>` tree and
   builds one accumulator per element with path/text primitives.
6. Post-passes in a fixed order: reclaim spanner ink → rehome strays →
   ledger dashes → spanner segments → implausible ties → part labels.
   The order is a correctness invariant that only a comment enforces.
7. `identity._build_elements` mints ids from
   `(part, measure, staff, voice, kind, seq)` and resolves onsets.
8. Synthesis adds slash and `%` elements.

Then `load_detailed` checks whether any system band overflows its
page. If yes: re-`prepare()` from disk with new page breaks and
**engrave again**. If a single system is still too tall: re-`prepare()`
again and **engrave a third time** at a smaller scale. Both big
fixtures take all three passes.

After that, `ScoreLoader.load` (`ui/score_loader.py`) builds the
scenes, the music21 model, the join, durations, schedule, reveal
tracks, glow scope and the applier. All of it runs synchronously on
the GUI thread.

### 1.3 Time and animation

There is no accumulated time anywhere. `Clock.now_seconds()` is the
only interface; `AudioClock` reads `QMediaPlayer` position with
anchors, `WallClock` is anchors over wall time, `FrameClock` is
`n / fps`. The 16 ms `QTimer` in `PlaybackController` only *triggers*
a read; it never adds to anything. Rules 2 and 3 hold.

Per frame, `apply_at(t)` bisects into `_trigger_seconds`, applies rows
crossed since the last frame, re-applies rows whose windows still
contain `t`, then runs the reveal and pulse drivers. The kernel is one
function, `element_state(trigger, effect, t, timescale)`, and effects
are pure data (`Effect(name, tracks, ...)`) composed by a table of
per-property ops. No evaluator branches on an effect name. Rule 6
holds.

Beats become seconds through one seam: `swing_warp` then
`TempoMap.seconds_at` (bisect + lerp over a prefix sum).

### 1.4 The document

`ProjectDoc` is one frozen dataclass of intent: file refs with hashes,
engraving params, dx/dy overrides keyed by `ElementId`, timing (offset,
tempo events, swing, taps, locked beats), style rules, stage config,
groups, break maps, stem flips, trigger overrides. No geometry, no
timemap. `serialize.py` has one tolerant reader for versions 1–12
(every field `.get()` with a default) rather than a migration chain.
Commands are `apply(doc) -> doc`; `UndoStack` stores before/after
snapshots and never re-runs `apply`. Rule 5 and rule 8 hold, with two
exceptions noted below.

### 1.5 What is good

Worth saying, because the rest of this document is about problems.
The provider/clock/envelope seams are real and respected. The pure
editing policies (`core/editing/*`) return an `Action` with a `reason`
when disabled, and the UI just displays it — that is exactly how to
keep Qt out of the logic. `golden.py` and the `check_score` doctor are
the right tools. `LiveField`'s preview-then-commit discipline is
applied consistently. Comments explain *why*, with dates.

---

## 2. What the numbers say

Measured with `check_score` and a headless `ScoreLoader.load`, then a
simulated 60 fps sweep of `apply_at`.

| fixture  | elements | pages | load  | engraves | `set_timing` per edit | `apply_at` per frame (median / p95) |
|----------|---------:|------:|------:|---------:|----------------------:|------------------------------------:|
| testscore|    1 687 |     3 |  1.5 s|        1 |            —          | —                                   |
| bigband1 |    4 595 |     3 |  2.3 s|        1 |            —          | —                                   |
| complex3 |   20 291 |    21 | 26 s  |        3 | 150 ms + 77 ms refresh| 0.14 ms / 0.29 ms                   |
| complex2 |   42 764 |    20 | 69 s  |        3 | 317 ms + 151 ms refresh| 0.26 ms / 0.51 ms                  |

Profile of complex3's 30 s load: `_engrave_prepared` ×3 = 26.5 s, so
**two thirds of the load is thrown away**. Inside one engrave, the
Python SVG walk (`decompose._walk`) is the biggest single cost (~3 s
per pass), then XML parsing (79 parses, 5.8 s total), then Verovio's
own `renderToSVG` (3.2 s for 63 pages), `loadData` and
`renderToTimemap`. `prepare()` runs four times from disk (3.8 s).
music21 is 5.4 s and runs once — it is not the bottleneck people
usually assume.

Two conclusions. Playback is not the problem: the Python side of a
frame is well under a millisecond even on complex2 (the Qt paint side
is not in these numbers, see §3.3). Editing is: every document change
— a colour tint, a keystroke in a live field, each preview frame of a
drag — costs ~470 ms on complex2, because `set_timing` re-resolves
every trigger and then `set_timing_config` runs a second full
`refresh`.

---

## 3. Findings

### 3.1 Confirmed bugs

**B1. Latent crash in `resolve_durations`** —
`core/animation/durations.py:118`. `span` is bound at line 74 as a
`dict[ElementId, Beats]`; inside the element loop, the SLASH/BAR_REPEAT
branch rebinds it: `span = span_by_ordinal.get(...)`, a float. The
next NOTEHEAD hits `span.get(head, ...)` on a float → `AttributeError`.
It has never fired only because synthesis appends slashes after every
notehead in `layout.elements`. Any future sort of the element list, or
an adapter change, turns it into a load crash on every slash-region
score. One-line fix (rename the local), plus a test with a slash
before a notehead.

**B2. Opening a project engraves twice** — `ui/score_install.py:42–52`.
`load_score` reads `system_break_overrides`, `page_break_overrides`,
`stem_directions`, `trigger_overrides` and `tied_notes_as_one` from
`w.app_state.doc` — the **previous** document, because
`reset_document` runs after. The loader caches those stale values;
`_on_document_changed` then finds `needs_reengrave(doc)` true and
engraves again. The comment in `file_actions.py:180` says "no double
engrave"; that is true only for a project with no overrides. Same
path in `open_score`: the old score's breaks are fed into the new load,
and old trigger overrides produce a bogus `trigger-override-inert`
warning.

**B3. Undo can drop the audio binding** — `ui/app_state.py:193` and
`core/project/commands/undo.py:44`. `bind_audio` replaces `doc.audio`
outside the stack (a documented ruling). But `UndoStack.undo` returns
a whole-document snapshot. Execute any command, bind audio, undo: the
document now has the pre-bind `audio`. Save writes a project without
its recording.

**B4. Old audio survives a new score** — `ui/audio.py`.
`AudioTransport` has no `unload`; `open_score` never clears it. After
opening a second score, the document says `audio=None` while the old
recording still plays and is still the master clock.

**B5. Unplayable audio fails silently** — `ui/audio.py`. Nothing
connects `QMediaPlayer.errorOccurred` or `mediaStatusChanged`. A bad
codec sets the source (so `has_media()` is true and the AudioClock
wins), `play()` does nothing, and the transport looks dead.

**B6. A failed re-engrave is retried on every later change** —
`ui/main_window.py:292–305`. The exception is caught, but the loader's
`_applied_*` caches keep the old inputs, so `needs_reengrave` stays
true. Every subsequent edit, even a colour change, re-runs the failing
engrave and prints another traceback.

**B7. Save is not atomic** — `core/project/serialize.py:484`.
`path.write_text(...)`. A crash mid-write leaves a truncated file that
the reader refuses. Write a temp file next to it and `os.replace`.

**B8. Exported ProRes is untagged for colour** — `render/encode.py:107`.
RGBA in, `yuva444p10le` out, with no `-colorspace/-color_primaries/
-color_trc` and no `out_color_matrix`. swscale defaults RGB→YUV to
BT.601; an NLE reads HD ProRes as BT.709. Black ink is unaffected;
part tints and the glow gold shift hue.

**B9. Bad score file crashes the slot; bad argv crashes the app** —
`ui/file_actions.py:149,194`, `ui/main_window.py:261`. No `try/except`
around `load_score`. From the menu the traceback goes to stderr and
the window stays in its old state with no message. From
`python -m scoreanim bad.xml` it propagates out of `main()`.

### 3.2 Design issues

**D1. The never-clip retry loop is the real large-score cost.**
`provider.py:150–227`. Repagination and scale-to-fit each need
`system_bands(engraved.layout)`, which needs a full decomposition — so
the throwaway passes pay for the SVG walk, id minting and all
post-passes, not just Verovio. Both retries also call `prepare()`
again from disk. The fit percentage could be computed from the first
pass's tallest band, and the page plan from the scaled bands, giving
one re-engrave instead of two. Better still: a cheap "measure only"
pass that reads system bounds from the SVG without decomposing.

**D2. Everything runs on the GUI thread.** `ui/score_loader.py:235`.
The whole engrave (0.25 s on testscore, a minute on complex2) blocks
the window with no busy cursor and no message. Same for every
re-engrave (break toggle, stem flip, a scale keystroke). Rule 1 is
what makes this fixable: everything from `load_detailed` through
`build_trigger_schedule` is pure Python and can run in a worker;
only `ScoreScenes` and the applier must be built on return.

**D3. `set_timing` has no early-out and is followed by a second full
refresh.** `render/animate.py:137` and `ui/playback.py:117–130`.
`set_style` compares before doing work; `set_timing` does not, and
`TempoMap` has no `__eq__`, so a fresh map built by
`MainWindow.timing_config` on every change never matches. This is the
~470 ms per edit on complex2.

**D4. Repeated parsing inside one engrave.** Per engrave: MEI exported
up to four times and parsed each time (`provider.py:445,452,510,511`);
the canonical XML parsed by `prepare`, again by `fill_region_measures`,
again by `strip_hidden_staves`, again by `_sig_change_measures`; and
`load_detailed` re-runs fill+strip once more just to report staff
hides (`provider.py:266–271`). Every one is a whole-score parse.

**D5. Per-drawable string round trips.** `decompose.py:379–398` turns
every `<rect>`, `<line>` and `<polygon>` (staff lines, stems, beams,
barlines — most of the ink) into a path string and re-tokenises it
with a regex to get four numbers. `parse_transform` is called 188k
times on complex3. `part_for_staff` is a linear scan called 75k times.

**D6. Hard raises not gated by `strict`.** The app assumes
`strict=False` makes loads degrade gracefully, but only the
unknown-class guard honours it. These raise regardless: orphan
drawable under a container class (`decompose.py:307`), unknown `<use>`
def (`:359`), non-path in `ledgerLines` (`:328`), `<text>` with two
positioned tspans (`svg_text.py:33`), ledger dash with no owner
(`attribution.py:291`), duplicate id (`identity.py:76,165`), torn group
span (`identity.py:239`). For "any Dorico file opens" these matter more
than the strict flag does.

**D7. Volta brackets are a coverage gap.** I injected first/second
endings into testscore: Verovio emits `class="voltaBracket"`, which is
not in `_KIND_BY_CLASS`. In the app it renders as a degraded static
element (never animates); under strict it FAILS. No fixture has an
`<ending>`, and `"ending"` in `_CONTAINER_CLASSES` (`kinds.py:97`) is a
leftover that does nothing. Big-band charts have these constantly.

**D8. Cross-staff ledger lines** (medium confidence, not tested).
`_attribute_ledger_dashes` buckets by the SVG-nesting staff. Verovio
draws a cross-staff note's ledger lines in the *target* staff's group
while the note stays in its source layer, so the dash finds no owner
and `attribution.py:291` raises. Piano-heavy scores are the likely
trigger. Worth a spike.

**D9. Condense ignores transposition** (`musicxml_rewrite.py:140–160`).
The absorbed part's notes are copied without its `<attributes>`, so
they render under the kept part's `<transpose>`. Horn in F + Horn in
E♭ condensed = wrong concert pitch, silently — the join still matches
because both libraries read the same bytes. Also `zip(keep_measures,
absorb...)` truncates silently on a measure-count mismatch.

**D10. Stage texts store derived layout** (rule 5). `stage_config.py:
185–201` runs `fit_texts` against the engraved band and stores the
result; `EditStageText` refits on edit. The unfitted seed is not kept,
so a later change to the free band (scale, hide-empty, condense) has
nothing to re-derive from. Schema question — ask before touching.

**D11. Dead code the document still feeds.** `derive_tempo_events`,
`lock_to_taps`, `start_residual` (`core/timing/taps.py`) and
`swing_unwarp` have no callers under `scoreanim/` — only tests. The
document still stores `tap_sessions`, and BACKLOG 27 says the strip
uses them. Either the UI was removed without the core, or the docs are
stale. Decide which.

**D12. Modal dialogs and popup menus leak.** `parts_menu.py:79,85,94`,
`text_edit.py:125`, `file_actions.py:275`, `menus.py:188` create
dialogs with `parent=window` and `exec()` them; the C++ object
outlives the Python temporary. Three of them connect to
`document_changed` in `__init__` and never disconnect, so every open
adds a hidden dialog that rebuilds its list on every change forever.
`stage_menu.py:123` and `lane_tempo.py:516` build a `QMenu` per
right-click and never delete it.

**D13. Repaint hygiene.** `stage_scrollbars.py:147` calls
`viewport().update()` on every mouse move, unconditionally. The tempo
and tick lanes repaint their full measure grid at 60 Hz during
playback (`lane_ticks.py:193–213` calls `seconds_at` twice per measure
per frame) when only the playhead moved. The waveform already does
this right with a pixmap cache.

**D14. Glow sprites build on the playback hot path**
(`glow_sprite.py:145–167`): first light of each shape runs a
silhouette render plus a blur pass in a throwaway scene, so the first
play-through hitches. The module-level caches are cleared only on a
glow style change, so old scores' pixmaps survive across loads.

### 3.3 Where the Qt side will hurt on big scores

Not measured here (offscreen, no paint), but visible in the code: one
`QGraphicsItem` per path primitive and per text run, doubled for
reveal kinds, all pages resident, export builds a second full copy.
That is tens of thousands of items on complex2 plus a Python
`ElementItem` with ~15 attributes each. `GroupItem.boundingRect()`
(`items.py:34`) returns `childrenBoundingRect()` on every call, so a
system group walks hundreds of descendants each time Qt asks; with the
pulse on, `setScale` on a group dirties every descendant every frame.
`_qpath`'s cache is per `ScoreScenes` instance, so export re-parses
every glyph outline.

### 3.4 The house rules, applied to the code

**Size.** The ~400-line rule is broken in ten places: `stage_view.py`
664, `provider.py` 603, `attribution.py` 591, `serialize.py` 537,
`stylesheet.py` 477 (one data string — fine), `export_dialog.py` 438,
`main_window.py` 427 (mostly composition — acceptable), `animate.py`
415, `musicxml_prep.py` 410, `items.py` 402. The two that actually do
several jobs are `provider.py` (toolkit options + retry orchestration +
the pipeline) and `attribution.py` (five unrelated passes). `schedule.py`
(391) is at the ceiling and half the animation package imports it just
for its policy tables.

**Duplication.** Six private `_clamp` helpers. `_MEASURE_RE` private in
`schedule.py`, public in `selection/policy.py`, and `durations.py`
imports the private one. Two unrelated modules both named `retime.py`
(`core/animation/` is a kind policy, `core/timing/` is tempo
arithmetic). Two different `GridTick` types. `heads_by_group` rebuilt
three times. `SelectionTriggerControls._context` and
`OnsetCursorController._context` are identical. The zoom curve
constants live in both `app_state.py` and `stage_view.py`. Four
dialogs hand-build the same list + Edit/Remove/Close scaffold.
`glow_driver.py:125–142` re-implements `windows.derive_windows`.

**Fail-soft consistency.** `read_glow` and `read_colors` swallow a bad
value; `build_presets`, `read_volume` and `read_pulse` raise on one. A
hand-edited project file behaves differently depending on which knob
was edited.

**Assertions as control flow.** `provider.py:149,186,217` use `assert
engraved is not None` on the retry paths. Under `python -O` they
vanish; under normal runs a legitimate `None` surfaces as a bare
`AssertionError`.

**Docs that have drifted from the code.** The `EngravingProvider` ABC
lacks `page_breaks`, `stem_directions`, `strict`. The pipeline order in
`verovio/__init__.py` and ARCHITECTURE §3 omits the reclaim passes and
label attribution; neither lists `region_fill`, `system_hides`,
`decoration_reclaim`, `group_span`, `svg_text`. `LoadWarning`'s
docstring misses ~9 codes actually emitted. ARCHITECTURE says
repagination "re-engraves once" — it can be twice, four engraves total.
`LayoutOverride` still says "no editing UI yet". BACKLOG 27 describes
tap code that nothing calls.

---

## 4. What to improve, in order

Each item names the seam. The first five are small and pay back
immediately; 6–8 are the big-score work; the rest is hygiene.

1. **Fix B1** (`durations.py:118`, rename the local; add a
   slash-before-notehead test). One line, and it is a crash waiting on
   element order.

2. **Guard `set_timing`** (`render/animate.py:137`): give `TempoMap`
   value equality, compare `(tempo_map, swing)` and return early; drop
   the trailing `_refresh()` in `playback.set_timing_config` when
   nothing moved. Fixes D3 — the cheapest large win for editing on big
   scores.

3. **Make `ScoreInstaller.load_score` take the new `ProjectDoc`** (or
   every engraving input explicitly) and pass the new document from
   both openers. Fixes B2. Add a test: open a project with a break
   override, assert one `load_detailed` call.

4. **Audio lifecycle** (`ui/audio.py`): add `unload()`, connect
   `errorOccurred`, reset the clock floor on the play transition, call
   `unload` from `open_score`. Fixes B4, B5, and the "play after end
   restarts sound but not animation" case.

5. **Small safety fixes in one commit**: atomic save (B7); colour tags
   on the ffmpeg line (B8, verify with a saturated test frame in the
   NLE); `try/except` + message around both open paths and the argv
   load (B9); mark failing inputs as applied after a failed re-engrave
   (B6); carry `audio` across undo snapshots or make binding a command
   (B3); replace the three `assert`s with real raises.

6. **Cut the retry cost** (`provider.py:150–227`): compute the fit
   percentage from the first pass's tallest band and plan page breaks
   on the scaled bands, so repaginate + fit is one re-engrave. Cache
   the first `PreparedScore` and re-run only the break pass on a copy
   instead of `prepare()` from disk. This alone should take complex2
   from three engraves to two.

7. **Move the load off the GUI thread** along the seam inside
   `ScoreLoader.load`: everything up to `build_trigger_schedule` in a
   worker, `ScoreScenes` + applier on return, discard a stale result if
   a newer load started. Even without speedups, this turns "hangs" into
   "takes a while, with a progress line and a cancel".

8. **Stop re-parsing inside one engrave** (D4, D5): export MEI once and
   derive `_MeiIndex` and both `_container_ns` from the same tree;
   carry an `ET.Element` (deep-copied once) through `region_fill` and
   `system_hides` and serialise once at `loadData`; compute bboxes for
   rect/line/polygon directly; precompute a `staff → part` dict on
   `PreparedScore`. Each is local and goldens must stay byte-identical.

9. **Make the app path actually fail-soft** (D6): gate the per-element
   raises (orphan drawable, unknown def, ledger-dash miss, multi-tspan
   text, torn group span) on `strict`, degrading to a warned static
   element like the unknown-class path already does. Keep structural
   ones (timeline gap, part-count mismatch) loud.

10. **Coverage**: add `voltaBracket` to `_KIND_BY_CLASS`, remove
    `"ending"` from the container set, cut an `endings_min` fixture.
    Spike cross-staff ledger lines (D8). Validate condense groups for
    equal `<transpose>` and measure counts (D9).

11. **Splits, each its own commit with no feature code**: `provider.py`
    → `toolkit.py` / `engrave.py` / `load.py`; `attribution.py` → one
    module per pass; `schedule.py` → `kinds.py` (tables + `is_animated`
    + `quantize_beats`) + the rules; `stage_view.py` → gestures out;
    `serialize.py` → move the 135-line changelog comment to docs and
    split `from_dict`. Rename `core/animation/retime.py` →
    `trigger_overrides.py`.

12. **Qt hygiene**: `WA_DeleteOnClose` on the five modal dialogs and
    disconnect in `done()`; `deleteLater()` on popup menus; only
    `update()` in `hover()` when state changed; cache the lanes' measure
    grid in a pixmap keyed on the axis; freeze `SystemGroupItem.
    boundingRect()`; pre-warm glow sprites after load and clear the
    caches per load; share the `_qpath` cache across scenes.

13. **Decide the taps' fate** (D11) and fix BACKLOG 27 either way.
    Store the unfitted stage-text seed (D10) — schema bump, so ask
    first. Refresh the ABC signature, pipeline-order docstrings and
    the `LoadWarning` code list.

14. **De-duplicate**: one clamp helper, one `_MEASURE_RE`, one
    `_context`, one row-list base for the layout zone, one
    list-manager dialog scaffold; move the chain-span window into
    `derive_windows` so `glow_driver` becomes a lookup.

---

## 5. Note on the test suite

Not re-reviewed here; `docs/TEST_SUITE_REVIEW.md` (2026-09-01) already
covers it. The one thing this review adds: B1 shows a gap in what the
synthetic fixtures exercise — element order is a hidden assumption in
`durations.py` that no test pins.
