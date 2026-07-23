# Refactor brief — verovio_adapter decomposition (2026-07-21)

Written by a Cowork planning session, 2026-07-21. Purpose: give the
refactor Claude Code session a verified map of the adapter so it
plans from facts. The map below was read from the current file
(1823 lines) and the current import graph on this date.

## Goal

Split `core/engraving/verovio_adapter.py` into a package of
pipeline-stage modules behind the same public API, with a
golden-snapshot safety net captured BEFORE the first move — and use
the split to surface and fix latent defects, under the
behavior-change policy below. The win is twofold: the next score bug
localizes to one ~200-line stage module instead of one 1800-line
file, and defects the split uncovers get fixed deliberately, each
one attributable to its own commit.

## Behavior-change policy (ruled by Marcus, 2026-07-21)

The goal includes making the adapter ERROR LESS, not just moving
code — but a move and a fix must never share a commit, or the
golden diff can't say which caused what. Three categories:

1. **Mechanical moves** (the split itself): goldens byte-identical,
   pytest green, per commit. No exceptions — a move that "needs" a
   tweak isn't a move; log the tweak as a finding instead.
2. **Hardening with no output change**: better error messages,
   tightened invariants/assertions, defensive checks that don't
   alter any fixture's output. Allowed freely in their own commits —
   the goldens prove the "no output change" claim.
3. **Behavior fixes** (output differs on some fixture): during the
   split, suspected defects are LOGGED in a findings list, not fixed
   inline. They are fixed in the dedicated findings stage, one fix
   per commit, each with (i) the golden before/after diff, (ii) a
   test pinning the new behavior, (iii) the golden baseline
   re-captured in the same commit. Fixes that change animation
   semantics or rendered output stop for Marcus's ruling first
   (flag-and-stop); pure crash/robustness fixes may proceed and be
   reported with their diffs at the end of the stage.

## What this refactor is NOT

- Not a redesign of the provider seam. Rule 4 stands exactly as is:
  Verovio types/ids/SVG still never leak past the adapter package.
- Not a fix for the live-playback spanner early-reveal bug. That
  leak was verified (2026-07-21) to be in the render/applier path
  (`render/animate.py` / `render/items.py` clip application), NOT in
  the adapter — the adapter's system attribution and the pure reveal
  pipeline check out clean. Chase that in its own session; do not
  let the refactor session get pulled into it.
- Not an abstraction pass. CLAUDE.md working style applies: boring,
  explicit code; no new seams beyond the module boundaries
  themselves. Strategy patterns, plugin registries, or a general
  "pipeline framework" are all out of scope.
- Not a license to improvise: behavior changes happen only through
  the findings stage under the policy above, never smuggled into a
  move.

## Why the file breeds bugs (verified map, 2026-07-21)

The module is eight jobs in one namespace (line ranges as of today):

1. **Policy tables** (≈39–170): `_KIND_BY_CLASS`,
   `_CONTAINER_CLASSES`, `_SPANNER_CLASSES`, `_STATIC_TEXT_CLASSES`,
   `_TIMEMAP_CLASSES`, text-style sets, scale constants.
2. **MEI indexing** (≈173–350): `_MeiIndex`, `_parse_mei`,
   `_walk_layer` — pure XML → lookup tables.
3. **Public records** (≈353–383): `AdapterNoteRecord`,
   `EngravedScore`.
4. **SVG decomposition** (≈386–762): `_ElementAccumulator`,
   `_PageDecomposer`, `_RunAttrs` — SVG tree walk → accumulators.
5. **Load orchestration** (≈765–1058): `_LoadState`,
   `VerovioEngravingProvider` with the toolkit options, the
   hide-empty-staves MEI round-trip, and the repagination /
   scale-to-fit retry loops (rule 7 amendments a and c).
6. **Attribution post-passes** (≈1061–1429):
   `_rehome_stray_paths`, `_attribute_ledger_dashes`,
   `_attribute_spanner_segments`, `_flag_implausible_ties`, tstamp
   helpers — in-place mutation of accumulators, order-sensitive.
7. **Identity + onset resolution + element construction**
   (≈1432–1543 and 1642–1823): `_build_elements`, `_identity_for`,
   `_attach_onset`, `_chord_group`.
8. **Synthesis** (≈1546–1639): `_synthesize_slashes`,
   `_synthesize_repeats`.

Structural failure modes this invites — each has already produced a
real bug in a past phase:

- `_LoadState` is a mutable god-object every stage reads AND writes;
  a change in one stage propagates invisibly to the others.
