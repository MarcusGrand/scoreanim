# M6 — Pages: build brief

Scope authority is `docs/ROADMAP.md` §M6. This file is how it gets built.
Written after the audit and the spike, before any feature code.

Status: **ruled 2026-07-28 (Marcus); building.** §4's thirteen decisions
(D0–D12) are all ruled **as recommended**, with the two standing riders
recorded in §4. Schema goes to **v9**; the ROADMAP rule-7 amendment is
applied to CLAUDE.md at M6.8 with the ruling date (the M5.6 pattern),
extended with what D3's collision ruling settled.

M6 pairs two things M5 left behind: page-break authoring, deferred in
ROADMAP's closing section "until M5 proves the pattern", and BACKLOG
17's left layout zone, deferred "until more than one action needs a
home". Marcus ruled both into one milestone on 2026-07-28.

---

## 0. Baseline

- `beta/m6-pages`, branched off `main` at **f473a10** (one docs commit
  past the M5 merge `d912040`, tagged `v0.2-beta.4` at `eddada0`).
- Suite at branch point: **960 passed, 1 xfailed**.
- Schema at branch point: **v8**; M6 takes **v9**.
- `spikes/page_breaks.py` is the measurement, kept. Sections A–F; run
  `python spikes/page_breaks.py` for everything, or name sections
  (`python spikes/page_breaks.py b d f`). B and E are the slow ones
  (complex2/complex3 condensing and scale-to-fit).

---

## 1. What already exists (audit)

Re-read against the tree on 2026-07-28.

### 1.1 The prep seam already has M6's twin, and its adversary

`core/score/musicxml_rewrite.py` holds both halves of M6's problem:

| pass | what it does | why it matters to M6 |
|---|---|---|
| `_apply_system_breaks` | writes `<print new-system>` from **stored** sparse intent; a delta, never strips | the pass M6's twin copies |
| `_repaginate` | **strips every** encoded `new-page` and asserts a **derived** plan | the pass M6's twin collides with |

`prepare()` runs them in that order, with the reason commented: user
break intent first, never-clip repagination on top. M5 could add its pass
upstream of `_repaginate` because `_repaginate` does not touch
`new-system`. **M6 cannot**, because `_repaginate` owns the exact
attribute M6 wants to author. §3.2 measures what that costs.

### 1.2 `page_of_measure` needs no adapter change

M5's D4 had to expose `EngravedScore.system_of_measure` so the toggle
could ask "does this measure already start a system". The page twin is
**free**: `LoadedScore` already carries `system_of_measure` *and*
`band_by_system` (`SystemBand.page`), so

```python
page_of_measure[m] = band_by_system[system_of_measure[m]].page
```

is a pure derivation over data the loader already hands the window. No
adapter change, no golden movement, no new field. The spike uses exactly
this derivation (`pages_of_measure`, `page_starts`), so what the brief
measures is what the app can compute.

### 1.3 The M5.2 trap, now times two

`provider.load_detailed` calls `prepare()` three times: the
hide-unavailable retry re-engraves the **same** prep (free — it inherits
whatever the first prep carried), and the **repagination** and
**scale-to-fit** retries re-prepare and must be handed every override map
explicitly. M5 pinned all three for `system_breaks`. Every one of those
pins now needs a page twin, and the two re-preparing calls each need a
second argument.

### 1.4 The M5 UI spine takes a third action without reshaping

`ui/break_action.py` (124 lines) already owns two QActions with one
`bind()`, one `sync()` and one `_execute()`; `PartsMenu.set_break_actions
(*actions)` is already variadic; `MainWindow` already loops over
`break_action.actions` to register shortcuts. A third action costs a
constructor block and one policy call. `_break_anchor` already
generalizes to "the lowest of at most two changed ordinals" and its
`1 <= n <= 2` bound is documented as "what a gesture can write".

### 1.5 The dock pattern the layout zone copies

`Inspector` is the template: `QDockWidget` subclass, `setObjectName`
(saveState identity), `NoDockWidgetFeatures`, one allowed area,
`toggleViewAction()` picked up by `menus.py` into the View menu.
`window_state.py` persists **all** docks through a single
`window.saveState(_STATE_VERSION)` / `restoreState` pair, so a third dock
needs no new persistence code. `_STATE_VERSION = 0` carries the comment
"bump to discard stored dock layouts on upgrade" — bears on D10.

### 1.6 The command idiom is settled

`SetSystemBreak(ordinal, mode, also)` is the fat-apply idiom's third use
(after `ApplyScoreSetup` and `SetElementStyle.segments`), validates
`ordinal >= 1` only, deliberately does not know the engraved layout, and
`describe()` follows the M3.5 rule. `SetPageBreak` has a template to copy
line for line.

---

## 2. What does not exist

- No `page_break_overrides`, no `PageBreak` vocabulary, no `SetPageBreak`,
  no `new-page` pass driven by stored intent. All new.
- **No way for user intent to reach `plan_page_breaks`.** Its signature is
  `(bands, page_height, first_measure_by_system)` — a pure derived plan
  with no input channel for "the user asked for a page here". D1 needs
  one.
