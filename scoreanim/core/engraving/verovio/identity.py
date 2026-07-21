"""Identity minting and element construction: accumulators →
RenderedElements + AdapterNoteRecords.

_identity_for mints deterministic ElementIds from musical position
(part/measure/staff/voice/kind/index) and resolves each element's onset
— the svg_class-gated chain (Phase 10R id-reuse fix, 2026-07-20 tuplet
fix live here). _build_elements runs it over every accumulator, then
constructs continuation-segment elements under their source's ":seg<k>"
ids in a second pass.

Inputs: the attributed accumulator list + _LoadState. Outputs:
RenderedElements, AdapterNoteRecords, and the staff-lines geometry map
synthesis positions from. _LoadState READS: prep, mei, onset_by_id,
measure_start, staff_centers_by_system (grpSym span),
suppressed_spanners. WRITES: warnings ("unattributed-continuation").
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from scoreanim.core.animation.schedule import REVEALED_KINDS, STATIC_KINDS
from scoreanim.core.engraving.types import (LoadWarning, Rect,
                                            RenderedElement,
                                            RenderPrimitive)
from scoreanim.core.engraving.verovio.attribution import _tstamp_extent
from scoreanim.core.engraving.verovio.decompose import _ElementAccumulator
from scoreanim.core.engraving.verovio.kinds import (_ID_TAG,
                                                    _SPANNER_CLASSES,
                                                    _STATIC_TEXT_CLASSES,
                                                    _TIMEMAP_CLASSES)
from scoreanim.core.engraving.verovio.mei_index import _MeiNote
from scoreanim.core.engraving.verovio.records import (AdapterNoteRecord,
                                                      _LoadState)
from scoreanim.core.score.identity import (Beats, ElementId,
                                           ElementIdentity, ElementKind)
from scoreanim.core.score.musicxml_prep import PartInfo

# ---------------------------------------------------------------------------
# Identity minting (plan D5) and element construction
# ---------------------------------------------------------------------------

def _build_elements(
    accumulators: list[tuple[int, _ElementAccumulator]],
    st: _LoadState,
) -> tuple[list[RenderedElement], list[AdapterNoteRecord],
           dict[tuple, tuple[int, int | None, Rect]]]:
    counters: dict[tuple, int] = defaultdict(int)
    elements: list[RenderedElement] = []
    note_records: list[AdapterNoteRecord] = []
    voice_order: dict[tuple, int] = defaultdict(int)
    seen_ids: set[str] = set()
    identity_by_vid: dict[str, ElementIdentity] = {}
    # (part_id, measure, staff_local) → (page, system, staff-lines bbox),
    # for slash synthesis
    staff_geo: dict[tuple, tuple[int, int | None, Rect]] = {}

    for page, acc in accumulators:
        if acc.continuation:
            continue                     # second pass, after sources exist
        if acc.verovio_id in st.suppressed_spanners:
            continue                     # implausible tie: no element
        identity = _identity_for(acc, page, st, counters)
        if str(identity.element_id) in seen_ids:
            raise ValueError(f"duplicate ElementId {identity.element_id}")
        seen_ids.add(str(identity.element_id))
        if acc.verovio_id:
            identity_by_vid[acc.verovio_id] = identity

        if acc.bbox is None:
            continue
        anchor = acc.bbox.center
        if len(acc.use_origins) == 1 and not acc.texts:
            x, y = acc.use_origins[0].x, acc.use_origins[0].y
        else:
            x, y = anchor.x, anchor.y
        elements.append(RenderedElement(
            identity=identity, page=page, x=x, y=y, bbox=acc.bbox,
            anchor=anchor,
            glyph=RenderPrimitive(paths=tuple(acc.paths),
                                  texts=tuple(acc.texts)),
            system=acc.system,
            text_class=(acc.svg_class
                        if acc.kind is ElementKind.TEXT else None),
        ))

        if (identity.kind is ElementKind.STAFF_LINES
                and identity.part is not None and acc.measure is not None):
            staff_geo[(identity.part, acc.measure, identity.staff)] = \
                (page, acc.system, acc.bbox)

        if acc.svg_class == "note":
            mei_note = st.mei.notes.get(acc.verovio_id)
            onset = st.onset_by_id.get(acc.verovio_id)
            if mei_note is None or onset is None:
                raise ValueError(f"note {acc.verovio_id} missing from "
                                 f"MEI/timemap — join bridge broken")
            part = st.prep.part_for_staff(mei_note.staff)
            vkey = (part.part_id, mei_note.measure, mei_note.staff,
                    mei_note.layer)
            order = voice_order[vkey]
            voice_order[vkey] += 1
            note_records.append(AdapterNoteRecord(
                element_id=identity.element_id,
                part=part.part_id,
                measure=mei_note.measure,
                staff=mei_note.staff - part.first_staff + 1,
                voice=mei_note.layer,
                onset=onset,
                grace=mei_note.grace,
                pitch_step=mei_note.pname.upper() if mei_note.pname else None,
                pitch_alter=mei_note.alter,
                octave=mei_note.octave,
                staff_loc=mei_note.loc,
                chord_group=_chord_group(mei_note, st, part),
                order_in_voice=order,
            ))

    # Second pass: continuation segments inherit the source spanner's
    # identity under a ":seg<k>" id — deterministic because segment
    # matching and system order are (per-element overrides on a broken
    # spanner therefore target one segment, documented in the plan).
    for page, acc in accumulators:
        if not acc.continuation:
            continue
        if acc.source_vid in st.suppressed_spanners:
            continue    # its source tie is suppressed: drop the ink too
        source = identity_by_vid.get(acc.source_vid or "")
        if source is None or acc.bbox is None:
            # unmatched continuation ink: skip, flagged (ruling b) —
            # never silently absorbed into another element
            st.warnings.append(LoadWarning(
                "unattributed-continuation",
                f"{acc.svg_class} continuation segment in system "
                f"{acc.system} matched no source spanner — skipped"))
            continue
        eid = f"{source.element_id}:seg{acc.seg_index}"
        if eid in seen_ids:
            raise ValueError(f"duplicate ElementId {eid}")
        seen_ids.add(eid)
        identity = replace(source, element_id=ElementId(eid))
        elements.append(RenderedElement(
            identity=identity, page=page,
            x=acc.bbox.center.x, y=acc.bbox.center.y,
            bbox=acc.bbox, anchor=acc.bbox.center,
            glyph=RenderPrimitive(paths=tuple(acc.paths),
                                  texts=tuple(acc.texts)),
            system=acc.system,
        ))
    return elements, note_records, staff_geo


def _chord_group(mei_note: _MeiNote, st: _LoadState,
                 part: "PartInfo") -> str | None:
    """Neutral per-chord token: (part, measure, voice, onset-of-chord)."""
    if mei_note.chord_id is None:
        return None
    first = next(iter(st.mei.chord_members.get(mei_note.chord_id, ())), None)
    onset = st.onset_by_id.get(first) if first else None
    return f"{part.part_id}:m{mei_note.measure}:v{mei_note.layer}:q{onset}"


def _attach_onset(st: _LoadState, vid: str) -> Beats | None:
    """Attach point of a measure-attached object: @startid's note onset
    (a chord reference resolves through its first member), else @tstamp
    arithmetic. None when the element carries neither."""
    ref = st.mei.attach_startid.get(vid)
    if ref:
        if ref in st.onset_by_id:
            return st.onset_by_id[ref]
        member = next(iter(st.mei.chord_members.get(ref, ())), None)
        if member and member in st.onset_by_id:
            return st.onset_by_id[member]
    if vid in st.mei.tstamps_by_id:
        return _tstamp_extent(st.mei.tstamps_by_id[vid], st)[0]
    return None


def _identity_for(acc: _ElementAccumulator, page: int, st: _LoadState,
                  counters: dict[tuple, int]) -> ElementIdentity:
    prep = st.prep
    kind_tag = _ID_TAG[acc.kind] if acc.svg_class != "dots" else "dots"
    if acc.svg_class == "note":
        kind_tag = "note"

    if acc.kind is ElementKind.GROUP_SYMBOL:
        # Geometric identity (Phase 10, replacing the injected-slot
        # ordinal): the symbol's bbox says which staves it spans, and
        # part_for_staff turns that into a part span — self-identifying
        # for injected groups AND native ones (a multi-staff part's
        # brace, foreign part-groups). Slot bookkeeping cannot work:
        # Verovio SUPPRESSES a native brace when an injected group
        # overlaps its part (triage spike, section E). Injected groups
        # keep their exact Phase 8 ids (score:sys{n}:grpsym:P1-P2); a
        # multi-staff part's own brace mints its part id alone
        # (score:sys{n}:grpsym:P5).
        if acc.system is None or acc.bbox is None:
            raise ValueError("group symbol without system/bbox")
        centers = st.staff_centers_by_system.get(acc.system, {})
        covered = sorted(n for n, cy in centers.items()
                         if acc.bbox.y <= cy <= acc.bbox.y + acc.bbox.h)
        if not covered or covered != list(range(covered[0],
                                                covered[-1] + 1)):
            raise ValueError(
                f"group symbol in system {acc.system} spans staves "
                f"{covered} — expected a contiguous non-empty range")
        first = prep.part_for_staff(covered[0])
        last = prep.part_for_staff(covered[-1])
        if first is last and first.staff_count > 1:
            span = first.part_id             # native grand-staff brace
        else:
            span = f"{first.part_id}-{last.part_id}"
        return ElementIdentity(
            element_id=ElementId(f"score:sys{acc.system}:grpsym:{span}"),
            kind=acc.kind, part=None, part_name=None, staff=None,
            voice=None, onset=None, extent=None,
        )

    if acc.kind is ElementKind.SYSTEM_DIVIDER:
        scope = ("systemdivider", acc.system)
        seq = counters[scope]
        counters[scope] += 1
        return ElementIdentity(
            element_id=ElementId(
                f"score:sys{acc.system}:systemdivider:{seq}"),
            kind=acc.kind, part=None, part_name=None, staff=None,
            voice=None, onset=None, extent=None,
        )

    # staff: from SVG nesting; measure-attached elements (dynam, dir…)
    # carry it as an MEI @staff attribute; spanners inherit their start
    # note's staff and voice.
    staff_n = acc.staff or st.mei.staff_attr_by_id.get(acc.verovio_id)
    layer_n = acc.layer
    is_spanner = acc.svg_class in _SPANNER_CLASSES
    if is_spanner and acc.verovio_id in st.mei.spanners:
        start_id, _ = st.mei.spanners[acc.verovio_id]
        start_note = st.mei.notes.get(start_id or "")
        if start_note is not None:
            staff_n = staff_n or start_note.staff
            layer_n = layer_n if layer_n is not None else start_note.layer

    part = part_name = None
    staff_local = None
    if staff_n:
        info = prep.part_for_staff(staff_n)
        part, part_name = info.part_id, info.name
        staff_local = staff_n - info.first_staff + 1

    # Onset resolution is GATED BY svg_class so a note-owned fragment
    # never picks up a spurious onset from its own id: under condensed
    # layout Verovio reuses SVG group ids across element types, so a
    # stem's id can collide with a distant note/spanner id. Only the
    # element type the table is FOR may consult it (Phase 10R fix).
    onset: Beats | None = None
    extent: tuple[Beats, Beats] | None = None
    vid = acc.verovio_id
    if acc.svg_class in _TIMEMAP_CLASSES and vid in st.onset_by_id:
        onset = st.onset_by_id[vid]
    elif is_spanner and vid in st.mei.spanners:
        start_id, end_id = st.mei.spanners[vid]
        start = st.onset_by_id.get(start_id or "")
        end = st.onset_by_id.get(end_id or "")
        if start is not None:
            onset = start
            extent = (start, end if end is not None else start)
        elif vid in st.mei.tstamps_by_id:
            # timestamp-addressed spanner (hairpins carry @tstamp/@tstamp2
            # and @staff, no startid/endid — Phase 5 spike)
            onset, extent = _tstamp_extent(st.mei.tstamps_by_id[vid], st)
    elif acc.svg_class == "beam" and vid in st.mei.beam_note_ids:
        onsets = [st.onset_by_id[n] for n in st.mei.beam_note_ids[vid]
                  if n in st.onset_by_id]
        if onsets:
            onset = min(onsets)
            extent = (min(onsets), max(onsets))
    elif acc.svg_class == "beamSpan" and vid in st.mei.beamspan_ends:
        # a beamSpan is a measure-level beam: its onset/extent come from
        # its @startid/@endid note onsets, not the layer-beam table
        start_id, end_id = st.mei.beamspan_ends[vid]
        ends = [st.onset_by_id[n] for n in (start_id, end_id)
                if n and n in st.onset_by_id]
        if ends:
            onset = min(ends)
            extent = (min(ends), max(ends))
    elif acc.owner_onset is not None:
        onset = acc.owner_onset          # stems, flags, accid, artic, dots
    elif (attach := _attach_onset(st, vid)) is not None:
        # a measure-attached object's onset is its attach point
        # (dynamics: ruling 2026-07-12; fermatas, trills/ornaments,
        # dirs, tempo, harm: Phase 10R)
        onset = attach
    elif acc.measure is not None \
            and acc.kind not in STATIC_KINDS \
            and acc.kind not in REVEALED_KINDS \
            and acc.svg_class not in _STATIC_TEXT_CLASSES:
        # Measure-start fallback for an attach-less, non-scaffold object
        # (animate-everything ruling 2026-07-20): clefs, key signatures,
        # meter changes, and measure-attached texts/dynamics light when
        # their measure begins. NOTE-REGION decorations do NOT reach here
        # — tuplets/tremolos inherit their notes' onset via owner_onset
        # (else this fallback would fire them at the downbeat, before
        # their first note — the 2026-07-20 tuplet bug). Spanners
        # (REVEALED_KINDS) are excluded too: a slur/tie/hairpin's timing
        # is its start note or nothing, never a spurious downbeat — if
        # its start is unresolved it stays onset-less (its reveal is
        # edge-driven regardless). Scaffold (STATIC_KINDS) and page
        # furniture (_STATIC_TEXT_CLASSES) stay onset-less = static.
        onset = st.measure_start.get(acc.measure)

    # spanners for notes were handled; note extent stays None in v1

    if acc.measure is not None and part is not None:
        scope = (part, acc.measure, staff_local, layer_n, kind_tag)
        seq = counters[scope]
        counters[scope] += 1
        eid = (f"{part}:m{acc.measure}:s{staff_local}:"
               f"v{layer_n if layer_n is not None else 0}:{kind_tag}:{seq}")
    elif acc.measure is not None:
        scope = ("score", acc.measure, kind_tag)
        seq = counters[scope]
        counters[scope] += 1
        eid = f"score:m{acc.measure}:{kind_tag}:{seq}"
    else:
        scope = ("page", page, kind_tag)
        seq = counters[scope]
        counters[scope] += 1
        eid = f"score:p{page}:{kind_tag}:{seq}"

    return ElementIdentity(
        element_id=ElementId(eid), kind=acc.kind,
        part=part, part_name=part_name, staff=staff_local,
        voice=layer_n, onset=onset, extent=extent,
    )
