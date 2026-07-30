"""Which staff does a drawn part label belong to, and so which part? (M7)

Verovio draws a staff label as a direct child of `<g class="system">`,
with no staff ancestor and no MEI `@staff`, so a label reaches its part
through neither of the adapter's usual routes. Its own SVG id is no help
either: Verovio mints a throwaway id for the drawn object that does not
exist in the MEI at all (measured 0/129, spikes/label_part.py).

What IS reliable is document ORDER, with one filter and one guard:

  The FILTER. Only staves whose MEI label matches the class being drawn
  count. Verovio draws the full `label` on system 1 and the `labelAbbr` on
  later systems, and a part with no abbreviation draws NOTHING after
  system 1. Without the filter, order is 101/129 and MIS-ATTRIBUTES
  silently rather than failing. With it, 129/129 — under hidden empty
  staves and condensing alike.

  The GUARD. Every pairing is checked against the label text the MEI
  carries. Order proposes the pairing; the text confirms it. Refusing to
  pair leaves the label part-less, which merely disables its rename;
  pairing wrongly would rename the wrong instrument. So we refuse whenever
  the evidence disagrees.

The order itself has two tiers, because a MULTI-STAFF part (a piano) hangs
its label on the `<staffGrp>` around its staves rather than on a
`<staffDef>`, and Verovio draws every group label FIRST, ahead of the
staff labels — measured 41/41 systems over the only two fixtures that have
one (spikes/label_group.py: video_test's Piano, complex2's Synth). So the
expected order is "group labels, then staff labels", and plain staff order
is kept as a second candidate: where the two disagree, only an order that
every label's text confirms is accepted.

`staff_for_labels` is the join, and it is pure. `_attribute_labels` is the
one adapter pass that uses it — it writes the staff number onto the
label's accumulator, which is all identity minting needs, since that
already turns a staff number into a part.
"""
from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence

from scoreanim.core.engraving.types import LoadWarning
from scoreanim.core.engraving.verovio.decompose import _ElementAccumulator
from scoreanim.core.engraving.verovio.mei_index import LABEL_CLASSES, StaffLabel
from scoreanim.core.engraving.verovio.records import _LoadState


def normalized(text: str) -> str:
    """Label text with all whitespace removed.

    The MEI and SVG sides extract their text through different walks, so a
    multi-row label can come back "Alto Sax 1" on one side and
    "AltoSax 1" on the other. Whitespace is never what distinguishes two
    instruments, and this comparison only CONFIRMS a pairing that order has
    already made, so dropping it costs nothing.
    """
    return "".join(text.split())


def _drawable(labels: Iterable[StaffLabel],
              visible: Collection[int]) -> list[tuple[StaffLabel, int]]:
    """The labels this system can actually draw, each with the staff it
    would sit beside: the first of its staves that is visible here."""
    out = []
    for label in labels:
        staff = next((n for n in label.staves if n in visible), None)
        if staff is not None:
            out.append((label, staff))
    return out


def _paired(candidate: Sequence[tuple[StaffLabel, int]],
            drawn_texts: Sequence[str]) -> list[int] | None:
    """The candidate order's staff numbers, but only if every drawn label
    agrees with the text the MEI carries there. None means "not this
    order"."""
    if len(candidate) != len(drawn_texts):
        return None
    if any(normalized(drawn) != normalized(label.text)
           for drawn, (label, _) in zip(drawn_texts, candidate)):
        return None
    return [staff for _, staff in candidate]


def staff_for_labels(drawn_texts: Sequence[str],
                     visible_staves: Collection[int],
                     labels: Sequence[StaffLabel]) -> list[int | None]:
    """Pair one system's drawn labels with the staves they belong to.

    `drawn_texts` is the labels of ONE class, in the order Verovio emitted
    them. `visible_staves` is the staff numbers present in that system.
    `labels` is that class's MEI labels in document order.

    Returns one entry per drawn label: its staff number, or None where we
    refuse to say.
    """
    drawable = _drawable(labels, visible_staves)
    groups_first = ([pair for pair in drawable if pair[0].on_group]
                    + [pair for pair in drawable if not pair[0].on_group])

    if groups_first == drawable:
        # No group label to reorder, so there is one candidate and nothing
        # to be ambiguous about. A count mismatch refuses the whole system
        # — if the two sequences are different lengths their order means
        # nothing — but a lone text disagreement refuses only that label.
        if len(drawable) != len(drawn_texts):
            return [None] * len(drawn_texts)
        return [staff if normalized(drawn) == normalized(label.text) else None
                for drawn, (label, staff) in zip(drawn_texts, drawable)]

    # A group label IS present, so the two orders disagree and only the
    # texts can say which one Verovio used. Accept a candidate only if
    # every label confirms it, and refuse outright if both candidates
    # confirm but disagree (duplicate part names could do that).
    by_group = _paired(groups_first, drawn_texts)
    by_staff = _paired(drawable, drawn_texts)
    if by_group is not None and by_staff is not None and by_group != by_staff:
        return [None] * len(drawn_texts)
    accepted = by_group if by_group is not None else by_staff
    return list(accepted) if accepted is not None \
        else [None] * len(drawn_texts)


# ---------------------------------------------------------------------------
# The adapter pass
# ---------------------------------------------------------------------------

def _drawn_text(acc: _ElementAccumulator) -> str:
    return "".join(run.content for text in acc.texts for run in text.runs)


def _attribute_labels(accumulators: list[tuple[int, _ElementAccumulator]],
                      st: _LoadState) -> None:
    """Give every drawn part label the staff number it belongs to (M7).

    Runs LAST among the post-passes, after every pass that reads
    `acc.staff` — all of which are gated on notes, rests or ledger dashes,
    so none of them ever sees a label. Writing `acc.staff` here is the
    whole integration: `_identity_for` already starts from `acc.staff` and
    derives part, part name and part-local staff from it, so identity
    minting needs no change. The label's ElementId does not change either
    — the part-bearing id branch needs a measure, and a label has none.

    A label we cannot place keeps `staff=None`, so it stays part-less and
    its rename stays disabled. That is warned, never guessed.
    """
    groups: dict[tuple[int, str], list[_ElementAccumulator]] = {}
    for _, acc in accumulators:
        if acc.svg_class in LABEL_CLASSES and acc.system is not None:
            groups.setdefault((acc.system, acc.svg_class), []).append(acc)

    for (system, label_class), accs in groups.items():
        drawn = [_drawn_text(acc) for acc in accs]
        # The system's visible staves. staff_centers_by_system is built from
        # the drawn staves, so it already reflects hidden empty staves and
        # condensing.
        visible = set(st.staff_centers_by_system.get(system, {}))
        labels = st.mei.staff_labels.get(label_class, ())
        staves = staff_for_labels(drawn, visible, labels)
        if all(staff is None for staff in staves):
            drawable = len(_drawable(labels, visible))
            st.warnings.append(LoadWarning(
                "label-unattributed",
                f"system {system}: its {len(drawn)} part label(s) "
                f"({', '.join(repr(text) for text in drawn)}) could not be "
                f"matched to the {drawable} label(s) the score carries for "
                f"its staves, so renaming them is disabled"))
            continue
        for acc, staff_n in zip(accs, staves):
            if staff_n is None:
                st.warnings.append(LoadWarning(
                    "label-unattributed",
                    f"system {system}: part label {_drawn_text(acc)!r} does "
                    f"not match the label its staff carries, so renaming it "
                    f"is disabled"))
                continue
            acc.staff = staff_n
