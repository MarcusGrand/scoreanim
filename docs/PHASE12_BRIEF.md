# Phase 12 planning brief — Orchestral scores (complex2) (2026-07-15)

Written by a Cowork planning session, 2026-07-15, same session as
docs/PHASE11_BRIEF.md. **Phase 11 is the stepping stone and comes
first** — its fixes are prerequisites here. End goal, ruled by Marcus:
`testdata/complex2.musicxml` (full orchestral, transposed, condensed
in Dorico, bar repeats; companion `complex2.pdf`) loads, renders
usably, animates, and exports — with the user prompted at load time
to make the choices (condensing, bracketing, hiding) the program
needs to lay the score out properly.

## What complex2 is (verified against the file)

36 parts / 37 staves (Synth P27 is 2-staff), 159 measures, 5.7 MB.
Full winds/brass/percussion/choir (584 lyrics)/strings. 11
transposed parts (A clarinets, F horns, B♭ trumpets). 19 encoded
page breaks, ZERO system breaks — one system per page, the normal
orchestral shape, so rule 7 is satisfied vacuously per system. 6
`<measure-repeat>` + 40 `<slash>` measure-styles, 85 tremolos, 30
graces, 220 tuplets, 220 unpitched notes, 26 arpeggios, 20 trills,
38 fermatas.

The Dorico PDF is CONDENSED; MusicXML export carries no condensing
(verified against Steinberg docs/forum 2026-07-15 — condensing is
layout-time and does not export). So the file arrives as 37
uncondensed staves and any condensed look must be reconstructed
in-app from user choices.

## Diagnosed state with the current build (2026-07-15)

With four shims applied (all scheduled into Phase 11 — see the
updated PHASE11_BRIEF), complex2 loads end-to-end in ~20 s: 42,530
elements, 20 pages, warnings: 20× system-overflow, 6×
dropped-spanner, 1× repaginated. Remaining problems, in order of
severity:

1. **Every system overflows the page** (20/20 "system-overflow").
   A 37-staff system is taller than the page; repagination cannot
   fix a single system that exceeds one page. Verovio also warns
   "justification highly compressed" on every system. An
   uncondensed render is structurally unusable — the user MUST
   reduce staff count (condense and/or hide) for this score to lay
   out. This is the core Phase 12 problem.

2. **The model↔layout join collapses: 1882/9546 matched.** Root
   cause verified on flute (non-transposing, so not a pitch issue):
   complex2's graces are APPOGGIATURAS — Verovio's timemap gives
   the grace its face value and delays the main note (score 43.0 →
   layout 43.5; 45.5 → 46.5), while music21 keeps notated offsets.
   Every note after a grace in its measure misses the exact-onset
   join key. Same family as complex1's 22 unmatched acciaccaturas,
   scaled up. Fix direction: join within (part, measure, voice) by
   (pitch, document order) with onset as tiebreak, not exact key —
   the `order` field already exists. Separate ruling needed on
   TRIGGERS: Verovio's performance-shaped qstamp (main note delayed)
   is arguably the RIGHT animation time; the notated beat is not
   when the note sounds. Decide at plan review; keep the seam so
   both sides stay derivable.

3. **Bar repeats don't animate.** `<measure-repeat>` regions render
   (Verovio draws the mRpt symbol) but produce no animated elements
   — the kind census has no repeat kind, and like slash regions
   they emit no notes. Needs adapter synthesis in the slash-region
   shape (rule 10 family): one element per repeated measure (or per
   beat — ruling), onsets from the timemap, so bar-repeat measures
   light up like slash measures do.

4. **Scale**: 42.5k elements (video_test: 4.7k). Load ~20 s + scene
   build. Budget a perf check (load time, scene build, tick cost on
   a dense page); no optimization work unless it misses targets.

## The Phase 12 feature: load-time setup (user choices)

Ruled by Marcus (2026-07-15): on load, the user is prompted to make
the choices the program needs — which staves to condense, bracket,
hide. Design constraints from the existing architecture:

- **All choices are document intent** (rule 5): a `condense_groups`
  field (schema v5) alongside the existing `staff_groups`,
  `hide_empty_staves`, `text_overrides`. Layout re-derives.
- **Condensing = prep-seam rewrite** (the Phase 8/9 pattern):
  merging N contiguous like parts into one part with one voice per
  source part in the canonical MusicXML BEFORE Verovio, with a
  combined label ("Flute 1.2"). Verovio cannot condense from
  MusicXML; this is the only viable route (verified). v1 semantics
  deliberately simple: shared staff, one voice per player, no a2
  unison collapse, no per-passage divisi logic. Needs a spike FIRST
  (spikes/condense_prep.py): does a naive two-voice merge of real
  Dorico parts render acceptably (stems, rests, collisions)?
  Expect ugliness on divergent rhythms — the user chooses which
  parts condense, so they can pick sane pairs.
