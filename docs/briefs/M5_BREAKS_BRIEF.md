# M5 — Breaks: build brief

Scope authority is `docs/ROADMAP.md` §M5. This file is how it gets
built. Written after the audit and the spike, before any feature code.

Status: **planning only.** §4 holds ten decisions that need a ruling.
Nothing in §5 is built. The rule-7 amendment stays a draft in ROADMAP
until the build session applies it to CLAUDE.md with the ruling date.

---

## 0. Baseline

- `beta/m5-breaks`, branched off `main` at 475cd86 (the M3 merge,
  tagged `v0.2-beta.3`). M5 closes as `v0.2-beta.4`.
- Suite at branch point: **858 passed, 1 xfailed**.
- Schema at branch point: **v7**; M5 takes **v8**.
- `spikes/system_breaks.py` is the measurement, kept. Sections A–F; run
  `python spikes/system_breaks.py` (full, ~6 min — complex2 condensing
  dominates) or `python spikes/system_breaks.py f` for A + the
  decision probes.

---

## 1. What already exists (audit)

Every claim below was re-read against the tree on 2026-07-28.

### 1.1 The prep-seam injection pattern (Phases 8 / 9 / 12)

`core/score/musicxml_prep.py:prepare()` is the one function that turns
a score path plus intent into the exact bytes Verovio and music21 both
see. It already carries **four** rewrite passes of exactly the shape M5
needs, in a fixed order with the reasons commented:

| pass | intent it consumes | phase |
|---|---|---|
| `_apply_condense` | `condense: tuple[PartCondenseSpec, ...]` | 12.3 |
| `_apply_text_overrides` | `texts: tuple[PartTextSpec, ...]` | 9.3 |
| `_inject_part_groups` | `groups: tuple[PartGroupSpec, ...]` | 8 |
| `_repaginate` | `page_break_measures: tuple[int, ...]` | 10R |

