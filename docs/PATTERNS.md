# ScoreAnim — Patterns

The idiom book: how this codebase solves problems, distilled from six
milestones of measured decisions. Every feature plan names which of
these it rides; deviating from one is a flag-and-stop, not a judgment
call. Deep sources: the closed sections of ROADMAP, the briefs in
`docs/briefs/`, and ARCHITECTURE. Keep entries short and plainly
worded — every session may read this file. When a session makes a
mistake a one-line entry here would have prevented, add the line.

## Idioms

**The prep-seam pass** — engraving-affecting user intent becomes a
rewrite of the canonical MusicXML BEFORE Verovio, never a render-side
patch. `musicxml_prep.prepare()` orchestrates the pass order (reasons
commented); `musicxml_rewrite.py` holds the passes. New intent = a new
pass: sparse delta keyed by stable identity, never stripping encoded
data (`_repaginate` is the one deliberate exception, page attrs only).
Precedent: groups (P8), part texts (P9), condense (P12), breaks (M5/M6).

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

**Two hit paths, on purpose** — selection resolves rule-13 OBJECTS;
double-click-to-edit has its own resolver that also reaches stage
texts. Stage texts are editable but never selectable (they carry no
measure/part). Do not merge the paths.

## Traps (each of these has already cost a debugging session)

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
  reveal edge is off by exactly dx.
- **Vacuous pins**: a test sampling state that cannot change passes
  forever (M2.7's "playback undisturbed" sampled a downbeat notehead).
  Guard non-vacuity: pick samples that MUST differ, fail if they don't.
- **"No-op at baseline" must be probed in the configurations the
  goldens pin** — BACKLOG 16's fix was measured a no-op on four default
  loads and still moved two goldens (hidden/flat variants repaginate).
- **Zero-area authored rects exist** (a stem's Rect has w = 0), so any
  area/size heuristic needs an exactness tier first.
- **Dorico encodes page breaks page-only**: `new-page="yes"` with no
  `new-system`. new-page IMPLIES a system break — clearing or stripping
  it destroys the system break too unless promoted/asserted.
- **`QMainWindow.saveState` covers docks, not inner splitters** — lane
  splitters need their own persistence if wanted.
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