- Post-pass ORDER is a correctness invariant that lives only in
  comments (`_flag_implausible_ties` must run after segment matching
  so bogus sources stay in the pairing pool; rehoming must precede
  element construction). The order is encoded implicitly by five
  consecutive calls inside `_engrave_prepared`.
- Onset resolution is one long if/elif chain in `_identity_for`,
  gated by svg_class — where both the Phase 10R id-reuse bug and the
  2026-07-20 tuplet-downbeat bug lived. It deserves its own module
  and its own focused unit tests.
- Tooling is coupled to the module's internals: tests import private
  names (`_identity_for`, `_LoadState`, `_MeiIndex`, `_parse_mei`),
  and two spikes monkeypatch module attributes
  (`complex1_triage.py` patches `verovio_adapter.parse_transform`;
  both triage spikes patch `_attribute_ledger_dashes`). Any move
  breaks them unless handled deliberately — rulings (a)/(b) below.

Import sites today (verified): app path `ui/main_window.py`; tools
`check_score.py`, `dump_notes.py`, `render_page_png.py`,
`bbox_overlay.py`; core `score/join.py` (AdapterNoteRecord); tests
`conftest.py` + ~12 test modules; spikes as above.

## Proposed target shape (starting map — the plan session proposes
the final split, Marcus approves it in ruling (c))

`core/engraving/verovio/` package:

- `kinds.py` — the policy tables/sets, no logic
- `mei_index.py` — job 2
- `records.py` — jobs 3 + `_LoadState` (the shared-state dataclass
  next to the records it feeds)
- `decompose.py` — job 4
- `attribution.py` — job 6
- `identity.py` — job 7
- `synthesis.py` — job 8
- `provider.py` — job 5 (toolkit options, retry loops, and ONE
  function that names the pipeline order explicitly)
- `__init__.py` — re-export the public API:
  `VerovioEngravingProvider`, `EngravedScore`, `AdapterNoteRecord`

The docstring contract at the top of today's file (identity minting,
xmlIdSeed determinism, rule-4 boundary) moves to the package
`__init__.py` docstring.

## Safety net (the point of the exercise)

Golden snapshots. `xmlIdSeed` makes loads fully deterministic, so a
serialized `EngravedScore` is a stable fingerprint:

- A small harness (suggested: `tests/golden.py` +
  `tests/test_golden_layouts.py`) serializes, per fixture: every
  element's (element_id, kind, page, system, part, staff, voice,
  onset, extent, bbox, path/text counts), all note_records, all
  warning (code, message) pairs — sorted, exact reprs, JSON.
- Fixtures: testscore, video_test, complex1, bigband1, complex3,
  pickup_min, bar_repeat_min, condense_min, tall_system_min — plus
  the option-variant loads that exercise the retry paths
  (hide_empty_staves on bigband1, condense on condense_min), since
  those branches are exactly where a botched move would hide.
- Capture baselines at R.0, BEFORE any move; commit them. Every
  subsequent commit must reproduce them byte-identically.
- Keep the goldens after the refactor as a permanent regression
  suite (they are cheap and they pin exactly what rule-5 re-derives).

## Staging (one commit-sized task each, PHASES.md format)

- **R.0 Golden harness + baselines**: build the snapshot harness,
  capture and commit baselines, full pytest green. Check: deleting a
  random element from a snapshot makes the test fail.
- **R.1 Mechanical split**: create the package; move one job per
  commit (suggested order: kinds → mei_index → records →
  decompose → attribution → identity+synthesis → provider), imports
  updated, ZERO logic edits — goldens byte-identical and pytest
  green after every commit. `verovio_adapter.py` shrinks to a shim
  and is deleted (or kept) per ruling (a).
- **R.2 Seams made explicit, minimally**: a single
  `run_pipeline`-style function in `provider.py` that names the
  post-pass order with a comment stating WHY the order is load-
  bearing; module docstrings state each stage's inputs/outputs and
  which parts of `_LoadState` it touches. No signature redesigns
  beyond what the move itself forces.
- **R.3 Tooling migration**: tests import from the new modules;
  spikes handled per ruling (b).
- **R.4 Findings pass**: work the findings list logged during
  R.1–R.3 under the behavior-change policy — category-2 hardening
  freely, category-3 fixes one per commit with golden diff + pinned
  test + baseline re-capture, flag-and-stop on anything that changes
  animation semantics or rendered output. Findings judged
  out-of-scope or too large go to BACKLOG with a one-line rationale.
- **R.5 Docs close-out**: the .md changes below; PHASES.md records
  as-built, including the findings list and each finding's fate
  (fixed / backlogged / ruled out).

