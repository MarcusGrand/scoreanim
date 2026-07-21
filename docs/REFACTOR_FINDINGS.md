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

(none yet)
