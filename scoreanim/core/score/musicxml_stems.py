"""The stem passes: which way a note's stem points.

Why this exists. Dorico exports the stem directions of the WRITTEN
score. ScoreAnim engraves CONCERT PITCH (rule 9,
`transposeToSoundingPitch`), and transposing a part moves its notes
across the middle staff line — but the exported `<stem>` does not
follow. Verovio honors an imported direction, so a transposing part
comes out with stems on the wrong side of its noteheads.

Measured before this was written (`spikes/stem_dirs.py`, 7 fixtures):
6.5-34.3 % of unbeamed single-voice stems point the wrong way as
exported, and the error is about seven times denser in transposing
parts than in concert-pitch ones. Dropping `<stem>` takes every fixture
to 100 % agreement with the convention.

So there are two passes, and they do NOT sit together in `prepare()`:

`_normalize_stem_directions` runs BEFORE `_apply_condense`. It drops
`<stem>` wherever a staff carries one voice in a measure, which hands
the decision to Verovio — the thing that is doing the transposing, and
a competent engraver besides (it gets beam groups and middle-line notes
right on its own). Running it before condensing is what makes a
condensed staff come out right for free: each source player is
single-voice, so its stems are stripped, and after the merge Verovio
sees two voices with no direction and applies its own voice-1-up /
voice-2-down. Running it after would leave every condensed staff with
whatever the file encoded.

A staff carrying two or more voices in a measure is left exactly as the
file has it (Marcus, 2026-08-03). Dorico generally gets those right,
and forcing a direction there would overrule real divisi and
cross-staff encoding.

`_apply_stem_directions` runs AFTER `_apply_condense`, because the
user's flips are keyed by engraved ElementIds and condensing renumbers
voices. It writes an explicit `<stem>` back, so where the two passes
meet on one note the flip WINS — that precedence is stated here rather
than left to fall out of the pass order.

Same shape as the module family: a tree in, mutated in place, nothing
returned but incidental counts.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from enum import Enum
from typing import Mapping

# A note value that draws no stem. Such an event must not consume a
# `seq`, or every override key past it in the measure points one note
# too far — pinned at 991/991 scopes by spikes/stem_dirs.py.
_STEMLESS_TYPES = frozenset({"whole", "breve", "long", "maxima"})

# The minted-id grammar, per-staff ink only:
# {part}:m{ord}:s{staff}:v{voice}:{kind}:{seq}
_STEM_ID_RE = re.compile(r"^([^:]+):m(\d+):s(\d+):v(\d+):stem:(\d+)$")


class StemDirection(str, Enum):
    """Which way the user pinned one note's stem (2026-08-03).

    The `<stem>` vocabulary, so it lives with the pass that writes the
    element — the same call `SystemBreak` and `PageBreak` made, and for
    the same reason: a two-valued vocabulary has no fields to twin, so
    there is no neutral copy in `core/project` and no conversion at the
    seam.

    There is deliberately no AUTO member. `F` cycles up and down only
    (Marcus, 2026-08-03), so a note the user has touched carries an
    absolute direction from then on; a note they have not touched is
    simply absent from the map.
    """
    UP = "up"
    DOWN = "down"


def _note_events(measure: ET.Element) -> list[list[ET.Element]]:
    """A measure's note events, in document order.

    An event is a maximal run of `<note>` starting at one without
    `<chord/>` — so a chord is ONE event, which is right because its
    notes share a stem. Rests are not events and start no run.
    """
    events: list[list[ET.Element]] = []
    current: list[ET.Element] | None = None
    for note in measure.findall("note"):
        if note.find("chord") is None:
            current = None
            if note.find("rest") is None:
                current = []
                events.append(current)
        if current is not None and note.find("rest") is None:
            current.append(note)
    return events


def _draws_a_stem(event: list[ET.Element]) -> bool:
    """Whether Verovio will draw a stem for this event, and therefore
    whether it takes up one of the measure's stem `seq` numbers."""
    if any(note.findtext("stem") == "none" for note in event):
        return False
    return not ({note.findtext("type") for note in event} & _STEMLESS_TYPES)


def _staff_of(note: ET.Element) -> int:
    return int(note.findtext("staff", "1") or 1)


def _voice_of(note: ET.Element) -> int:
    return int(note.findtext("voice", "1") or 1)


