"""Which staff does a drawn part label belong to? (M7)

Verovio draws a staff label as a direct child of `<g class="system">`,
with no staff ancestor and no MEI `@staff`, so a label reaches its part
through neither of the adapter's usual routes. Its own SVG id is no help
either: Verovio mints a throwaway id for the drawn object that does not
exist in the MEI at all (measured 0/129, spikes/label_part.py).

What IS reliable is document ORDER. Within one system Verovio emits the
labels top to bottom, in the same order as the staves they belong to. So
the k-th drawn label belongs to the k-th labelled staff — with one filter
that naive order misses, and one guard that makes a mistake harmless:

  The FILTER. Only staves whose staffDef actually carries a label of the
  class being drawn count. Verovio draws the full `label` on system 1 and
  the `labelAbbr` on later systems, and a part with no abbreviation draws
  NOTHING after system 1. Without the filter, order is 101/129 and
  MIS-ATTRIBUTES silently rather than failing. With it, 129/129 — under
  hidden empty staves and condensing alike.

  The GUARD. Every pairing is checked against the staffDef's own label
  text. Order decides the pairing; the text only confirms it. Refusing to
  pair leaves the label part-less, which merely disables the rename;
  pairing wrongly would rename the wrong instrument. So we refuse
  whenever the evidence disagrees.

Pure: strings and numbers in, staff numbers out. No Verovio types, no
XML, no _LoadState.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence


def normalized(text: str) -> str:
    """Label text with all whitespace removed.

    The MEI and SVG sides extract their text through different walks, so
    a multi-row label can come back "Alto Sax 1" on one side and
    "AltoSax 1" on the other. Whitespace is never what distinguishes two
    instruments, and this comparison only CONFIRMS a pairing order has
    already made, so dropping it costs nothing.
    """
    return "".join(text.split())


def staff_for_labels(drawn_texts: Sequence[str],
                     visible_staves: Sequence[int],
                     staffdef_labels: Mapping[tuple[int, str], str],
                     label_class: str) -> list[int | None]:
    """Pair one system's drawn labels with the staves they belong to.

    `drawn_texts` is the labels of ONE class, in the order Verovio emitted
    them. `visible_staves` is the staff numbers present in that system, in
    top-to-bottom order. `staffdef_labels` maps (staff number, class) to
    the label text the MEI carries there.

    Returns one entry per drawn label: its staff number, or None where we
    refuse to say. A count mismatch refuses the whole system — if the two
    sequences are not the same length, their order cannot be trusted at
    all. A text disagreement refuses only that one label.
    """
    expected = [n for n in visible_staves
                if (n, label_class) in staffdef_labels]
    if len(expected) != len(drawn_texts):
        return [None] * len(drawn_texts)
    return [staff_n if normalized(drawn) ==
            normalized(staffdef_labels[(staff_n, label_class)]) else None
            for drawn, staff_n in zip(drawn_texts, expected)]