- **No left dock, and no `ui/` module that owns a button surface over
  existing QActions.** The layout zone is new UI, though not new
  semantics.
- Still no stage context menu (M5's §2 finding, unchanged).

---

## 3. Measurements (`spikes/page_breaks.py`)

The spike monkeypatches `prepare` (and, for one candidate design,
`plan_page_breaks`) so the **whole existing pipeline** — all three
`prepare()` calls, the hide-unavailable retry, repagination,
hide-empty-staves, condensing, scale-to-fit — runs against the edited
page-break set. `testscore` loads strict; `bigband1`, `complex2`,
`complex3` go through the app path (`strict=False`, the `gliss` caveat).

Every load is checked for **clipped ink** (`clipped()`: any system band
running past the bottom of its page). **It came back empty in every
single case in every section.** Never-clip is not at risk in anything
below; the question is only ever *whose* page plan wins.

### 3.0 The three candidate designs, named

The spike measures three ways of composing authored page intent with
`_repaginate`, as `mode=` to its `load()`:

- **`pre`** — the naive M5 twin: the page pass runs where the system pass
  runs, upstream of `_repaginate`.
- **`post`** — the page pass runs over `_repaginate`'s output, so user
  intent always wins.
- **`plan`** — user intent is an **input** to `plan_page_breaks`: forced
  ordinals are unioned into the never-clip plan, suppressed ones dropped
  from it.

### 3.1 Verovio honors authored page breaks (section A, testscore)

Baseline: 3 pages, page starts `(1, 5, 13)`, systems
`{1:(1,4), 2:(5,8), 3:(9,12), 4:(13,16), 5:(17,19)}`. Encoded `<print>`
on part 1: **m5 and m13 are `new-page="yes"` ONLY; m9 and m17 are
`new-system="yes"`.**

| case | result | honored |
|---|---|---|
| A1 FORCE page at m3 (mid-system) | 4 pages, starts `(1,3,5,13)`, 5→6 systems | **yes** |
| A2 FORCE page at m9 (already a system start) | 4 pages, starts `(1,5,9,13)`, systems unchanged | **yes** |
| A3 SUPPRESS encoded page at m5 | 3 pages, starts `(1,9,17)`, **systems 5→3** | yes, plus damage |
| A4 SUPPRESS encoded page at m13 | 2 pages, starts `(1,9)`, **systems 5→3** | yes, plus damage |
| A5 SUPPRESS at m9 (no encoded page) | identical to baseline | inert |
| A6 FORCE m3 + SUPPRESS m13 | starts `(1,5,17)`, both applied | **yes** |
| A7 FORCE past the end (ordinal 20 of 19) | identical to baseline | silently inert |

Nothing clipped anywhere. A7 reproduces M5's F1 exactly, so D10's
inert-warning machinery has the same job to do.

**A3/A4 are the finding of this section, and it is not about
repagination.** Dorico encodes those page breaks **page-only** — m5 and
m13 carry `new-page="yes"` and no `new-system`. So clearing `new-page`
clears the measure's *only* break marker and the **system break vanishes
with it**: systems 1+2 merge, and 3+4 merge. The user asked "don't start
a page here" and was given "don't start a system here either".

This is the exact mirror of M5's D7 (where suppressing a *system* break
had to clear a coincident `new-page`, or the suppression was a lie), and
it wants the mirror answer: **a page SUPPRESS must assert
`new-system="yes"`** to keep the system break the page break implied.
See D3.

### 3.2 User FORCE vs never-clip repagination (section B) — the sharp one

**B0, which fixtures repaginate at baseline:** complex2 and complex3 do
(`repaginated` + `scaled-to-fit`); testscore, bigband1 and
tall_system_min do not. So the collision is only reachable on an
overflowing score — or on a score a *system* edit pushes into overflow,
which is what M5 made possible.

**B1 — does a forced page break survive a load that repaginates?**
Forced ordinals were chosen so that none already starts a page (a probe
on an existing page start is vacuous):

| fixture | `pre` | `post` | `plan` |
|---|---|---|---|
| complex3, page FORCE m8 | honored | honored | honored |
| complex2, page FORCE m6 | honored | honored | honored |
| **testscore + system FORCE m19, page FORCE m3** | **LOST** | honored | honored |

**B3 catches the loss in the act.** Spying on `_repaginate` for that row:

```
new-page before=[3, 5, 13]   plan=(5, 13, 19)   after=[5, 13, 19]
user's forced page at m3 survived: False
```

The user's m3 goes in and does not come out. The mechanism is exactly
`_repaginate`'s strip-and-re-assert, and it fires **only when the
re-derived plan diverges from the encoded set** — which is why complex2
and complex3 pass: their plans happen to reproduce their own page starts
plus the new one. That is BACKLOG 16's latency condition, one level up,
and it means **`pre` fails rarely and silently**, which is worse than
failing often.

**B2 — does a SUPPRESS that creates overflow get overridden?** Suppress
*every* encoded page break, so the score piles onto one page:

| fixture | result (all three designs identical) |
|---|---|
| testscore (suppress 5, 13) | 2 pages, starts `(1,9)`, `repaginated`, **nothing clipped** |
| bigband1 (suppress 12, 20) | 3 pages, starts `(1,14,23)`, `repaginated`, **nothing clipped** |
| complex3 (suppress all 20) | **1 page**, `scaled-to-fit`, **nothing clipped** |

Never-clip wins cleanly in every case, and — the detail that matters —
**no suppressed ordinal came back**: the planner re-broke the score
*elsewhere* (5,13 → 9; 12,20 → 14,23). So a suppression is honored *at
its own ordinal* even when the page count is re-derived around it. The
user is never told "no"; they are told "yes, and here is where the pages
fell instead". complex3's row is the extreme: suppressing all twenty page
breaks yields one enormous scaled-down page. Legal, useless, and
unclipped — the guarantee holds even when the request is silly.

### 3.3 Id and beat stability (section C, testscore) — rule 12 holds

| | FORCE page m3 | SUPPRESS page m5 |
|---|---|---|
| measures with byte-identical id sets | **18/19** (only m3) | 14/19 (m4,5,8,9,13) |
| triggers | 89 → 89 | 89 → 89 |
| timemap `score_end` | 70.0 → 70.0 | 70.0 → 70.0 |
| shared ids with a changed beat | **0** | 6 |
| reveal tracks | 35 → 42 | 35 → 21 |
| non-monotonic reveal edge x | 0 | 0 |

`score_end` and the trigger count are **identical** in both directions —
the rule-12 result that matters: the timemap is a performance axis and a
page break is a layout choice. The id differences are the same two
mechanisms M5 measured: system-start restatement furniture (m3 *gains*
`clef:0`/`key_sig:0` per part; m4 *loses* its `meter_sig:0` courtesy
signature when it stops ending a system) and `ledger_lines` id re-use in
re-laid-out measures. The 6 changed beats are all `LEDGER_LINES`, none is
a notehead, rest or spanner. Page-scoped ids shift, the accepted rule
7(a) precedent.

The suppress column is wider than the force column **because of §3.1's
damage**, not because suppression is intrinsically disruptive: it merged
two systems it should not have.

### 3.4 The collision matrix (section D, testscore) — and it is not a tie

Both maps key by measure ordinal, so every combination is reachable.
`starts a system` / `starts a page` are read off the resulting layout.

| overrides at one ordinal | `pre` | `post` |
|---|---|---|
| system FORCE + page FORCE @m3 | both, **+ spurious `break-override-inert`** | both, clean |
| **system SUPPRESS + page FORCE @m9** | **neither** (system wins) | **both** (page wins) |
| system FORCE + page SUPPRESS @m3 | system yes, page no | system yes, page no |
| system SUPPRESS + page SUPPRESS @m5 | as system-alone, **+ spurious `break-override-inert`** | as system-alone, clean |
| page FORCE @m5 (already a page start) | no-op, no warning | no-op, no warning |

Two findings.

1. **The incoherent combination resolves in OPPOSITE directions under the
   two orderings.** system SUPPRESS + page FORCE at m9 yields "no break at
   all" under `pre` and "a page break" under `post`. Whichever ordering
   ships, the answer is arbitrary unless something states the rule — so
   this needs a decision, not a default.
2. **Two passes racing on one `<print>` element manufacture false
   warnings.** Under `pre`, the page pass writes `new-system="yes"` (or
   `new-page="no"`) *before* `_apply_system_breaks` looks, so M5's pass
   finds nothing left to change and reports the user's system override as
   inert. `break-override-inert` fires on two rows for gestures that
   worked perfectly. This is M5.7's M1 finding one level up, and it is the
   argument for **one combined pass over two racing ones** (D3).

### 3.5 Downstream sweep re-run for pages (section E)

| case | result |
|---|---|
| bigband1, hide OFF, FORCE page m7 | 3→4 pages, 9→10 systems, warning set **unchanged** |
| bigband1, hide OFF, SUPPRESS page m12 | starts `(1,14,23)`, `repaginated`, nothing clipped |
| bigband1, **hide ON**, FORCE page m7 | identical page/system result; hiding still applied; warning set unchanged |
| bigband1, hide ON, SUPPRESS page m12 | honored; `reclaimed-spanner-ink` count **drops** (fewer systems), does not grow |
| complex2 + condensing, FORCE page m6 | 20→21 pages; `repaginated` **and** `scaled-to-fit` both still fire |
| tall_system_min, FORCE page m2 | 1→2 pages, `scaled-to-fit` still fires, nothing clipped |

Every readability and never-clip mechanism survives page authoring
unchanged. **E4 — one page toggle's full re-engrave: testscore 0.27 s,
bigband1 0.68 s**, the same order as M5's F4 (0.25 / 1.28), so
`SetPageBreak` arrives via `execute()`, never `preview()`.

### 3.6 BACKLOG 16, measured (section F)

Page-only break markers per fixture — measures whose *only* break marker
is `new-page`, i.e. the ones `_repaginate` can destroy: testscore
`[5, 13]`, bigband1 `[12, 20]`, complex3 **all twenty**.

