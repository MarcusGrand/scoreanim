# Live-timing brief — early/late reveals on complex3 (2026-07-22)

Written by a Cowork planning session, 2026-07-22, after reading the
current live path (render/animate.py, render/items.py,
render/scene.py, core/animation/reveal.py, core/animation/schedule.py
— including the grow-with-playhead revision that landed TODAY,
2026-07-22, in schedule rule 1 / reveal anchors). Purpose: give the
diagnosis session verified code facts and a harness design that makes
"live-only" bugs deterministic and testable.

## Symptom census (Marcus, 2026-07-22, complex3, LIVE playback)

1. Slurs/ties still appear before their music is reached (the known
   early-reveal leak, previously seen on bigband1).
2. Notes in certain staves/measures appear LATE — they light when the
   playhead is already past them, sometimes by measures.
3. Key signatures and meter signatures sometimes appear ~2 measures
   late.
4. Unknown whether video export shows the same (untested).

## The governing principle — why "it only happens live" is testable

CLAUDE.md rule 2: element state is a pure function state(t). So every
live symptom must decompose into exactly one of three layers, each
deterministically reproducible offscreen (QT_QPA_PLATFORM=offscreen):

- **L0 — the DATA is wrong**: a trigger beat, reveal anchor, onset,
  or curve key is wrong before Qt is ever involved. Pure Python,
  plain pytest.
- **L1 — the APPLICATION is wrong**: the scene after a fresh
  `refresh(t)` disagrees with the pure expectation computed from the
  schedule + curves at that same t. Offscreen Qt, still fully
  deterministic.
- **L2 — the application is SEQUENCE-DEPENDENT**: ticking
  `apply_at(t0), apply_at(t1), …, apply_at(T)` (what live playback
  actually does, ~60 calls/s) leaves the scene in a different state
  than one fresh `refresh(T)`. This is the layer whole-page render
  tests can never see — and it is still deterministic: same tick
  sequence, same result, no audio needed.

Whole-page render checks only ever test L1 at one t. The harness
below tests all three, on any fixture, in CI.

## Verified code facts (read 2026-07-22 — verify against head, then
treat as the suspect list)

**F1 — a curve-less spanner is silently VISIBLE FROM t=0.** This is
the strongest early-reveal candidate and it is silent by
construction: `RevealPathItem._clip_right` initializes to None,
which paint() treats as FULLY REVEALED (render/items.py). The only
thing that ever clips it is `AnimationApplier._apply_reveal`, which
iterates the resolved curves and fans edges out to
`_revealed_by_key[(curve.system, curve.part)]`. Consequence: a
revealed-kind item whose `(item.system, identity.part)` key matches
NO curve never receives ANY edge — it sits fully painted from load,
which reads exactly as "slur/tie from later music already showing".
`build_reveal_tracks` only creates a track for (system, part) keys
that have ANCHOR_KINDS elements with part AND onset in that system.
Ways a revealed item can miss: its part resolved to None at identity
minting (spanner start note absent from the MEI note table, staff
attr missing); its part has no anchor-kind elements with onsets in
that system (e.g. rests absent from the timemap there); or its
item.system disagrees with the curve's system. The diagnosis is one
audit (D1 below); the fix direction is to invert the default
(hidden until an edge arrives) + fail loud on curve-less keys — but
diagnose first.

**F2 — the applier silently drops schedule ids missing from the
scene.** `AnimationApplier.__init__`: `items[eid] ... if eid in
items`. Any schedule↔scene ElementId mismatch produces elements that
never receive their trigger — invisible in all current tests.

**F3 — a notehead's LATE appearance points at the join, not the
applier.** Since today's grow-with-playhead revision, a notehead's
trigger is its OWN notated onset via the joined ScoreNote
(`note_trigger[eid] = note.onset`). If the order-based join matches
a layout notehead to the WRONG ScoreNote (complex3: X0 pickup,
appoggiatura onset shifts), the note fires at the matched note's
onset — off-by-measure(s), clustered in particular staves/measures.
That is pure data (L0), fully headless-testable. Note also that
elements NOT in the join mapping and not rests resolve through the
group table keyed (part, staff, voice, quantized onset) with
fallback to own onset — a stale/missed group key also shifts timing.

**F4 — keysig/meter onsets are measure-start fallbacks from SVG
nesting.** Their onset = `measure_start[acc.measure]` where
acc.measure is the MEI ordinal of the SVG <measure> group the glyph
nests in. "Two measures late" therefore points at attribution (which
measure group Verovio nests a mid-score keySig/meterSig change in —
possibly the cautionary vs the change measure) or at a
measure-ordinal mapping slip on the X0-pickup file. Also L0,
headless.

**F5 — sequence-dependence candidates for L2** (only if L0/L1 come
back clean for a symptom): the diff-apply cursor logic in
`apply_at`; `_last_edges` value-caching in `_apply_reveal`; the
lazily cached `_inverse` scene transform in
`RevealPathItem.set_clip_right` (stale if a sceneTransform ever
changes after first clip); `_apply_window`'s re-evaluation range.

## D — the diagnosis harness (build this FIRST, fix nothing yet)