- **The setup dialog** appears when opening a score whose flat
  render overflows (the load already measures this — reuse the
  warning) or on Parts → Score Setup…: per-part list with
  condense-group, staff-group (existing), and hide-empty-staves
  controls; OK executes the commands (one undo step or a macro
  command — ruling) and re-engraves once via the existing
  diff-guard path. Everything already exists for groups/hide;
  condense adds the third control.
- **ElementIds shift when condensing changes** (part identity
  changes are engraving inputs, like part renames). Overrides keyed
  to merged parts re-derive; accepted staleness per the existing
  override policy.

## Proposed Phase 12 tasks

- **12.0 Spikes** (kept): (a) condense-merge prep rewrite on two
  complex2 wind parts → render, judge; (b) measure-repeat census —
  what Verovio draws and what the timemap says for mRpt regions;
  (c) appoggiatura timemap semantics pinned (grace steal direction,
  chord graces). Findings to spikes/NOTES.md.
- **12.1 Order-based join**: rewrite join_notes matching within
  (part, measure, voice) by (pitch, order), onset tiebreak;
  complex1 AND complex2 join complete; testscore/video byte-
  identical mappings pinned. Trigger-time ruling recorded.
- **12.2 Bar-repeat synthesis**: mRpt elements animate (slash-
  region pattern); complex2's 6 regions light up on the beat.
- **12.3 Condense at the prep seam**: PartCondenseSpec + rewrite +
  label merge; doc field + Add/Edit/RemoveCondenseGroup commands
  (schema v5, one bump with any other planned v5 fields); id
  behavior pinned.
- **12.4 Score Setup dialog**: triggered on overflow at load + on
  demand; condense/bracket/hide controls; one re-engrave on OK;
  undoable.
- **12.5 Scale + exit**: perf numbers recorded; complex2 fixture
  promotion (censuses pinned); scripted exit — open complex2, make
  setup choices until nothing overflows, animate, export frames;
  visual review against complex2.pdf (condensed reference — expect
  layout differences where the user's choices differ from Dorico's
  condensing; fidelity target is "usable and clean", not
  PDF-identical).

Exit criteria: complex2 opens with the setup dialog, and with
reasonable choices renders with zero system-overflow warnings,
animates in sync, and exports; join complete on all six fixtures;
pytest green.

## Suggested .md changes (during the build, per the usual close-out)

- CLAUDE.md: rule-10 family gains bar repeats; testdata note gains
  complex2 + PDF; a new rule if condensing lands ("condensing is a
  prep-seam engraving input; the doc stores condense groups only").
- ARCHITECTURE.md: §3 adapter rulings for mRpt synthesis +
  appoggiatura timemap semantics; §4 schema v5; §7 Score Setup
  dialog; known-risks entry for orchestral scale.
- PHASES.md: Phase 12 section in the established format.
- BACKLOG.md: divisi/a2 condensing sophistication; per-passage
  condensing changes; anything deferred from the spike findings.

## Prompts to paste into Claude Code

Run these AFTER Phase 11 is closed. One session per prompt, plan
mode for prompt 1, /clear between.

### Prompt 1 — plan review

    Read CLAUDE.md, docs/ARCHITECTURE.md, docs/PHASES.md,
    docs/PHASE11_BRIEF.md, and docs/PHASE12_BRIEF.md. Phase 11 is
    closed; plan Phase 12 (orchestral robustness, end goal
    testdata/complex2.musicxml with its companion PDF) following
    the Phase 12 brief. Start with the 12.0 spikes — condense-merge
    prep rewrite, measure-repeat census, appoggiatura timemap
    semantics — verifying the brief's diagnosis rather than
    trusting it. Then draft the Phase 12 section for docs/PHASES.md
    and stop for my rulings on: (a) trigger timing for notes after
    appoggiaturas (Verovio performance qstamp vs notated beat), (b)
    bar-repeat element granularity (per measure vs per beat), (c)
    setup-dialog command shape (macro vs per-action), (d) anything
    the condense spike shows that changes the plan. Do not build
    before I rule.

### Prompt 2 — build

    Phase 12 is planned in docs/PHASES.md with my rulings recorded.
    Build it task by task (12.1 through 12.5): headless tests as
    you go, every existing fixture's pinned behavior unchanged
    unless the plan says otherwise, commit per task, flag-and-stop
    when reality disagrees with the plan.

### Prompt 3 — exit + close-out

    Run the Phase 12 exit: full pytest; score-doctor over all
    fixtures; scripted offscreen run on complex2 — open, apply a
    sensible setup (condense wind/brass pairs, hide empty staves),
    verify zero system-overflow, animate, export frames. Close out
    the docs the established way and give me a review artifact:
    rendered complex2 pages next to the corresponding complex2.pdf
    pages, plus the bar-repeat and appoggiatura measures up close.