> **CORRECTION, found at build (M6.0, 2026-07-28).** F1's "no goldens
> move" conclusion is WRONG, and the flaw is in its coverage, not its
> arithmetic: F1 probes each fixture in ONE configuration, and neither
> of the two golden loads that actually repaginate is that
> configuration. `complex3` is probed FLAT here but its golden is the
> HIDDEN load, and `video_test` — the golden suite's canonical
> repagination fixture — is not in F1's list at all. **Two of the twelve
> goldens move**, and both movements are the fix working:
>
> - `video_test_flat`: the engraving is byte-identical — every element,
>   id, bbox, glyph hash, note record and timeline value unchanged.
>   Only `canonical_xml_sha256` moves (the promoted attributes are in
>   the prepared XML) and the load-warning list reorders, because an
>   `<sb>` that now exists shifts Verovio's seeded id sequence. Verified
>   deterministic across three fresh processes.
> - `complex3_hidden`: 20 systems → **21**, which is exactly the encoded
>   set (measure 1 plus its twenty page-only breaks). The hidden load
>   was silently losing one encoded system break — m74 and m78 had
>   merged — and the 16 changed ids are m74 regaining its system-start
>   restatement furniture. Pages stay 20, nothing is clipped, and the
>   timeline and every note record are identical.
>
> Both baselines are re-captured in the M6.0 commit, which is the golden
> suite's own protocol for a deliberate behaviour fix. The ruling is
> unaffected — if anything this strengthens D0, since the damage was
> live on `main` on the app's real orchestral fixture, not only under a
> user edit.

**F1 — promotion is a total no-op at baseline.** Promoting every encoded
`new-page="yes"` to also carry `new-system="yes"` before anything strips
it:

| fixture | systems same | pages same | **element ids same** |
|---|---|---|---|
| testscore | yes | yes | **yes** |
| bigband1 | yes | yes | **yes** |
| complex2 | yes | yes | **yes** |
| complex3 | yes | yes | **yes** |

Including complex2 and complex3, which repaginate *and* scale to fit. The
fix **moves no goldens**.

**F2 — and it fixes the damage M5 recorded.** testscore with a system
FORCE at m19, the case ROADMAP §M5 names:

```
promote=False:  {1:(1,8), 2:(9,16), 3:(17,18), 4:(19,19)}   ← 1+2 and 3+4 merged
promote=True:   {1:(1,4), 2:(5,8), 3:(9,12), 4:(13,16), 5:(17,18), 6:(19,19)}
```

The encoded system structure is preserved exactly, and only the break the
user asked for is added.

**F3 — but promotion alone does NOT save a forced PAGE break.** Same
testscore case, page FORCE at m3, `promote=True`:

| design | page honored | systems |
|---|---|---|
| `pre` + promote | **no** — starts `(1,5,13,19)` | correct |
| `plan` + promote | **yes** — starts `(1,3,5,13,19)` | correct |

The two fixes are **orthogonal and both needed**. Promotion preserves the
*system* break a page break implies; only feeding intent into the plan
preserves the *page* break itself. Under `pre`+promote the user asks for
a page break and silently receives a system break.

---

## 4. Decisions — proposed, then ruled

**All thirteen (D0–D12) were ruled as recommended (Marcus,
2026-07-28)**, with two standing riders carried over from M5. Each is
kept below in its original form, because the argument for each is the
record of why the ruling went the way it did.

- **Rider 1 (menu/panel affordances).** Every action the milestone adds
  — the page toggle in the Score menu, and every button the layout zone
  puts over an existing action — gets a **keyboard shortcut** where one
  makes sense, and any action that can be disabled for more than one
  reason carries a **status tip naming WHY**. This is M5's D1 rider,
  restated as standing policy.