One offscreen tool, `scoreanim/tools/live_oracle.py` (doctor-style
CLI: any fixture path; plus a fast pytest subset over testscore +
complex3 + bigband1). Build ScoreScenes + AnimationApplier exactly
as main_window does. Four checks:

- **D1 (L0) curve audit**: every revealed-kind item's
  (system, part) key must match a resolved curve. Report violators:
  element_id, kind, system, part, bbox — these are visible-from-t0
  right now. Also report every schedule eid missing from the scene
  item map and vice versa (F2).
- **D2 (L0) trigger audit**: per animated element, report
  |trigger_beats − identity.onset| where it exceeds a beat, grouped
  by (part, staff, measure) — misjoins cluster (F3). For
  KEY_SIG/METER_SIG/CLEF: report onset vs the start of the measure
  their SVG nesting claims, and vs the measure their musical change
  actually belongs to per the MEI scoreDef stream (F4).
- **D3 (L1) fresh-state oracle**: for a time grid (every measure
  downbeat ±ε, plus every trigger second ±ε), `refresh(t)` and
  compare each item's observable state — opacity, and for reveal
  children (clip_right, hidden) — against the pure expectation
  computed directly from element_state / reveal_x. Report diffs.
- **D4 (L2) live-tick differential**: two identical scene+applier
  builds; tick A with apply_at over a dense forward grid (include a
  couple of backward seeks — that's what scrubbing does), fresh-
  refresh B at checkpoint times; compare full observable state at
  each checkpoint. On divergence, bisect the tick sequence to the
  first diverging tick and report the culpable items. Run STEPPED
  and CONTINUOUS both.

Exit of the diagnosis phase: a findings table — symptom → layer →
named mechanism, each with the element ids that prove it — and
D1–D4 wired into pytest so the fix phase has regression pins from
day one. NO fixes in this phase; flag-and-stop per finding.

## Fix phase (after Marcus rules on the findings)

One session per confirmed mechanism, smallest fix consistent with
CLAUDE.md rules 1–11; every fix must flip a now-failing D-check to
green and keep the others green. Expected candidates, pending
findings: default-hidden reveal children + loud curve-less-key
warning (inverts F1's silent failure); join corrections for the
misjoined clusters; keysig/meter measure attribution; any L2
sequence bug found by D4. The oracle stays as a permanent tool
(like the score-doctor) — every future "it looks wrong live" starts
with one command instead of an argument about what's testable.

## Relation to other work in flight

- The verovio_adapter refactor (docs/REFACTOR_BRIEF.md) is
  INDEPENDENT: run this diagnosis first — its findings tell you
  whether adapter-side data (join, measure attribution) or the live
  path is at fault, and the refactor's golden snapshots will then
  pin whatever the fixes change. Do not mix the sessions.
- The 2026-07-22 grow-with-playhead revision (schedule rule 1,
  reveal anchors) landed BEFORE this brief; the harness is built on
  top of it, and D3/D4 will confirm whether it behaves as intended
  under live ticking.

## Prompts to paste into Claude Code

One session per prompt; `/clear` between them. Start prompt 1 in
plan mode (Shift+Tab twice).

### Prompt 1 — diagnose (build the oracle, fix nothing)

    Read CLAUDE.md, docs/ARCHITECTURE.md, docs/PHASES.md, and
    docs/LIVE_TIMING_BRIEF.md. Live playback on
    testdata/complex3.musicxml shows three timing symptoms (census
    in the brief): spanners revealing early, notes in certain
    staves/measures lighting late, key/meter signatures lighting ~2
    measures late. Your job this session is DIAGNOSIS ONLY — build
    the live-oracle harness the brief specifies
    (scoreanim/tools/live_oracle.py, offscreen, doctor-style CLI +
    a pytest subset; checks D1–D4) and run it on complex3, bigband1,
    and testscore. First verify the brief's code facts F1–F5
    against the current head — the schedule/reveal revision from
    2026-07-22 is already in, don't re-litigate it. Then report the
    findings table: each symptom → layer (L0 data / L1 application
    / L2 sequence-dependence) → named mechanism → proving element
    ids, including D1's list of revealed items with no matching
    reveal curve (the brief's prime early-reveal suspect) and D2's
    misjoin clusters. Wire the checks into pytest as
    currently-failing tests marked xfail with the finding they pin.
    Fix NOTHING — no behavior changes this session; stop and
    present the findings for my rulings.

### Prompt 2 — fix (one mechanism per session, after rulings)

    Read docs/LIVE_TIMING_BRIEF.md and the findings recorded in
    docs/PHASES.md. Fix ONLY the mechanism I name below, the
    smallest way consistent with CLAUDE.md rules 1-11: flip its
    xfail oracle test to a passing regression pin, keep every other
    D-check and the full pytest green, and run the live-oracle CLI
    on all fixtures before and after, reporting the diff. If the
    fix wants to change behavior beyond the named mechanism,
    flag-and-stop.

    Mechanism to fix: <paste the finding id from the diagnosis>

### After both — the standing rule

    Any future "it looks wrong in live playback" report starts
    with: python -m scoreanim.tools.live_oracle testdata/<file> —
    and its output names the layer and the elements before anyone
    guesses at causes.