Explicitly deferred (BACKLOG, not this refactor): narrowing
`_LoadState` into per-stage inputs, restructuring the
`_identity_for` onset chain into a table, any performance work.

## Suggested .md changes (apply during the refactor, not before)

- **CLAUDE.md** rule 4: "the adapter in
  `core/engraving/verovio_adapter.py`" → "the adapter package
  `core/engraving/verovio/`" (boundary wording unchanged). Package
  layout tree: expand `engraving/` to list the package modules in
  one line each.
- **ARCHITECTURE.md §3** (`core/engraving/` block): add a short
  module map of the package and the pipeline order — engrave →
  parse MEI → timemap → decompose pages → rehome strays → attribute
  ledger dashes → attribute spanner segments → flag implausible
  ties → build elements → synthesize slash/repeat — with one line on
  why the order is fixed.
- **PHASES.md**: the refactor phase section in the established
  format (the build session writes it, rulings recorded).
- **BACKLOG.md**: add the deferred items above; note the goldens as
  the standing regression net for future adapter work.

## Rulings needed from Marcus (plan session: stop for these)

(a) **Shim vs import update.** Recommendation: update all import
    sites (app, tools, join.py, tests) to the new package and delete
    `verovio_adapter.py` — a permanent shim re-exporting privates
    would freeze the old structure in place. But a temporary shim
    during R.1 is fine.
(b) **Spikes.** The two triage spikes monkeypatch adapter internals
    and will break. Recommendation: update their few patch/import
    lines (cheap); alternative: pin them as historical documents
    with a header note saying they predate the package split.
(c) **Module split approval.** The plan session verifies the map,
    proposes the final module list (merging or splitting the
    suggestion above where the code says so), and waits.

## Prompts to paste into Claude Code

Use one session per prompt; `/clear` between them. Start prompt 1 in
plan mode (Shift+Tab twice).

### Prompt 1 — plan

    Read CLAUDE.md, docs/ARCHITECTURE.md, docs/PHASES.md, and
    docs/REFACTOR_BRIEF.md. Plan the verovio_adapter refactor per
    the brief: split core/engraving/verovio_adapter.py into a
    package of pipeline-stage modules, with the golden-snapshot
    safety net built and baselined BEFORE any code moves. Verify
    the brief's map against the current file and import graph —
    don't trust it. The brief's behavior-change policy is already
    ruled — record it, don't re-open it: moves are byte-identical
    to the goldens; no-output-change hardening is free in its own
    commits; suspected defects found during the split are LOGGED,
    then fixed in the findings stage one per commit with a golden
    before/after diff and a pinning test, stopping for my ruling
    when a fix changes animation semantics or rendered output.
    Never mix a move and a fix in one commit. Other hard
    constraints: pytest green after every commit; no new
    abstractions beyond the module boundaries (no strategy
    patterns, no pipeline framework); CLAUDE.md rules 1-11 all
    stand, rule 4 boundary unchanged. This refactor does NOT touch
    the live-playback spanner reveal bug — that is a
    render/applier issue, out of scope here. Draft the refactor
    phase section for docs/PHASES.md in the established format
    (R.0 through R.5, one commit-sized task per move, each with
    its concrete check), then stop for my rulings on: (a) shim vs
    updating all import sites, (b) how the two triage spikes that
    monkeypatch adapter internals are handled, (c) your proposed
    module split. Do not build before I rule.

### Prompt 2 — build

    The verovio_adapter refactor is planned in docs/PHASES.md with
    my rulings recorded. Build it task by task in order (R.0
    through R.5), the usual way: full pytest green after EVERY
    commit; moves byte-identical to the goldens with no logic
    edits smuggled in; suspected defects logged to the findings
    list, not fixed inline. In R.4 work the findings under the
    brief's behavior-change policy: one fix per commit, golden
    diff + pinning test + baseline re-capture each, and
    flag-and-stop for my ruling on any fix that changes animation
    semantics or rendered output.

### Prompt 3 — exit + close-out

    Run the refactor exit: full pytest, the golden suite, the
    score-doctor over all testdata fixtures, and a scripted
    offscreen open+animate+export-frame run on bigband1 and
    complex1. Confirm verovio_adapter.py's fate matches ruling (a)
    and that no file under scoreanim/ imports it anymore (if
    deletion was ruled). Then close out the docs the established
    way: PHASES.md as-built including the findings list and each
    finding's fate, CLAUDE.md rule 4 path + package layout tree,
    ARCHITECTURE.md §3 module map + pipeline order, BACKLOG.md
    deferred items + backlogged findings, spikes/NOTES.md a note
    on the package split. Report the final per-module line counts
    and a summary of every behavior change that landed, with its
    golden diff.