- **Rider 2 (flag, don't deviate).** If a ruling or a brief measurement
  is contradicted by reality mid-build, stop and flag it rather than
  silently working around it.

Two consequences worth stating up front, because they narrow what the
app may do forever after:

- **D0's ruling answers the question it raised**: a repagination may NOT
  change system content. `_repaginate` promotes each encoded
  `new-page="yes"` to also carry `new-system="yes"` before it strips, so
  the encoded system structure survives a re-derived page plan intact.
- **D1 + D3 together fix the ordering**: never-clip owns the final page
  plan and authored page intent is an INPUT to it (never a pass layered
  over it), and the two override maps are written by ONE combined pass
  with a stated precedence — a page break implies a system break, so at
  one ordinal page FORCE beats system SUPPRESS, and a page SUPPRESS
  asserts `new-system="yes"` rather than clearing the measure's only
  marker. That precedence is what the D8 `page-break-repaginated`
  warning reports when the two disagree.

Each decision states the measurement behind it.

### 4.0 D0 — pay BACKLOG 16 first (stop-and-ask)

`_repaginate` destroys a system break encoded only as a page break,
contradicting rule 7(a)'s own wording. M5 flagged it rather than fixing
it, on the grounds that M5's charter was a layout-intent edit.

Three things now argue for paying it here. It is in the **page-break**
machinery, which is M6's charter. §3.6 F1 measures the fix as a **total
no-op at baseline on all four fixtures, element ids included** — so it
moves no goldens, which was the stated reason to defer. And §3.6 F2 shows
it repairing damage the app does **today**, on `main`, whenever a user
forces a system break on a score with page-only markers.

**Recommend: do it, as M6.0, its own commit, no feature code in it** —
the M5.0/M3.0 precedent. The pass is a promotion loop inside
`_repaginate`, before the strip.

Alternative to name: leave it, and let M6's own design work around it.
§3.6 F3 shows that the workaround is needed anyway (they are orthogonal),
so leaving it buys nothing and keeps a known-wrong behaviour in a
milestone that touches the exact code.

**A question this raises, which is Marcus's, not the brief's:** whether a
repagination is allowed to change *system* content at all. The promotion
says no. That is the right answer for authored breaks; it is worth
stating out loud because it narrows what `_repaginate` may do forever
after.

### 4.1 D1 — how user page intent composes with never-clip (stop-and-ask)

The sharpest decision in the milestone. Measured across §3.2.

- **`pre` (the naive M5 twin) is disqualified.** It loses a forced page
  break whenever the re-derived plan diverges from the encoded set
  (§3.2 B1/B3), and it fails *rarely and silently* — complex2 and
  complex3 pass by luck — which is the worst failure shape available.
  It also manufactures false inert warnings (§3.4).
- **`post` works** for FORCE but puts user intent **above** never-clip,
  which rule 7 does not permit: a suppression applied after the planner
  could remove a break the planner needed.
- **`plan` works in both directions** and keeps the ordering rule 7
  states: never-clip owns the final page plan, and user intent is an
  input to it.

**Recommend `plan`:** `plan_page_breaks` grows forced/suppressed
parameters; forced ordinals are unioned into the plan (restricted to real
system starts), suppressed ordinals are dropped from it. Never-clip keeps
the last word — §3.2 B2 shows suppression is nonetheless honored at its
own ordinal in every measured case, with the planner re-breaking
elsewhere.

> **REFINEMENT, found at build (M6.3, 2026-07-28).** `plan` is built as
> ruled, with one correction the spike's data could not distinguish:
> **the suppressed set is not subtracted from the plan, and
> `plan_page_breaks` takes no `suppressed` parameter at all.**
>
> The suppression is applied at the prep seam, so the bands the planner
> measures ALREADY honor it — the planner is looking at the piled-up
> layout the suppression produced and deciding from scratch where pages
> must fall, so every break it emits is one it needs. Subtracting the
> suppressed ordinals therefore deletes breaks never-clip requires.
> Measured on the post-D3 build: bigband1 with both page breaks
> suppressed drops from a 4-page plan to a 2-page one and is rescued by
> **scale-to-fit at 40%**; testscore's A6 row lands at **51%**. Legal
> and unclipped — but a far worse score than the extra page the planner
> asked for, and never-clip keeping the last word in form while losing
> it in substance.
>
> Not subtracting gives exactly the ruled behaviour instead, in the
> ROADMAP amendment's own words: *"a suppressed one is overridden, and
> warned, whenever honoring it would clip ink."* A suppression is
> honored wherever the planner does not need that break — which is
> every case §3.2 measured, since `plan ∩ suppressed` was empty in all
> of them, so the two formulations agree on all measured data — and
> overruled where it does, reported by `page-break-repaginated`.
> bigband1 now lands on 4 pages saying which two overrides it could not
> honor, and complex3 with all twenty suppressed keeps its 21 pages
> rather than collapsing to the spike's single scaled-down one.

The consequence to state plainly, and the reason this is stop-and-ask:
**a suppressed page break is a request, not a guarantee.** The page count
stays owned (rule 7(a), and M5's D7 already established the principle for
the system→page direction). D8 makes the app say so rather than fail
silently.

Note the retry structure this must respect: `plan_page_breaks` is only
called when the first pass overflows, so on a non-overflowing score
(testscore, bigband1) the forced ordinal must still reach the XML. So
`plan` is not "instead of" a prep pass — it is a prep pass **plus** an
input to the planner, so the FORCE is asserted once and re-asserted if
the planner runs. That doubling is the actual shape to build, and it is
what the spike's `plan` mode does.

### 4.2 D2 — the key convention

Marcus's ruling, and it matches everything already in the codebase: the
document key is the ordinal of the measure that **STARTS the new page**
(N+1 from a barline in measure N), which is what `<print new-page>`,
`_repaginate`'s `break_measures`, and `system_break_overrides` all
already mean. The UI converts at the seam. **Recommend: as ruled**, no
alternative worth naming.

### 4.3 D3 — the collision between the two maps (stop-and-ask)

§3.4 shows the incoherent combination (system SUPPRESS + page FORCE)
resolving in **opposite directions** under the two pass orderings, and
§3.4 finding 2 shows two passes racing on one `<print>` element
manufacturing false `break-override-inert` warnings.

**Recommend three things together:**

1. **One combined pass, not two racing ones.** `_apply_breaks(root,
   system_overrides, page_overrides)` replaces `_apply_system_breaks`,
   writing both attributes of one `<print>` in one visit, and computing
   the inert set for both maps from what it actually wrote. This removes
   the false warnings by construction rather than by ordering luck. It is
   also where the semantic couplings live in one readable place.
2. **A stated precedence at the seam:** a page break implies a system
   break, so at one ordinal **page FORCE beats system SUPPRESS** (it
   writes `new-page="yes"` *and* `new-system="yes"`), and **page SUPPRESS
   asserts `new-system="yes"`** rather than clearing the measure's only
   marker — the §3.1 A3/A4 fix, and the exact mirror of M5's D7.
3. **Policy-level prevention, so the precedence is rarely exercised.**
   The page toggle's fat-apply clears a contradicting system override at
   the same ordinal in the same undo entry (`SetPageBreak.also_system`),
   and the system toggle does the same in reverse. The user never
   authors an incoherent pair through the UI; the precedence exists for
   hand-edited files and rule-5 staleness.

The pure part — "given both maps and an ordinal, what is coherent" — is a
`normalize()` in `core/editing/breaks.py`, headless-tested cell by cell
against §3.4's table.

Alternative to name: precedence only, no prevention. Cheaper, but it
leaves the document holding pairs that contradict each other, and every
future reader of the two maps has to re-derive the rule.

### 4.4 D4 — the handle and the enable rules

**Recommend: reuse M5 wholesale.** BARLINE selection (rule 13's only
handle into a break position), the N+1 arithmetic of D2, and the four
disable cases with their status-tip reasons: no score, nothing selected,
not a barline, the barline carries no measure (system-start barlines are
page-scoped), the last measure. §3.1 A7 confirms an out-of-range ordinal
is silently inert, so D6's reasoning transfers unchanged.

The status-tip strings are new (they say "page break"), so the constants
table in `core/editing/breaks.py` grows a page half.

### 4.5 D5 — the toggle sense, and where it reads the current state

**Recommend the M5 three-step sense, over `page_of_measure` derived in
the app** (§1.2): an override exists → clear it; else the target already
starts a page → SUPPRESS; else → FORCE. No adapter change, no new
`EngravedScore` field, no golden movement — a strictly cheaper D4 than
M5's.

### 4.6 D6 — schema

**Recommend v9**, `_READABLE_VERSIONS` extended, the bump comment block
continued, **no read gate**: a missing key defaults to `{}`, which is "no
overrides", which is the pre-option look. Identical to M5's §1.4
reasoning. The strict-by-version gate is the point of bumping — a tagged
v8 reader must refuse a v9 file rather than silently drop the field and
destroy it on the next save.

### 4.7 D7 — the command

**Recommend `SetPageBreak(ordinal, mode, also=(), also_system=())`** — a
sibling of `SetSystemBreak`, the fat-apply idiom's fourth use.
`also_system` is what makes D3's prevention one undo entry (rule 8):
clearing a contradicting system override is part of the same gesture, not
a second command. `describe()` follows the M3.5 rule — one entry keeps
"force / suppress / clear page break", more than one returns "change
breaks".

Alternative to name: one `SetBreaks` command carrying both maps,
retiring `SetSystemBreak`. Tidier in the abstract, but it rewrites a
shipped, tested command and its call sites for no behaviour, and the
`also`/`also_system` pair says what is happening more plainly.

### 4.8 D8 — what the app tells the user

Two different things happen, and **recommend two codes**, because only
one of them is the app disagreeing with the user:

- **`page-break-override-inert`** — the D10 twin: the ordinal wrote
  nothing at the seam (past the end of a shortened score; a suppression
  whose encoded page break has gone). Rule-5 staleness, the user's fault
  or the file's.
- **`page-break-repaginated`** — never-clip re-derived the page plan and
  the resulting page starts are not the ones the overrides asked for.
  This is the app overruling the user under rule 7, and §3.2 B2 shows it
  is a normal outcome (5,13 → 9), not an error. It must name the
  ordinals, counted in the status bar like every other load warning
  (flag-and-continue, Phase 10 ruling b).

Alternative to name: one code for both. Rejected because "your override
was stale" and "your override was overruled to avoid clipping ink" want
different things from the user.

### 4.9 D9 — the layout zone's mechanism and contents

**Recommend: a left `QDockWidget` on the `Inspector` template** —
`setObjectName` for saveState identity, `NoDockWidgetFeatures`, left area
only, `toggleViewAction()` added to the View menu beside the inspector
and lower-zone toggles. `window_state.py` needs **no change** (§1.5).

v1 content is a re-home and a readout, per BACKLOG 17's "M1-style re-home
of existing commands, not new semantics":

- the three break actions — **the same `QAction` objects** the Score menu
  holds, so enabled state, label and status tip cannot diverge between
  the two surfaces (the `follow_action` precedent from M1, where the
  Playback menu and the inspector share one action);
- a readout of the active overrides, both maps, by ordinal, with a
  per-entry clear — which needs **no new command**, since `mode=None`
  already pops an entry.

Menu actions stay. Own module(s) under `ui/`, and the readout is its own
widget module rather than a limb on the dock.

**Recommend against** putting anything in v1 that is not already a
command. A zone that grows its own semantics stops being a re-home and
becomes the thing BACKLOG 17 deferred.

### 4.10 D10 — `_STATE_VERSION`

A third dock arrives into stored `QMainWindow` state that predates it.
Qt normally places an unknown dock at its `addDockWidget` default, which
is the desired outcome.

**Recommend: verify before changing anything** — restore a v0 state
saved without the zone, and check the zone lands in the left area at a
sane width. Bump `_STATE_VERSION` to 1 only if it does not, since bumping
discards every user's saved window layout.

### 4.11 D11 — the view anchor and the selection across a page edit

`_break_anchor` diffs only `system_break_overrides` and re-anchors on the
lowest of at most two changed ordinals.

**Recommend: generalize it to both maps**, same `1 <= n <= 2` bound over
the union of changed ordinals, same "lowest wins" rule. D14's reasoning
carries: a page gesture writes at most one ordinal of its own plus at
most one contradicting-override clear, and the lowest is where the
affected music is. D9's selection restore needs no change — §3.3 shows
measure-scoped ids surviving a page edit for the same reason they survive
a system edit.

### 4.12 D12 — the readout's per-entry clear

**Recommend: it goes through `execute()` like the menu action**, so it
re-engraves, re-anchors and restores the selection on exactly the path
D11/D9 already own. No special case, no second path to keep in sync.

---

## 5. Task breakdown

Each task ends with a concrete check. D0–D12 were ruled on 2026-07-28
(§4) — D0, D1 and D3 changed what gets built, and the tasks below are
written to the ruled shape.

### M6.0 — BACKLOG 16 (no feature code)

Per D0: `_repaginate` promotes each encoded `new-page="yes"` to also
carry `new-system="yes"` before stripping.

**Verify:** `pytest` green at 960/1; `tests/test_golden_layouts.py`
byte-identical on all 12 fixtures; a new test pinning §3.6 F2 (system
FORCE at testscore m19 leaves systems `{1:(1,4) … 6:(19,19)}`, not the
merged `{1:(1,8) …}`). Its own commit.

### M6.1 — document field, command, schema v9

`PageBreak` vocabulary, `ProjectDoc.page_break_overrides` defaulting to
`{}`, `SetPageBreak(ordinal, mode, also, also_system)` in
`core/project/commands/layout.py`, `serialize.py` to v9 per D6.

**Verify:** headless — round-trip a doc with two page overrides and one
system override; `mode=None` pops; an `also_system` entry is applied in
the same step and one undo restores both maps; a v8 fixture loads with
`{}` and unchanged look; a v9 file is refused by a `_READABLE_VERSIONS`-
restricted reader.

### M6.2 — the combined prep-seam pass

Per D3: `_apply_breaks(root, system_overrides, page_overrides)` replaces
`_apply_system_breaks`, writing both attributes in one visit with the
stated precedence, returning the inert set for both maps. `prepare()`
grows `page_breaks=`; the provider threads it through **all three**
`prepare()` calls (§1.3).

**Verify:** headless — FORCE and SUPPRESS both land on testscore
(assert `page_starts`); §3.1 A3's damage is gone (suppressing m5's page
break leaves five systems, not three); every cell of §3.4's matrix,
including that the two spurious `break-override-inert` rows no longer
warn; a load that repaginates still carries both maps; goldens
byte-identical.

