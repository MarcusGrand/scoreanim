"""Stem-direction spike (kept) — the three Verovio facts the stem
feature rests on, measured before any of it was written.

Why this exists: Dorico exports the stem directions of the WRITTEN
score, but ScoreAnim engraves CONCERT PITCH (rule 9). Transposing moves
notes across the middle line and the exported `<stem>` does not follow,
so a transposing part comes out with stems on the wrong side. The fix is
to drop `<stem>` and let Verovio — the thing doing the transposition —
decide. That plan rests on three things nobody had checked:

Q1  Does stripping `<stem>` make Verovio apply the convention, on the
    pitch it actually draws? Measured geometrically (notehead centre
    against the middle staff line), so no pitch reasoning is needed.
Q2  Does a stem's `seq` in its ElementId follow note-event document
    order in the prepared MusicXML? This is what makes the per-note
    override key resolvable at the prep seam.
Q3  Which note events draw no stem at all? A stemless event must not
    consume a `seq`, or every index past it drifts.

Read-only w.r.t. the repo.

    python spikes/stem_dirs.py [fixture ...]

WHAT IT MEASURED (2026-08-03, 7 fixtures)

Q1 — stripping works, and the bug is big. Share of unbeamed
single-voice stems pointing the way the convention says:

    fixture        as exported   <stem> stripped
    testscore          77.2 %        100.0 %
    video_test         65.7 %        100.0 %
    complex1           86.7 %        100.0 %
    bigband1           70.9 %        100.0 %
    grieg_short        89.5 %        100.0 %
    brackets           93.5 %         99.6 %
    condense_min      100.0 %        100.0 %

So 6.5–34.3 % of these stems are drawn the wrong way today, and
dropping `<stem>` fixes all but one of them. Verovio also gets the
middle-line case right on its own (48 such notes across the set, all
stem-down), and it beams correctly — beamed groups are excluded from
the count above precisely because the group, not the note, owns the
direction there. The one holdout on brackets is inside the oracle's
own error bar: this check picks the head furthest from the middle line
by geometry, which is not how an engraver breaks every tie.

condense_min is NOT the pathology it looked like from a raw grep — its
68 stems really are all `down` because the music sits above the middle
line, and it scores 100 % either way.

Q2/Q3 — the key is safe. Over all 7 fixtures: **991 of 991 scopes had
exactly as many drawn stems as the prepared XML has stem-bearing note
events, and 0 scopes drew their stems out of x order.** So a stem's
`seq` IS the index of its note event, and `draws_a_stem` below — skip
rests, skip `<stem>none</stem>`, skip whole/breve/long/maxima — is the
right stemless predicate. The prep seam can resolve
`P1:m5:s1:v1:stem:2` by counting note events.
"""
from __future__ import annotations

import collections
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scoreanim.core.animation.scale_groups import stem_is_up  # noqa: E402
from scoreanim.core.engraving.types import EngravingParams  # noqa: E402
from scoreanim.core.engraving.verovio.provider import (  # noqa: E402
    VerovioEngravingProvider)
from scoreanim.core.score.identity import ElementKind  # noqa: E402

FIXTURES = ["testscore", "video_test", "complex1", "bigband1",
            "condense_min", "grieg_short", "brackets"]

# A note event draws no stem when its written value has none.
_STEMLESS_TYPES = {"whole", "breve", "long", "maxima"}


# ---------------------------------------------------------------------------
# The MusicXML side: note events, in document order
# ---------------------------------------------------------------------------

def note_events(measure: ET.Element) -> list[list[ET.Element]]:
    """Maximal `<note>` runs, each starting at a non-`<chord/>` note.
    Rests are not events. A chord is ONE event — its notes share a
    stem."""
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


def draws_a_stem(event: list[ET.Element]) -> bool:
    """Whether Verovio will draw a stem for this event (Q3)."""
    if any(n.findtext("stem") == "none" for n in event):
        return False
    types = {n.findtext("type") for n in event}
    return not (types & _STEMLESS_TYPES)