def _set_stem(note: ET.Element, value: str) -> None:
    """Write `<stem>`, reusing the note's own element if it has one.
    MusicXML orders `<stem>` after `<type>`/`<dot>` and before
    `<notehead>`/`<beam>`; appending is fine for Verovio, but an
    existing element is edited in place so the file's own order holds
    for the overwhelmingly common case."""
    stem = note.find("stem")
    if stem is None:
        stem = ET.SubElement(note, "stem")
    stem.text = value


def _normalize_stem_directions(root: ET.Element) -> int:
    """Drop `<stem>` on every staff that carries ONE voice in a measure,
    so Verovio decides the direction from the pitch it actually draws.

    Runs before `_apply_condense` — see the module docstring. Returns
    the number of `<stem>` elements removed.
    """
    removed = 0
    for part in root.findall("part"):
        for measure in part.findall("measure"):
            by_staff: dict[int, set[int]] = {}
            for note in measure.findall("note"):
                if note.find("rest") is not None:
                    continue
                by_staff.setdefault(_staff_of(note), set()).add(_voice_of(note))
            single = {staff for staff, voices in by_staff.items()
                      if len(voices) == 1}
            if not single:
                continue
            for note in measure.findall("note"):
                if note.find("rest") is not None:
                    continue
                if _staff_of(note) not in single:
                    continue
                for stem in note.findall("stem"):
                    # <stem>none</stem> is not a direction, it is "this
                    # note has no stem". Leave it: stripping it would
                    # grow a stem the score says should not exist.
                    if stem.text == "none":
                        continue
                    note.remove(stem)
                    removed += 1
    return removed


def _apply_stem_directions(root: ET.Element,
                           directions: Mapping[str, StemDirection]
                           ) -> tuple[str, ...]:
    """Write the user's pinned stem directions back into the tree.

    Keys are minted stem ElementIds — `P1:m5:s1:v1:stem:2`. The seq is
    the index of the note event among the stem-BEARING events of that
    (part, measure, staff, voice), which is what
    `spikes/stem_dirs.py` measured to be exact over every fixture.

    Runs after `_apply_condense`, and deliberately overwrites whatever
    `_normalize_stem_directions` left: a flip is the user saying this
    one is wrong, so it is the last word.

    Returns the keys it could not place, sorted — an id whose note no
    longer exists because the score or the condensing changed. Derived,
    warned upstream, never stored (rule 5).
    """
    if not directions:
        return ()

    # (part, measure ordinal, staff, voice) -> stem-bearing events
    wanted: dict[tuple[str, int, int, int], dict[int, StemDirection]] = {}
    inert: set[str] = set()
    for key, direction in directions.items():
        match = _STEM_ID_RE.match(str(key))
        if match is None:
            inert.add(str(key))
            continue
        part, ordinal, staff, voice, seq = match.groups()
        scope = (part, int(ordinal), int(staff), int(voice))
        wanted.setdefault(scope, {})[int(seq)] = direction

    seen: set[tuple[str, int, int, int]] = set()
    for part in root.findall("part"):
        pid = part.get("id", "")
        for ordinal, measure in enumerate(part.findall("measure"), start=1):
            events: dict[tuple[int, int], list[list[ET.Element]]] = {}
            for event in _note_events(measure):
                if not _draws_a_stem(event):
                    continue
                lead = event[0]
                key = (_staff_of(lead), _voice_of(lead))
                events.setdefault(key, []).append(event)
            for (staff, voice), in_scope in events.items():
                scope = (pid, ordinal, staff, voice)
                by_seq = wanted.get(scope)
                if by_seq is None:
                    continue
                seen.add(scope)
                for seq, direction in by_seq.items():
                    if seq >= len(in_scope):
                        inert.add(f"{pid}:m{ordinal}:s{staff}:"
                                  f"v{voice}:stem:{seq}")
                        continue
                    for note in in_scope[seq]:
                        _set_stem(note, direction.value)

    for scope, by_seq in wanted.items():
        if scope in seen:
            continue
        pid, ordinal, staff, voice = scope
        for seq in by_seq:
            inert.add(f"{pid}:m{ordinal}:s{staff}:v{voice}:stem:{seq}")
    return tuple(sorted(inert))