### M6.3 — never-clip composition

Per D1: `plan_page_breaks` grows forced/suppressed inputs; the provider
passes the override-derived sets. The D8 warnings.

**Verify:** headless — §3.2 B1's testscore+system-FORCE row keeps the
forced page at m3 (the case `pre` loses); §3.2 B2's three suppress-all
rows produce their measured page sets with nothing clipped and
`page-break-repaginated` naming the overruled ordinals; the never-clip
invariant asserted directly (no system band past its page bottom) on
every row.

### M6.4 — the toggle policy

Per D4/D5/D3: `core/editing/breaks.py` grows the page toggle, its status
tips, and `normalize()`. Pure, no Qt.

**Verify:** headless unit tests on synthetic maps — all three toggle
branches, all five disable cases, every cell of the D3 coherence table,
and a round-trip (FORCE → toggle → doc equals the original).

### M6.5 — UI wiring

The third QAction on `BreakActionController`; `ScoreLoader.
_applied_page_breaks` + the `needs_reengrave` clause + the `load()`
parameter; `_break_anchor` per D11.

**Verify:** headless window test — select a barline, trigger, assert one
re-engrave and the page split; undo restores in one entry; the action is
disabled with each reason; the view re-anchored and the selection
survived.

### M6.6 — the layout zone