def xml_events(root: ET.Element) -> dict[tuple, list[list[ET.Element]]]:
    """(part, measure ordinal, staff, voice) -> its note events."""
    out: dict[tuple, list[list[ET.Element]]] = collections.defaultdict(list)
    for part in root.findall("part"):
        pid = part.get("id", "")
        for ordinal, measure in enumerate(part.findall("measure"), start=1):
            for event in note_events(measure):
                lead = event[0]
                staff = int(lead.findtext("staff", "1"))
                voice = int(lead.findtext("voice", "1"))
                out[(pid, ordinal, staff, voice)].append(event)
    return out


# ---------------------------------------------------------------------------
# The engraved side
# ---------------------------------------------------------------------------

def load(path: Path, strip: bool = False):
    """Engrave a fixture. With strip=True, every `<stem>` is removed
    from a temporary copy first — Q1's 'let Verovio decide' render."""
    src = path
    if strip:
        root = ET.fromstring(path.read_bytes())
        for note in root.iter("note"):
            for stem in note.findall("stem"):
                note.remove(stem)
        src = Path(OUT / f"{path.stem}_nostem.musicxml")
        src.write_bytes(ET.tostring(root, encoding="utf-8"))
    provider = VerovioEngravingProvider()
    return provider.load_detailed(src, EngravingParams(), strict=False)


def stems_by_scope(layout) -> dict[tuple, list]:
    """(part, measure, staff, voice) -> STEM elements, in seq order.
    The measure ordinal comes out of the id, which is where it lives."""
    out: dict[tuple, list] = collections.defaultdict(list)
    for el in layout.elements:
        ident = el.identity
        if ident.kind is not ElementKind.STEM or ident.part is None:
            continue
        eid = str(ident.element_id)
        if ":seg" in eid:
            continue
        parts = eid.split(":")
        ordinal = int(parts[1][1:])
        seq = int(parts[-1])
        out[(ident.part, ordinal, ident.staff, ident.voice)].append((seq, el))
    return {k: [el for _, el in sorted(v)] for k, v in out.items()}


def heads_by_scope(layout) -> dict[tuple, list]:
    out: dict[tuple, list] = collections.defaultdict(list)
    for el in layout.elements:
        ident = el.identity
        if ident.kind is not ElementKind.NOTEHEAD or ident.part is None:
            continue
        eid = str(ident.element_id)
        if ":seg" in eid:
            continue
        ordinal = int(eid.split(":")[1][1:])
        out[(ident.part, ordinal, ident.staff, ident.voice)].append(el)
    return out


def staff_middles(layout) -> dict[tuple, float]:
    """(part, staff, page, system) -> y of the middle staff line, read
    off the drawn STAFF_LINES box."""
    out: dict[tuple, float] = {}
    for el in layout.elements:
        ident = el.identity
        if ident.kind is not ElementKind.STAFF_LINES or ident.part is None:
            continue
        out[(ident.part, ident.staff, el.page, el.system)] = el.bbox.center.y
    return out


# ---------------------------------------------------------------------------
# Q2 + Q3: does seq follow document order, and what is stemless?
# ---------------------------------------------------------------------------

def check_counts(name: str, engraved) -> tuple[int, int]:
    root = ET.fromstring(engraved.prepared.canonical_xml)
    xml = xml_events(root)
    stems = stems_by_scope(engraved.layout)

    scopes = set(xml) | set(stems)
    agree = disagree = 0
    examples: list[str] = []
    for scope in sorted(scopes, key=str):
        expected = [e for e in xml.get(scope, []) if draws_a_stem(e)]
        drawn = stems.get(scope, [])
        if len(expected) == len(drawn):
            agree += 1
        else:
            disagree += 1
            if len(examples) < 6:
                examples.append(f"      {scope}: xml wants {len(expected)}, "
                                f"drawn {len(drawn)}")

    # Ordering: within a scope, seq should climb with x. A measure runs
    # left to right in time, so if that holds and the counts match, seq
    # IS the note-event index.
    out_of_order = 0
    for scope, drawn in stems.items():
        xs = [el.bbox.center.x for el in drawn]
        if xs != sorted(xs):
            out_of_order += 1

    print(f"  Q2/Q3  scopes matching: {agree}/{agree + disagree}"
          f"   x-order violations: {out_of_order}/{len(stems)}")
    for line in examples:
        print(line)
    return disagree, out_of_order


