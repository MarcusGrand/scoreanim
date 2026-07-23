# Phase 11 planning brief — Dorico robustness (2026-07-15)

Written by a Cowork planning session, 2026-07-15. Purpose: give the
Phase 11 Claude Code session verified failure data so it plans from
facts, not guesses. The diagnosis below was reproduced against the
real files with the current build (commit c396593, 409 tests green).

## Goal

Any Dorico-exported MusicXML loads, animates, and exports. Milestone:
`testdata/complex1.musicxml` (14 single-staff parts, 3 pages, 921
notes). **Phase 11 is the stepping stone toward Phase 12**
(orchestral complex2 — see docs/PHASE12_BRIEF.md); the decomposer
and geometry fixes below were verified 2026-07-15 to be exactly what
complex2 needs to load at all, so they land here. The grace-note
join defect is diagnosed here but FIXED in Phase 12 (12.1,
order-based join) — complex2 showed it is an appoggiatura-semantics
problem, not a tolerance problem, and the fix is one rewrite, not
two.

## Diagnosed failure chain for complex1 (verified 2026-07-15)

Three defects, in load order. With fixes 1 and 2 shimmed, the file
loads fully: 3490 elements, 3 pages, 3 dropped-spanner warnings (the
"3 ties left open" import warnings — the Phase 10.3 machinery already
handles those gracefully).

1. **`bTrem` unknown SVG class** (raise at `_walk`, page 2). The file
   has one bowed tremolo (`<tremolo>`); Verovio wraps the note in
   `<g class="bTrem">` containing the id-bearing `note`. Treating
   bTrem as a container class was sufficient in the shim. The MEI
   `fTrem` twin (two-note measured tremolo) is not in this file but is
   the same family — cover both (complex2 has 85 tremolos). Ruling to
   confirm: tremolo stroke ink animates with its owning note (it
   lives inside the note/stem groups, so this may fall out for free).

   Two more coverage gaps, found on complex2 (2026-07-15) and
   scheduled HERE because they are the same decomposer/geometry
   class of fix — pin them with synthetic tests plus a
   complex2-loads-under-the-doctor smoke:

   1b. **`beamSpan` unknown SVG class** (cross-measure/cross-staff
   beams). Shim mapped it to the beam kind; verify segment/onset
   behavior like beam.

   1c. **`rotate` SVG transforms crash the geometry walker**
   (`svg_geom.parse_transform` raises "unsupported transform
   'rotate'"; complex2 page 5 carries rotate(-90 …), likely vertical
   text). `Affine` already stores the full 2×3 matrix; fix =
   parse rotate into the matrix + rewrite `Affine.apply_rect` to
   map all four corners (exact for 90° multiples, conservative
   otherwise), and drop the "Verovio never rotates" assumption
   from the svg_geom docstring — complex2 disproves it.

2. **Ledger-dash attribution misses `mRest` owners** (raise at
   `_attribute_ledger_dashes`, page 3 m13 staff 8, Trombone 1). A
   two-voice measure displaces a whole-bar rest (`mRest`, id m16om1hq)
   above the staff onto a ledger dash at x=1277; the Phase 10.2
   candidate pool has tiers for `note` and `rest` but not `mRest`.
   Fix: add mRest to the rest tier (same geometry rule). Same bug
   family as Phase 10.2's m12 fix — the pool was underinclusive.

3. **Grace notes fail the model↔layout join** — 899/921 matched, 22
   unmatched on each side, and they pair 1:1: every unmatched pair is
   a grace note where music21 reports the integer beat (e.g. 28.0)
   while Verovio's timemap reports the fractional grace qstamp
   (28.0957…). The source has 26 `<grace>` notes.
   **RESCHEDULED → Phase 12 task 12.1** (2026-07-15): complex2
   showed the full shape — appoggiaturas shift every subsequent
   onset in their measure (1882/9546 matched there), so the join
   needs an order-based rewrite, not a grace tolerance. One fix in
   Phase 12 covers both files. Phase 11's exit accepts complex1
   with exactly these 22 unmatched (pin the count so regressions
   still surface); complete-join for complex1 moves to the Phase 12
   exit.