Per D9/D10: `ui/layout_zone.py`, the left dock hosting the three shared
QActions.

**Verify:** headless — the dock exists with its objectName, its
`toggleViewAction` is in the View menu, its buttons mirror the actions'
enabled state and trigger the same commands; a save/restore cycle from a
state that predates the dock places it sanely (D10's check, before any
`_STATE_VERSION` decision).

### M6.7 — the overrides readout

Its own widget module. Lists both maps by ordinal with a per-entry clear
(D12).

**Verify:** headless — the readout reflects both maps, refreshes on
document change, and a clear pops exactly that entry in one undo step
and re-engraves.

### M6.8 — docs

Apply the ROADMAP rule-7 amendment to CLAUDE.md **with the ruling date**;
close ROADMAP §M6 with what was built and where reality differed;
ARCHITECTURE gets the combined break seam; BACKLOG 16 closed (if D0 says
so) and 17 closed.

**Verify:** full suite green, goldens byte-identical, `docs/` diff read
end to end before the merge.

---

## 5b. As built (M6.0–M6.8, 2026-07-28)

Every task landed in order, each with its own verification before the
next started, and every decision was built as ruled. Suite **960 → 1042
passed / 1 xfailed**. Goldens byte-identical for every unmodified
fixture at every commit after M6.0.