# ---------------------------------------------------------------------------
# Q1: with <stem> gone, does Verovio follow the convention?
# ---------------------------------------------------------------------------

def check_convention(name: str, engraved) -> None:
    """For every UNBEAMED single-voice stem, does it point the way the
    convention says — away from the middle line? Purely geometric: no
    pitch, no clef, no transposition arithmetic."""
    root = ET.fromstring(engraved.prepared.canonical_xml)
    xml = xml_events(root)
    stems = stems_by_scope(engraved.layout)
    heads = heads_by_scope(engraved.layout)
    middles = staff_middles(engraved.layout)

    # which (part, measure, staff) carry exactly one voice
    voices: dict[tuple, set] = collections.defaultdict(set)
    for (pid, ordinal, staff, voice) in xml:
        voices[(pid, ordinal, staff)].add(voice)

    agree = disagree = onliner = skipped = 0
    for scope, drawn in stems.items():
        pid, ordinal, staff, voice = scope
        if len(voices.get((pid, ordinal, staff), ())) != 1:
            continue
        events = [e for e in xml.get(scope, []) if draws_a_stem(e)]
        if len(events) != len(drawn):
            skipped += len(drawn)
            continue
        scope_heads = heads.get(scope, [])
        for event, stem in zip(events, drawn):
            if any(n.find("beam") is not None or n.find("grace") is not None
                   for n in event):
                continue
            mid = middles.get((pid, staff, stem.page, stem.system))
            if mid is None:
                skipped += 1
                continue
            near = [h for h in scope_heads
                    if abs(h.bbox.center.x - stem.bbox.center.x) < 30
                    and h.page == stem.page]
            if not near:
                skipped += 1
                continue
            up = stem_is_up(stem, near)
            far = max(near, key=lambda h: abs(h.bbox.center.y - mid))
            offset = far.bbox.center.y - mid
            if abs(offset) < 1e-6:
                onliner += 1
                # convention: a note ON the middle line takes a down stem
                disagree += int(up)
                agree += int(not up)
                continue
            # y grows downward: below the middle line -> stem up
            agree += int(up == (offset > 0))
            disagree += int(up != (offset > 0))
    total = agree + disagree
    pct = 100 * agree / total if total else 0.0
    print(f"  Q1     convention held: {agree}/{total} ({pct:.1f}%)"
          f"   middle-line notes: {onliner}   unmeasurable: {skipped}")


def main() -> None:
    names = sys.argv[1:] or FIXTURES
    bad_counts = bad_order = 0
    for name in names:
        path = Path("testdata") / f"{name}.musicxml"
        if not path.exists():
            print(f"{name}: no such fixture")
            continue
        print(f"\n=== {name} ===")
        as_is = load(path)
        print("  as exported:")
        d, o = check_counts(name, as_is)
        bad_counts += d
        bad_order += o
        check_convention(name, as_is)

        stripped = load(path, strip=True)
        print("  <stem> stripped:")
        check_counts(name, stripped)
        check_convention(name, stripped)

    print("\n" + "=" * 66)
    print(f"Q2/Q3 verdict: {bad_counts} scope count mismatches, "
          f"{bad_order} x-order violations, over the as-exported loads.")
    print("Both must be 0 for the ElementId seq to be a usable prep-seam key.")


OUT = Path("spikes/out")

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    main()
