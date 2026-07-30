# Refactor findings — verovio_adapter package split (Phase R)

Suspected defects surfaced during R.1–R.3, logged here instead of fixed
inline (behavior-change policy, docs/REFACTOR_BRIEF.md). Worked in R.4:
category-2 hardening freely in its own commits; category-3 fixes one per
commit with golden before/after diff + pinning test + baseline
re-capture; flag-and-stop for Marcus's ruling on anything that changes
animation semantics or rendered output. Out-of-scope or too-large
findings go to BACKLOG.md with a one-line rationale.

Format per finding:

    ## F<N> — <one-line title>
    - Where: <module:function / line>
    - Category: 2 (hardening, no output change) | 3 (behavior fix)
    - Observed: <what the code does / would do>
    - Expected: <what it should do>
    - Fate: open | fixed <commit> | backlogged | ruled-out <why>

## F1 — LoadWarning import omitted in the identity.py move
- Where: verovio/identity.py (move 6, R.1)
- Category: move defect (not a latent adapter defect)
- Observed: the extracted module was missing the LoadWarning import its
  unattributed-continuation branch uses; the golden suite caught it on
  video_test_hidden before commit.
- Expected: moves carry their imports.
- Fate: fixed pre-commit inside move 6 (cdb28b9) — restoring the move's
  byte-identity, not a logic edit.

## F2 — bare KeyError on an unsupported text-anchor
- Where: verovio/decompose.py:_add_text
- Category: 2 (hardening, no output change)
- Observed: a text-anchor outside start/middle/end died on a bare
  KeyError at the bbox lookup, AFTER the TextPrimitive (carrying the
  bogus anchor) was already appended.
- Expected: a load error with page context, raised before any mutation
  (TextPrimitive.anchor is a 3-value contract the renderer relies on).
- Fate: fixed (R.4 hardening commit) + pinned
  (test_unsupported_text_anchor_fails_loudly); goldens unchanged.

## F3 — IndexError on a whitespace-only @staff in _parse_mei
- Where: verovio/mei_index.py:_parse_mei (measure-attached elements)
- Category: 2 (hardening, no output change)
- Observed: `sp.get("staff")` is truthy for a whitespace-only value, so
  `.split()[0]` raised IndexError and failed the load.
- Expected: treated like a missing @staff (skipped).
- Fate: fixed (R.4 hardening commit) + pinned
  (test_whitespace_staff_attr_is_ignored_not_a_crash); goldens
  unchanged.

## F4 — redundant re-prepare in the scale-to-fit path
- Where: verovio/provider.py:load_detailed
- Category: perf (out of the refactor's scope)
- Observed: when systems overflow but plan_page_breaks returns (), the
  scale-to-fit branch calls prepare() again with identical inputs
  before the scaled engrave — a full wasted prep; output unaffected.
- Expected: reuse the existing PreparedScore when breaks is empty.
- Fate: backlogged (BACKLOG.md "Phase R deferrals" — the brief defers
  all performance work).

No category-3 (output-changing) defects surfaced during R.1–R.3: the
moves reproduced every golden byte-identically, and the review of the
split modules found no behavior fix candidates. Nothing required
flag-and-stop.