Also present in complex1 but apparently already covered (verify in
the exit run, don't rebuild): 26 tuplets, 16 unpitched percussion
notes, 6 transposed parts, grace notes rendering, no slash regions,
no part-groups.

## Proposed Phase 11 tasks

- **11.0 Score-doctor CLI** (`python -m scoreanim.tools.check_score
  <file-or-dir>`): headless load of any MusicXML; prints either
  PASS (element/page/note counts, warning census, join completeness)
  or the exact failure point. Batch mode over a folder. This is the
  engine for the "any Dorico file" goal: every new score becomes a
  one-command triage instead of an app crash, and the fix loop
  (doctor → smallest fix → fixture) becomes routine.
- **11.1 Decomposer/geometry coverage**: bTrem/fTrem + beamSpan in
  the decomposer (stroke ink animates with the owning note); rotate
  transforms in svg_geom (corner-mapped apply_rect).
- **11.2 mRest ledger tier**: extend the Phase 10.2 pool; existing
  fixtures byte-identical by construction (new tier consulted only on
  miss).
- **11.3 Join gap pinned, not fixed**: complex1 joins 899/921; pin
  the 22 unmatched as exactly the grace set (the order-based join
  rewrite is Phase 12.1 — see the brief there).
- **11.4 Graceful degradation** (RULED by Marcus, 2026-07-15, in the
  Cowork planning session): an unknown drawable SVG class no longer
  fails the load in the app path — it mints a static OTHER element +
  LoadWarning "unknown-class" (never silent — the status bar counts
  it, stderr names the class). Tests stay strict: a fail-fast flag
  (default on under pytest / the doctor's --strict) preserves the
  Phase 10 discipline so coverage gaps keep surfacing loudly in
  development.
- **11.5 Fixture promotion + exit**: complex1 joins the permanent
  fixtures (census pins: 3490 elements, 3 pages, 921 notes, join
  899/921 with the 22 graces pinned, 3 dropped-spanner warnings);
  scripted exit run on the offscreen MainWindow: open, animate,
  export a frame.

Exit criteria: complex1 loads, plays, and exports cleanly (join gap
= exactly the pinned grace set); the doctor reports PASS for the
four current fixtures AND "loads with N system-overflow warnings"
for complex2 (the overflow is Phase 12's problem — Phase 11 only
has to get complex2 through decomposition); pytest green.

## Suggested .md changes (apply during Phase 11, not before)

- **PHASES.md**: append the Phase 11 section (the build session
  writes it in the established format, rulings recorded).
- **CLAUDE.md**: add complex1.musicxml to the testdata note; if
  ruling 11.4 lands as graceful degradation, add it to the
  load-warning rule text ("unknown ink degrades to a warned static
  element in the app path; tests stay strict").
- **ARCHITECTURE.md §3**: adapter ruling for tremolos + the join's
  grace rule; extend the LoadWarning code list ("unknown-class" if
  11.4 lands).
- **BACKLOG.md**: add "arbitrary-exporter MusicXML robustness"
  progress note; park tremolo animation polish there if any is
  deferred.

## Prompts to paste into Claude Code

Use one session per prompt; `/clear` between them. Start prompt 1 in
plan mode (Shift+Tab twice) so it plans before touching code.

### Prompt 1 — plan review

    Read CLAUDE.md, docs/ARCHITECTURE.md, docs/PHASES.md, and
    docs/PHASE11_BRIEF.md. Plan Phase 11 (Dorico robustness,
    milestone testdata/complex1.musicxml) following the brief. First
    write a triage spike (spikes/complex1_triage.py, kept, in the
    style of video_test_triage.py) that reproduces the brief's three
    failures in order and confirms the shim results — do not trust
    the brief, verify it. Ruling 11.4 (graceful degradation with a
    strict test flag) is already made — record it, don't re-open it.
    Then draft the Phase 11 section for docs/PHASES.md in the
    established format and stop for my rulings on: (a) tremolo
    stroke animation, (b) the grace-join mechanism. Do not build
    anything beyond the spike before I rule.

### Prompt 2 — build

    Phase 11 is planned in docs/PHASES.md with my rulings recorded.
    Build it task by task in order (11.0 through 11.5), the usual
    way: headless tests as you go, each task ends with its concrete
    check, existing fixtures byte-identical unless the plan says
    otherwise, commit after each task. Flag-and-stop if anything in
    the plan doesn't survive contact with reality.

### Prompt 3 — exit + close-out

    Run the Phase 11 exit: full pytest, the score-doctor over all
    four fixtures, and a scripted offscreen exit run on complex1
    (open, animate, export a frame). Then close out the docs the
    established way: PHASES.md records as-built, ARCHITECTURE.md
    adapter rulings updated, BACKLOG.md updated, spikes/NOTES.md
    gets the Phase 11 findings. Give me a review artifact with
    complex1's three rendered pages.

### After Phase 11 — the ongoing loop for new scores

For each new Dorico export that fails (e.g. the future complex2):

    Run python -m scoreanim.tools.check_score testdata/<file>.musicxml
    and diagnose the failure chain. Propose the smallest fix
    consistent with CLAUDE.md rules 1-10, spike first if Verovio
    behavior is uncertain, and stop for my ruling before building.