**`_repaginate` is M5's template and it is closer than the roadmap
implies.** It already rewrites `<print>` on part 1 only ("Verovio reads
print layout from the first part — spike section D"), already keys by
1-based document ordinal rather than printed number, with the
adapter-item-12 rationale spelled out in a comment, and already handles
the create-`<print>`-if-absent case. M5's pass is its twin over the
`new-system` attribute instead of `new-page`.

Two things about `_repaginate` that M5 must NOT copy: it is
**derived** data (a plan re-computed every load from measured overflow,
never stored), and it **strips all encoded page breaks** before
re-asserting its own. M5's overrides are stored intent and are a sparse
*delta* on the encoded set — they never strip.

**Flag (no-monoliths).** `musicxml_prep.py` is **577 lines**, already
44% past the ~400 ceiling, and it is where M5's pass belongs. See D0.

### 1.2 The `_applied_*` diff re-engrave shape

`ui/score_loader.py` holds five `_applied_*` caches recording the
engrave inputs of the last load, and `needs_reengrave(doc)` compares
the document against all five. `MainWindow._on_document_changed` calls
it first, before any sync, so execute / undo / redo all route through
one place; `_reengrave` re-loads and calls `router.show_current()`.
Adding a sixth input is three lines (a cache field, a clause in
`needs_reengrave`, a `load()` parameter) plus the assignment at the
bottom of `load()`. Cost measured in §3.6: 0.25 s testscore, 1.28 s
bigband1 — so `SetSystemBreak` arrives via `execute()`, never
`preview()`, like `SetPartText`.

### 1.3 `AppState.selection.measure_ordinal`

`core/selection/context.py:Selection.measure_ordinal` is a property
delegating to `core/selection/policy.py:measure_ordinal_of`, which
parses `:m(\d+):` out of the minted id and returns `None` for ids that
genuinely have no measure. Its docstring already names M5 as a
consumer. **M5 reads the property**, adds no third caller of the helper,
and therefore leaves BACKLOG 9(c) open exactly as M3 did.

### 1.4 Schema version machinery

`core/project/serialize.py`: `PROJECT_VERSION = 7`,
`_READABLE_VERSIONS = (1, …, 7)`. The bump comment block documents each
version and, for each, whether it needed a **read gate**. Only v4
(`hide_empty_staves`) did — older files predate the option and must load
OFF. M5's field needs none: a missing key defaults to `{}`, which is "no
overrides", which is the pre-option look.

The alpha's **strict-by-version gate** is the point of bumping at all:
`v0.1-alpha` and every tagged beta refuse a file whose version they do
not know, rather than silently dropping the field and destroying it on
the next save. That is the v2 rationale, restated at v6 and v7.

### 1.5 `ui/view_router.show_current`

`show_current()` re-shows the current position in the current mode:
`show_page(self._page)` or `show_system(self._system)`. Both clamp
(`max(1, min(n, count))`), so a break edit that changes the page or
system count cannot put the router out of range. What it **does** do is
keep the same *index*, and after a break edit the same index is
different music. See D8.

### 1.6 Barline selectability and its id grammar

`core/selection/policy.py` ranks candidates by
`(not exact, tier, area, element_id)`. `BACKDROP_KINDS = {STAFF_LINES}`
is filtered out entirely by `is_selectable`; `BARLINE` is in
`STATIC_KINDS`, so it sits in the scaffold tier — above the backdrop,
below animated ink. The M2.0 census measured barline click accuracy at
**100%** on complex3 after tiering. The handle rule 13 promises is real
and tested.

`core/engraving/verovio/identity.py` mints three id shapes. A barline
has no part, so it takes the middle one:
`score:m{ordinal}:barline:{seq}` — **unless** it also has no measure, in
which case it falls to `score:p{page}:barline:{seq}`. §3.5 measures
which barlines land where, and the answer decides D2 and D3.

---

## 2. What does not exist

- No `system_break_overrides` field, no `SetSystemBreak` command, no
  `new-system` rewrite. All new.
- **No context menu anywhere on the stage.** `ui/stage_view.py` handles
  press / release / double-click and has no `contextMenuEvent`. A
  context menu is new machinery, not a re-home. Bears on D1.
- **No measure→system map outside the adapter.** The provider builds
  `state.system_of_measure` and derives `first_measure` from it for the
  repagination planner, then drops both — `EngravedScore` does not carry
  either. The spike reconstructs the map from element ids + `el.system`,
  which works, but D4 needs it in the app. Bears on D4.

---

## 3. Measurements (`spikes/system_breaks.py`)

The spike monkeypatches `prepare` so the **whole existing pipeline** —
retry loops, hide-empty-staves round-trip, repagination, scale-to-fit —
runs against the edited break set, rather than testing a rewrite in
isolation. `bigband1` and `complex2` go through the app path
(`strict=False`); `testscore` is loaded strict.

### 3.1 Verovio honors both directions (section A, testscore)

Baseline systems: `{1:[1-4], 2:[5-8], 3:[9-12], 4:[13-16], 5:[17-19]}`,
3 pages.

| case | result | honored |
|---|---|---|
| A1 FORCE at m3 (`new-system="no"` encoded) | `1:[1,2] 2:[3,4] 3:[5-8] …` | **yes** |
| A2 SUPPRESS at m9 (`new-system="yes"` encoded) | `2:[5,6,7,8,9,10,11,12]` | **yes** |
| A3 SUPPRESS at m3 (no encoded break) | identical to baseline | inert |
| A4 FORCE at m1 (already a system start) | identical to baseline | inert |
| A4 FORCE at m19 (last measure) | `3:[17,18] 4:[19]` + `repaginated` | **yes** |
| A6 FORCE m3 **and** SUPPRESS m9 together | both applied | **yes** |

No new warning codes, no load failures, page count unchanged except
where the never-clip repagination fired.

### 3.2 ElementIds of unaffected measures survive (section B)

| edit | measures with byte-identical id sets |
|---|---|
| FORCE before m3 | **18 / 19** (only m3 differs) |
| SUPPRESS at m9 | **17 / 19** (only m8, m9 differ) |

The differences are not noise — they are exactly two mechanisms, and
both are musically correct:

1. **System-start restatement furniture.** A measure that becomes a
   system start *gains* `…:clef:0` and `…:key_sig:0` per part (14 ids on
   FORCE m3, across 7 parts); a measure that stops being one *loses*
   them. The engraver restates clef and key at every system start.
2. **Spanner continuation segments and ledger re-layout.** Merging m8/m9
   removed `P3:m8:s1:v1:tie:0:seg1` and `:tie:1:seg1` — a tie that
   crossed the break is one unbroken tie once the break is gone — plus
   two `ledger_lines` ids as the measure re-lays out.

Page-scoped ids (`score:p{n}:…`) shift, as they do under repagination:
FORCE m3 turned `score:p1:barline:0` into `{barline:0, barline:1}` and
added six `score:p1:text:*`. This is the accepted rule-7(a) precedent.

**Barline ids specifically: the 19 measure-scoped barline ids are
byte-identical under both edits.** Only the page-scoped system-start
barlines renumber. This is what makes D9 cheap.

### 3.3 Downstream flows correctly (section C, bigband1 app path)

| case | result |
|---|---|
| C1 force m3 | 9 → 8 systems, 3 → 4 pages, `repaginated` fired and held |
| C1 suppress encoded m5 | 9 → 8 systems, 3 pages, no new warnings |
| C1 force m7 (mid-system) | clean split `2:[5,6] 3:[7,8]` |
| C2 hide_empty_staves ON | force and suppress both honored; hiding still applied |
| C3 force m2..m15 (18 systems) | 7 pages, `repaginated`, **0 systems overflow** |
| C4 suppress every encoded break | 1 system, 1 page, no `scaled-to-fit` needed |
| C5 complex2 + condensing + force m4 | 20 → 21 systems / pages, `repaginated` + `scaled-to-fit` both still fire |

The never-clip guarantee (rule 7) survives the worst thing a user can
do with this feature: C3 forces fourteen breaks and every system still
fits its page after the retries.

One thing to watch, not a blocker: C2's `force m3` run emitted
`segment-count-mismatch` and `unattributed-continuation` warnings that
the flat run does not. Those are the Phase-11/FINDING-5 spanner
attribution diagnostics reacting to a re-laid-out hidden-staff system —
expected under flag-and-continue, but the build should confirm they are
not a new leak (M5.2's verification says so explicitly).

### 3.4 Animation and reveal re-derive sanely (section D)

| | FORCE m3 | SUPPRESS m9 |
|---|---|---|
| join complete | True → True | True → True |
| triggers | 89 → 89 | 89 → 89 |
| timemap `score_end` | 70.0 → 70.0 | 70.0 → 70.0 |
| shared ids with a changed beat | **0** | 5 |
| reveal tracks (system × part) | 35 → 42 (6 sys × 7) | 35 → 28 (4 sys × 7) |
| tracks with non-monotonic edge x | 0 | 0 |

`score_end` and the trigger count are **identical** across both edits.
That is the rule-12 result that matters: the engraved timemap is a
performance-time axis and a break is a layout choice, so the beat
authority does not move.

The 5 changed beats on SUPPRESS are all `LEDGER_LINES`, all inside m8
and m9 — the two measures the merge re-lays out — and they are **id
re-use**, not retiming: `P3:m9:s1:v1:ledger_lines:3` goes 33.0 → 30.0
because seq 3 now names a different ledger group in a re-flowed measure.
No notehead, rest, or spanner changed its trigger.

Reveal tracks land at exactly 7 per system (one per part) in every case,
and every edge is monotonic in x.

### 3.5 The barline handle, measured (section E)

| fixture | barlines | carry an ordinal | do not |
|---|---|---|---|
| testscore | 24 | **19** | 5 |
| bigband1 | 37 | **28** | 9 |

- Exactly **one measure-scoped barline per measure**, and **no measure
  lacks one** (histogram `{1: n}`, missing `[]`, both fixtures).
- It is the measure's **right** barline: `score:m1:barline:0` sits at
  x=796 on a system whose m1 spans from x≈356. So "the barline you
  clicked" always means "the end of measure N".
- The **system-start (left) barline is page-scoped** —
  `score:p{page}:barline:{k}` — so `Selection.measure_ordinal` is
  `None` for it. That is 5 of 24 / 9 of 37 barlines: selectable, but
  carrying nothing M5 can key on. Bears on D3.
- Last measure of each system, testscore: `{1:4, 2:8, 3:12, 4:16,
  5:19}`; bigband1: `{1:4, 2:8, 3:11, 4:13, 5:16, 6:19, 7:22, 8:25,
  9:28}`. These are the barlines where a break already exists.

### 3.6 The decision probes (section F)

- **F1** — FORCE at ordinal 20 on a 19-measure score is **silently
  inert**: the rewrite loop simply never reaches that ordinal, exactly
  as `_repaginate` behaves for an out-of-range plan entry.
- **F2** — SUPPRESS on m5, whose encoded break is `new-page="yes"`:
  - leaving `new-page` alone → **no merge at all**, systems identical to
    baseline. The suppression is a lie.
  - dropping `new-page` too → m4 and m5 share a system; page count
    unchanged (3), because repagination re-derives the page breaks.
- **F3** — the full changed-beat set on a merge is the five
  `LEDGER_LINES` ids of §3.4, all in the two touched measures.
- **F4** — one toggle's full re-engrave: **testscore 0.25 s, bigband1
  1.28 s**. Comparable to the part-label re-engrave (~0.6 s) that
  already ships through `execute()`.

---

## 4. Decisions — proposed, recommended, not decided

Each states the measurement behind it. Nothing here is settled.

### 4.0 D0 — pay the no-monoliths debt first (stop-and-ask)

`musicxml_prep.py` is **577 lines** and M5's pass belongs in it. The
working-style rule says split along a real seam BEFORE adding, and M3.0
set the precedent: pay it as the first commit on the branch, with no
feature code in it.

**Proposed seam — rewrite vs read.** The module does two unrelated jobs.
Eight functions *rewrite the tree* (`_apply_condense`, `_voice_cursor`,
`_apply_text_overrides`, `_set_part_text`, `_inject_part_groups`,
`_repaginate`, `_neutralize_octave_only_transposes`,
`_drop_redundant_trailing_forwards` — ~253 lines); the rest *read* it
(`_parts`, `_slash_regions`, `_repeat_regions`, `_credits`,
`_page_size`) or define the spec dataclasses. Move the rewriters to
`core/score/musicxml_rewrite.py`; `musicxml_prep.py` keeps the
dataclasses, the scanners, and `prepare()` as the orchestrator that
names the pass order. Both land near ~320 lines, M5's pass joins the
rewrite module, and no downstream import changes (`prepare`,
`PreparedScore` and the three `*Spec` types keep their home).

**Recommend: do it, as M5.0, its own commit, goldens byte-identical.**
Alternative: skip it and add a ninth function to a 577-line module —
which the rule exists to prevent.

### 4.1 D1 — where the toggle lives (stop-and-ask)

The roadmap says "context menu / Score menu". Measured: **there is no
stage context menu today** (§2), so that branch is new machinery —
`contextMenuEvent` on `StageView`, hit resolution, a menu built per
click.

**Recommend: a Score-menu action, "Toggle System Break Here", with a
shortcut**, enabled only when the selection yields a target (D3, D6).
Reasons: the Score menu is already the home of every layout choice
(Score Setup, Staff Groups, Hide Empty Staves); the action is
keyboard-reachable, which is what break authoring actually wants when
you are working through a score; and it costs one `addAction` in
`ui/parts_menu.py`'s `rebuild()`. A context menu can be added later
over the same command without changing anything below the UI.

Counter-argument, stated fairly: right-click on the barline is the
gesture a Dorico user will reach for first, and a menu-bar action makes
the selection→action link less obvious.

### 4.2 D2 — what "here" means, and what the map is keyed by

Measured (§3.5): the selectable barline is the measure's **right**
barline, one per measure, every measure. So "break at this barline"
unambiguously means "the break falls **after** measure N".

**Recommend: the document key is the ordinal of the measure that STARTS
the new system — N+1, not N.** The UI converts at the seam (barline in
measure N → key N+1). This makes the key mean exactly what the MusicXML
attribute means (`<print new-system="yes">` sits on the measure that
starts the system) and exactly what `_repaginate`'s `break_measures`
already means, so the rewrite is a straight lookup with no arithmetic
and the two break mechanisms read the same way.

Alternative, to name and reject: key by N ("break after this measure").
It reads more naturally in the UI, but every consumer then has to do
`+1`, and it would be the only ordinal in the codebase that does not
mean "this measure".

### 4.3 D3 — the system-start barline has no ordinal

Measured: 5 of 24 (testscore) / 9 of 37 (bigband1) barlines are minted
`score:p{page}:barline:{k}` and return `None` from
`Selection.measure_ordinal`. These are the left-hand barlines that open
each system — selectable under M2's tiering, but carrying nothing to key
on.

**Recommend: the action disables when `measure_ordinal` is None.** The
Selection panel already shows "—" for the measure in that case, so the
disabled action is consistent with what the user is being told.

Alternative, to name and reject: attribute those barlines in the
adapter so they carry a measure. That is an adapter change that **moves
goldens** — precisely the reason M3's part-label route could not be
built (BACKLOG 14) — and it is out of a milestone whose charter is a
layout-intent edit, not new adapter semantics.

### 4.4 D4 — toggle sense: what does the action write?

A "toggle" has to know the current state. Three sources are available:
the document override (exact, cheap), the current engraved layout
(exact, needs exposing), and the encoded break set (would need a second
no-override load — reject).

**Recommend a three-line rule, in this order:**

1. An override already exists for the target ordinal → **clear it**
   (back to whatever the file encodes). Keeps the doc sparse, the
   `SetElementStyle` idiom, and makes the gesture perfectly reversible.
2. No override, and the target ordinal already starts a system in the
   current layout → write **SUPPRESS**.
3. No override, and it does not → write **FORCE**.

This needs measure→system in the app. **Recommend adding
`EngravedScore.system_of_measure`**: the adapter already builds it
(`state.system_of_measure`) and throws it away, and the golden
serializer names its fields explicitly, so adding one **does not move
goldens** (verified by reading `tests/golden.py`). The alternative —
reconstructing it in the UI from element ids, as the spike does — works
but puts a parse where a fact is available.

The toggle sense itself is pure and belongs in `core/`, headless-tested
on synthetic maps (the `core/selection/policy.py` shape).

### 4.5 D5 — SUPPRESS where there is no encoded break: no-op or rejected?

The question the roadmap asks. Measured (§3.1 A3): at the seam it is
**silently inert** — the attribute is set to `"no"` where it already
was `"no"`.

**Recommend: neither — it is never written.** Under D4 the toggle can
only produce SUPPRESS when the target *does* currently start a system,
so the case does not arise through the UI. For a document that
nonetheless holds one (hand-edited file, or a score replaced under an
existing project), **recommend storing it and letting it be inert**,
with the load-time warning of D10 — matching how `_repaginate` treats an
out-of-range plan entry, and matching rule 5's stated staleness trade.

Alternative, to name: have `SetSystemBreak` reject it with a
`CommandError`. That requires the command to know the engraved layout,
which no command does today (`part_order` is the precedent for passing
runtime data in, but it would be validating against *derived* data, not
against the score's structure).

### 4.6 D6 — the last measure

Measured (§3.6 F1): an ordinal past the end is silently inert. So under
D2 a barline on the final measure targets ordinal N+1, which does not
exist.

**Recommend: the action disables on the last measure's barline** —
there is no music after it to start a system, and a disabled action says
so more honestly than one that does nothing.

Note the case this does *not* cover, which stays allowed and works:
forcing a break at the last measure (targeted from measure N−1's
barline) yields a legitimate one-measure final system plus a
`repaginated` warning (§3.1 A4).

### 4.7 D7 — SUPPRESS on a measure whose encoded break is a PAGE break

Measured (§3.6 F2), and this is the sharpest of the ten:

- Leave `new-page="yes"` alone → **the suppression does nothing**. A
  page break implies a system break, so the systems do not merge.
- Drop `new-page` too → the merge happens, and the page count is
  unchanged, because rule 7(a)'s repagination re-derives page breaks
  whenever the encoded ones do not hold.

**Recommend: SUPPRESS drops the encoded `new-page` as well.** The
consequence to state plainly: suppressing a *system* break can move a
*page* break. That is acceptable because rule 7(a) already establishes
that we own page breaks whenever they cannot hold their systems, and
because the alternative makes the feature silently fail on exactly the
measures where a score's layout is most deliberate.

Alternative, to name: disable suppression on page-break measures. Honest,
but it makes a whole class of barlines dead for no reason the user can
see — and page-break measures are common (testscore has 2 in 19).

Page-break *authoring* stays out of beta scope (ROADMAP's closing
section) either way. This is a side effect of suppression, not a
feature.

### 4.8 D8 — where the view goes after the re-engrave

`_reengrave` calls `router.show_current()`, which re-shows the same
page/system **index**. Both accessors clamp, so nothing goes out of
range — but measured, FORCE m3 takes testscore from 5 systems to 6 and
SUPPRESS m9 takes it to 4, so the same index is different music, and in
system mode the stage jumps away from the edit.

**Recommend: the router gains `show_measure(ordinal)` and the break
re-engrave re-anchors to the system (or page) containing the edited
measure.** It reads off the same `system_of_measure` map D4 needs, so
the cost is small, and "the score stays where you were working" is the
behavior every notation editor has.

Alternative: leave `show_current()` and accept the jump. Cheaper, and
in paged mode on a multi-measure page it is often invisible.

### 4.9 D9 — the selection after the re-engrave

`_install` calls `selection.bind_scenes`, which clears the selection —
BACKLOG 9 seam (b), still open after M3. Consequence for M5: toggle a
break and the barline you clicked deselects, so toggling back needs a
fresh click on ink that has just moved.

Measured (§3.2): **the 19 measure-scoped barline ids are byte-identical
across both edits.** The id the user clicked still exists in the fresh
scenes.

**Recommend: M5 pays seam (b) narrowly** — after a re-engrave, re-resolve
the selection through `scenes.items.get(eid)` and restore it if the id
survived, clear it if it did not. Roughly the ten lines BACKLOG 9 has
been describing since M2, and M5 is the first milestone with a concrete
reason to want it.

Alternative: leave it clearing. The feature works; it just feels wrong.

### 4.10 D10 — a stale override, and whether it warns

Rule 5 accepts override staleness (ARCHITECTURE §4): an id that no
longer exists is skipped. Break overrides are keyed by measure ordinal
rather than element id, so the failure mode is different — an ordinal
past the end of a score that has since been shortened, or a suppression
whose encoded break has gone.

**Recommend: a `LoadWarning "break-override-inert"`** naming the
ordinals that had no effect, counted in the status bar like every other
load warning (flag-and-continue, Phase 10 ruling b). It costs a set
comparison at the seam and it is the difference between "my break did
nothing" and "my break did nothing *and the app told me*".

Alternative: stay silent, on the grounds that rule 5 staleness is silent
everywhere else.

---

## 5. Task breakdown

Each task ends with a concrete check. No task starts before D0–D10 are
ruled — several of them change what gets built.

### M5.0 — the prep-seam split (no feature code)

Per D0: `core/score/musicxml_rewrite.py` takes the eight tree-rewriting
functions; `musicxml_prep.py` keeps the spec dataclasses, the scanners,
and `prepare()`. Re-export so no downstream import changes.

**Verify:** `pytest` green at 858/1; `tests/test_golden_layouts.py`
byte-identical on all 12 fixtures; `wc -l` on both modules under 400.
Its own commit, no M5 feature code in it.

### M5.1 — document field, command, schema v8

`SystemBreak` (a `str` enum or `Literal`: FORCE / SUPPRESS),
`ProjectDoc.system_break_overrides: Mapping[int, SystemBreak]` defaulting
to `{}`, and `SetSystemBreak(ordinal, mode | None)` in
`core/project/commands/layout.py` — sparse (a `None` mode pops the
entry, the `SetElementStyle` idiom), undoable (rule 8). `serialize.py`
to v8 with the bump comment, `_READABLE_VERSIONS` extended, no read gate
(§1.4).

**Verify:** headless tests — round-trip a doc with two overrides; a
`None` mode pops the entry and leaves the doc equal to the unedited one;
undo/redo step through each toggle individually; a v7 fixture file loads
with `{}` and unchanged look; a v8 file is refused by a `_READABLE_
VERSIONS`-restricted reader (the gate's own test).

### M5.2 — the prep-seam pass

`_apply_system_breaks(root, overrides)` in the rewrite module, twin of
`_repaginate`: part 1 only, keyed by ordinal, creates `<print>` when
absent, FORCE sets `new-system="yes"`, SUPPRESS sets `new-system="no"`
and — per D7 — clears an encoded `new-page="yes"`. `prepare()` grows a
`system_breaks=` parameter; `EngravingProvider.load` / `load_detailed`
thread it through.

**The trap to pin by test:** `load_detailed` calls `prepare()` **three
more times** — the hide-unavailable retry, the repagination retry, and
the scale-to-fit retry. Each must carry the overrides, or a score that
repaginates silently loses the user's breaks.

**Verify:** headless — FORCE and SUPPRESS both land on testscore
(assert `system_of_measure`); a load that emits `repaginated` still has
the forced break; `hide_empty_staves=True` + FORCE still hides; the C2
warning set from §3.3 does not grow beyond what the spike recorded.
Goldens byte-identical (no fixture has overrides).

### M5.3 — measure→system, and the toggle policy

Expose `EngravedScore.system_of_measure` (the adapter already builds it;
goldens unaffected per D4). Add a pure policy module — `core/editing/
breaks.py`, the `core/editing/nudge.py` shape — holding the target
arithmetic (barline ordinal N → target N+1, D2), the enable rules
(None ordinal D3, last measure D6), and the three-step toggle sense
(D4). No Qt.

**Verify:** headless unit tests on synthetic maps — each of the three
toggle branches, both disable cases, and a round-trip
(FORCE → toggle → doc equals the original).

### M5.4 — UI wiring

The Score-menu action per D1, enabled from `AppState.selection` via the
M5.3 policy and disabled with no selection; `ScoreLoader._applied_breaks`
+ the `needs_reengrave` clause + the `load()` parameter; the D10 warning.

**Verify:** headless window test — select a barline, trigger the action,
assert one re-engrave happened and the systems split; undo, assert they
merge back; assert the action is disabled for a system-start barline, for
a last-measure barline, and with nothing selected.

### M5.5 — position and selection across the re-engrave

`ViewRouter.show_measure(ordinal)` per D8, called by the break
re-engrave; selection re-resolution per D9.

**Verify:** additions to `tests/test_view_router.py` (stub-based, the M3.0
pattern) for `show_measure` in both modes; a test that a break toggle
leaves the same barline selected.

### M5.6 — docs

Apply the ROADMAP rule-7 amendment to CLAUDE.md **with the ruling date**;
close ROADMAP §M5 with what was built and where reality differed;
ARCHITECTURE gets the break-override seam; BACKLOG 9 seam (b) closed if
M5.5 lands, 9(c) restated as still open.

**Verify:** full suite green, goldens byte-identical, `docs/` diff read
end to end before the merge.

---

## 6. Exit criteria (from ROADMAP §M5)

On bigband1: force a break mid-way — the system splits, downstream
repagination stays sane, animation and reveal edges are correct on both
new systems; suppress an encoded break — systems merge; both undo
cleanly; save/reload reproduces; goldens for unmodified fixtures
unchanged. Suite green.

**Fixture caveat.** bigband1 does not load under the strict path
(`unknown SVG class 'gliss'`), so the interactive exit run is the app
path; headless tests and spikes against it must pass `strict=False`.
The spike does; §3.3's numbers are all app-path.

---

## 7. Invariants in force throughout

Rule 1 — the toggle policy and the break rewrite are pure Python in
`core/`; no Qt. Rule 5 — overrides are intent, keyed by measure
**ordinal**, never printed number, and every layout consequence
re-derives. Rule 7 — the amendment is a draft until M5.6 applies it; the
never-clip guarantee holds under every forced break (§3.3 C3 pins it).
Rule 8 — `SetSystemBreak` is undoable, one entry per toggle. Rule 12 —
the engraved timemap does not move when a break does (§3.4 pins
`score_end` and the trigger count). Rule 13 — the barline is the handle,
and it stays an object in a measure, never the measure itself.
No-monoliths — D0 is paid before anything is added. Goldens
byte-identical for unmodified fixtures at every commit.