| task | commit | what it is |
|---|---|---|
| M6.0 | `f20b33a` | BACKLOG 16: `_repaginate` promotes page-only breaks before stripping. No feature code. |
| M6.1 | `6cdad9a` | `PageBreak`, `page_break_overrides`, `SetPageBreak`, schema v9 |
| M6.2 | `ef33181` | `_apply_breaks` — one pass over both maps, `_wanted_break_attrs` the stated rule |
| M6.3 | `fb30e21` | `plan_page_breaks(forced=…)`, the two D8 warnings |
| M6.4 | `4ff9f84` | `core/editing/page_breaks.py` + `break_coherence.py` (the split) |
| M6.5 | `b16e09f` | the third QAction, `_applied_page_breaks`, `_break_anchor` over both maps |
| M6.6 | `3ce96a1` | `ui/layout_zone.py`, the left dock over the SAME actions |
| M6.7 | `ec45cd5` | `ui/panels/break_overrides.py`, the readout with per-entry clear |

**Where reality differed.** Four places, each already recorded inline
above at the decision it touches:

1. **§3.6 F1 was wrong about goldens** — two of twelve move, both as the
   fix working. See the correction box in §3.6 and ROADMAP §M6 "As
   built" item 1.
2. **D1's suppressed-set subtraction is not built** — see the refinement
   box in §4.1. `plan_page_breaks` takes `forced` only.
3. **§3.1 A6 and §3.2 B2's numbers moved** because the ruled D3 fix
   preserves the system breaks the spike prototype destroyed; three
   pages where the spike measured two. The tests carry the new numbers
   and the reason.
4. **`core/editing/breaks.py` split before M6.4 landed**, exactly as §7
   said it would have to — one module per document map, plus
   `break_coherence.py` for the rule that couples them.

**Two things worth carrying forward.** The page-inert warning is
computed against the FINAL layout rather than the seam, so it can never
double-report an ordinal that `page-break-repaginated` already covers —
the two codes partition. And `PageBreakAction` is its own dataclass
rather than a reuse of `BreakAction`: the two carry different
vocabularies in `mode`, and one shared type would let a page gesture be
handed to the system command with nothing complaining.

---

## 6. Exit criteria (from ROADMAP §M6)

On bigband1 (app path, the `gliss` caveat): force a page break mid-score
— the page splits, systems and reveal edges stay correct on both pages,
`score_end` and the trigger count do not move. Suppress an encoded page
break — the pages merge, or never-clip overrides it *and says so*. Both
undo cleanly in one entry each; save/reload reproduces (v9); a v8 project
loads with no overrides and an unchanged look. The layout zone drives all
three actions, mirrors their enabled state, lists the active overrides
and clears them individually. Goldens byte-identical for unmodified
fixtures. Full suite green.

**Fixture caveat**, unchanged from M5: bigband1 does not load strict
(`unknown SVG class 'gliss'`), so the interactive exit run is the app
path and headless tests/spikes against it must pass `strict=False`. The
spike does; §3's bigband1 numbers are all app-path.

---

## 7. Invariants in force throughout

Rule 1 — the toggle policy, the coherence rule and the break rewrite are
pure Python in `core/`; no Qt. Rule 5 — overrides are intent, keyed by
measure **ordinal**, never printed number, and every layout consequence
re-derives; `page_of_measure` is derived per load, never stored. Rule 7 —
never-clip is absolute and the page count stays owned; the amendment is a
draft until M6.8 applies it. §3 checked for clipped ink on every one of
its loads and found none, which is the invariant this milestone is most
able to break. Rule 8 — `SetPageBreak` is undoable, one entry per
gesture including the D3 prevention half. Rule 12 — the engraved timemap
does not move when a page break does (§3.3 pins `score_end` and the
trigger count in both directions). Rule 13 — the barline is the handle
and stays an object in a measure, never the measure itself.
No-monoliths — D0 is paid before anything is added, the layout zone and
its readout are separate modules, and `core/editing/breaks.py` (233
lines) is watched: if the page half takes it past ~400 it splits along
the system/page seam before M6.4 lands.
