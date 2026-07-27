"""The `:seg` family: which ids does an override on THIS id belong to?

Open since Phase 5.3 (BACKLOG 9). A spanner broken across systems is
several elements — the adapter mints continuation segments in a second
pass as `f"{source.element_id}:seg{k}"` with
`identity = replace(source, element_id=...)`, so everything but the id
is inherited — and a per-element style override keyed by id therefore
reaches only the segment the user clicked.

**Ruling (Marcus, 2026-07-27): fan out to the whole family.** They are
one musical object; colouring a hairpin should not require finding every
system it crosses.

The grammar was audited before the ruling rather than assumed
(`spikes/seg_fanout.py`, 4 fixtures, 30124 elements, 116 broken
spanners): no nesting, no orphans, no identity mismatch between a
segment and its source, and sources only ever TIE / SLUR / HAIRPIN. The
suffix is unambiguous because `_ID_TAG` is
`{k: k.name.lower() for k in ElementKind}` and there is no SEG kind, so
a base id always ends `:<kindtag>:<digits>` — only the continuation pass
can produce `:seg<digits>`. (It has been wrong once: before the FINDING-5
fix, stems minted `:seg1` ids. The fix restricted sources to spanner
classes, and `test_seg_family` pins the grammar so a regression there
surfaces here rather than silently mis-colouring.)
"""
from __future__ import annotations

import re
from typing import Iterable

from scoreanim.core.score.identity import ElementId

_SEG_SUFFIX = re.compile(r":seg\d+$")


def source_of(element_id: ElementId | str) -> ElementId:
    """The family's source id — itself, for anything that is not a
    continuation segment."""
    return ElementId(_SEG_SUFFIX.sub("", str(element_id)))


def is_segment(element_id: ElementId | str) -> bool:
    return _SEG_SUFFIX.search(str(element_id)) is not None


def family_of(element_id: ElementId | str,
              known_ids: Iterable[ElementId | str]) -> tuple[ElementId, ...]:
    """Every id of the same spanner, source first then segments in
    order.

    `known_ids` is the loaded score's element registry: the family is
    intersected with what actually EXISTS, so an override never names an
    id the current engraving does not have. A flat element (the common
    case by far) comes back as just itself.
    """
    source = str(source_of(element_id))
    prefix = source + ":seg"
    segments = []
    have_source = False
    for known in known_ids:
        text = str(known)
        if text == source:
            have_source = True
        elif text.startswith(prefix) and text[len(prefix):].isdigit():
            segments.append((int(text[len(prefix):]), text))
    out = [source] if have_source else []
    out.extend(text for _, text in sorted(segments))
    # the id we were handed always belongs to its own family, even if the
    # registry has never heard of it (a stale override being cleared)
    if not out:
        out = [str(element_id)]
    return tuple(ElementId(t) for t in out)
