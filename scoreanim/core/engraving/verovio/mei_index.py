"""MEI indexing: Verovio's MEI export → per-id musical lookup tables.

Pure XML in, plain dicts out — one _MeiIndex per load, read by every
downstream stage. Also home to the two other pure-XML helpers:
_set_scoredef_optimize (the hide-empty-staves round-trip marker) and
_container_ns (staff/layer @n by xml:id, shared by MEI and SVG).

Inputs: MEI XML text. Outputs: _MeiIndex / plain dicts. Touches no
_LoadState — this stage runs before it exists.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from scoreanim.core.engraving.verovio.kinds import (_ACCID_TO_ALTER,
                                                    _MEI_NS, _XML_ID)

# ---------------------------------------------------------------------------
# MEI-side tables (plan D2): musical attributes per Verovio id, one load.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _MeiNote:
    measure: int
    staff: int
    layer: int
    pname: str | None            # 'a'..'g'; None for unpitched
    alter: float
    octave: int | None
    loc: int | None              # staff position for unpitched notes
    grace: bool
    chord_id: str | None


@dataclass
class _MeiIndex:
    notes: dict[str, _MeiNote] = field(default_factory=dict)
    chord_members: dict[str, tuple[str, ...]] = field(default_factory=dict)
    beam_note_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # tremolo group id → its contained note ids, for onset propagation
    # (chord-member style; Phase 11 ruling a)
    tremolo_note_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # tuplet group id → its contained note ids: the tuplet bracket/number
    # decorate those notes, so they light with the tuplet's first note,
    # NOT the measure start (bug fix 2026-07-20)
    tuplet_note_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # beamSpan id → (startid, endid) note ids, its onset/extent source
    # (Phase 11 — not in the layer-beam table)
    beamspan_ends: dict[str, tuple[str | None, str | None]] = \
        field(default_factory=dict)
    spanners: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)
    spanner_tags: dict[str, str] = field(default_factory=dict)
    measure_by_id: dict[str, int] = field(default_factory=dict)
    # measure-attached elements (dynam, dir, tempo, harm...) → their @staff.
    # Spanners are recorded here too (Phase 5): hairpins carry @staff but
    # no startid, so this is their only staff source.
    staff_attr_by_id: dict[str, int] = field(default_factory=dict)
    # timestamp-addressed elements (hairpins AND dynamics — Phase 5
    # re-plan R.1): id → (measure_n, tstamp, tstamp2 or None). tstamp is
    # in meter units, 1-based; tstamp2 grammar is "<n>m+<beat>"
    # (n measures ahead) or a bare beat (same measure).
    tstamps_by_id: dict[str, tuple[int, str, str | None]] = \
        field(default_factory=dict)
    # measure-attached elements addressed by @startid (fermatas, trills,
    # ornaments; dynamics from non-Dorico exporters) — their animation
    # attach point (Phase 10R widened this beyond dynam)
    attach_startid: dict[str, str] = field(default_factory=dict)
    # active meter denominator per measure (document-order tracking of
    # meterSig), for tstamp → quarter-note conversion
    meter_unit_by_measure: dict[int, int] = field(default_factory=dict)
    # "label"|"labelAbbr" → that class's part labels in MEI document order.
    # The MEI half of the label→part join (M7); see _staff_labels.
    staff_labels: dict[str, tuple[StaffLabel, ...]] = \
        field(default_factory=dict)


def _int_or(value: str | None, fallback: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback


def _parse_mei(mei_xml: str) -> _MeiIndex:
    root = ET.fromstring(mei_xml)
    index = _MeiIndex()
    index.staff_labels.update(_staff_labels(root))

    def ref(value: str | None) -> str | None:
        return value.lstrip("#") if value else None

    # Document-order meter tracking: meterSig elements (initial scoreDef +
    # mid-score changes) precede the measures they govern. Needed to
    # convert spanner tstamps (meter units) to quarters (Phase 5 spike).
    unit = 4
    meter_ordinal = 0
    for el in root.iter():
        tag = el.tag.removeprefix(_MEI_NS)
        if tag == "meterSig" and el.get("unit"):
            unit = _int_or(el.get("unit"), unit)
        elif tag == "measure":
            meter_ordinal += 1
            # Measure IDENTITY is the 1-based document-order ordinal, never the
            # printed @n. The printed number is not unique or consistent across
            # music21/DOM/MEI (Dorico's "X0"/"X1" pickup/split bars collide with
            # real numbers under any int-fallback); the ordinal is (the k-th
            # <measure> is the same bar in all three, verified 1:1). Display
            # numbers live only in MeasureInfo.number.
            index.meter_unit_by_measure[meter_ordinal] = unit

    measure_ordinal = 0
    for measure in root.iter(f"{_MEI_NS}measure"):
        measure_ordinal += 1
        m_n = measure_ordinal
        m_id = measure.get(_XML_ID)
        if m_id:
            index.measure_by_id[m_id] = m_n
        for staff in measure.findall(f"{_MEI_NS}staff"):
            s_n = _int_or(staff.get("n"), 0)
            for layer in staff.findall(f"{_MEI_NS}layer"):
                l_n = _int_or(layer.get("n"), 1)
                _walk_layer(layer, index, m_n, s_n, l_n)
        for sp in measure:
            sp_id = sp.get(_XML_ID)
            if not sp_id:
                continue
            tag = sp.tag.removeprefix(_MEI_NS)
            if tag in ("slur", "tie", "hairpin", "octave", "lv"):
                index.spanners[sp_id] = (ref(sp.get("startid")),
                                         ref(sp.get("endid")))
                index.spanner_tags[sp_id] = tag
                if sp.get("tstamp"):
                    index.tstamps_by_id[sp_id] = (
                        m_n, sp.get("tstamp", "1"), sp.get("tstamp2"))
            elif tag in ("dynam", "fermata", "trill", "mordent", "turn",
                         "dir", "tempo", "reh", "harm"):
                # measure-attached objects animate at their attach point
                # (dynamics: ruling 2026-07-12; the rest: Phase 10R
                # animate-everything ruling). Dorico addresses texts and
                # dynamics by @tstamp+@staff, ornaments/fermatas by
                # @startid; both are honored.
                startid = ref(sp.get("startid"))
                if startid:
                    index.attach_startid[sp_id] = startid
                if sp.get("tstamp"):
                    index.tstamps_by_id[sp_id] = (
                        m_n, sp.get("tstamp", "1"), sp.get("tstamp2"))
            elif tag == "beamSpan":
                index.beamspan_ends[sp_id] = (ref(sp.get("startid")),
                                              ref(sp.get("endid")))
            staff_tokens = (sp.get("staff") or "").split()
            if staff_tokens:    # a whitespace-only @staff must not crash
                index.staff_attr_by_id[sp_id] = _int_or(staff_tokens[0], 0)
    return index


def _walk_layer(layer: ET.Element, index: _MeiIndex,
                m_n: int, s_n: int, l_n: int) -> None:
    def note_alter(note: ET.Element) -> float:
        accid = note.find(f"{_MEI_NS}accid")
        value = None
        if accid is not None:
            value = accid.get("accid.ges") or accid.get("accid")
        value = value or note.get("accid.ges") or note.get("accid")
        return _ACCID_TO_ALTER.get(value, 0.0)

    def visit(node: ET.Element, chord_id: str | None, grace_ctx: bool) -> list[str]:
        """Returns note ids in document order beneath node."""
        collected: list[str] = []
        tag = node.tag.removeprefix(_MEI_NS)
        node_id = node.get(_XML_ID)
        if tag == "note" and node_id:
            oct_str = node.get("oct")
            index.notes[node_id] = _MeiNote(
                measure=m_n, staff=s_n, layer=l_n,
                pname=node.get("pname"),
                alter=note_alter(node),
                octave=int(oct_str) if oct_str is not None else None,
                loc=_int_or(node.get("loc"), 0) if node.get("loc") else None,
                grace=grace_ctx or node.get("grace") is not None,
                chord_id=chord_id,
            )
            collected.append(node_id)
            return collected
        child_chord = node_id if tag == "chord" else chord_id
        child_grace = grace_ctx or tag == "graceGrp" or node.get("grace") is not None
        for child in node:
            collected.extend(visit(child, child_chord, child_grace))
        if tag == "chord" and node_id:
            index.chord_members[node_id] = tuple(collected)
        if tag == "beam" and node_id:
            index.beam_note_ids[node_id] = tuple(collected)
        if tag in ("bTrem", "fTrem") and node_id:
            index.tremolo_note_ids[node_id] = tuple(collected)
        if tag == "tuplet" and node_id:
            index.tuplet_note_ids[node_id] = tuple(collected)
        return collected

    for child in layer:
        visit(child, None, False)


def _set_scoredef_optimize(mei_xml: str) -> str:
    """Mark the score's first scoreDef optimize='true' — the encoding
    Verovio's condense honors for hiding empty staves per system."""
    ET.register_namespace("", _MEI_NS.strip("{}"))
    root = ET.fromstring(mei_xml)
    score_def = next(root.iter(f"{_MEI_NS}scoreDef"), None)
    if score_def is None:
        raise ValueError("MEI has no scoreDef to optimize")
    score_def.set("optimize", "true")
    return ET.tostring(root, encoding="unicode")


def _container_ns(mei_xml: str, tag: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for el in ET.fromstring(mei_xml).iter(f"{_MEI_NS}{tag}"):
        el_id = el.get(_XML_ID)
        if el_id and el.get("n"):
            result[el_id] = _int_or(el.get("n"), 0)
    return result


# Staff-label classes, in the two flavours Verovio draws: the full name on
# system 1, the abbreviation on later systems.
LABEL_CLASSES = ("label", "labelAbbr")


@dataclass(frozen=True)
class StaffLabel:
    """One part label in the MEI, and the staves it can be drawn beside."""
    text: str
    staves: tuple[int, ...]      # one staff for an ordinary part; all of a
                                 # multi-staff part's staves for a group label
    on_group: bool               # hangs on a <staffGrp>, not a <staffDef>


def staff_labels(mei_xml: str) -> dict[str, tuple[StaffLabel, ...]]:
    """`_staff_labels` from MEI text, for callers holding no root."""
    return _staff_labels(ET.fromstring(mei_xml))


def _staff_labels(root: ET.Element) -> dict[str, tuple[StaffLabel, ...]]:
    """Every part label per class, in MEI document order (= staff order).

    The MEI side of the label→part join (M7, measured in
    spikes/label_part.py and spikes/label_group.py). A label's own SVG id
    is a throwaway that does not exist in the MEI at all (0/129 measured),
    so this table plus document order is the only join there is.

    Two hosts, because a part's label hangs wherever its staves do:

    - an ordinary part on its own `<staffDef>`, which carries `@n`, the
      global staff number that PreparedScore.part_for_staff turns into a
      part;
    - a MULTI-STAFF part (a piano) on the `<staffGrp>` holding its
      staffDefs, so the label covers all of them. Verovio draws these
      FIRST, ahead of every staffDef label, which is why the join needs to
      know which host a label came from.

    A part with no abbreviation appears under "label" and not under
    "labelAbbr" — which is exactly the filter the join needs, because such
    a part draws nothing after system 1.
    """
    result: dict[str, list[StaffLabel]] = {cls: [] for cls in LABEL_CLASSES}
    for host in root.iter():
        tag = host.tag.removeprefix(_MEI_NS)
        if tag == "staffDef":
            staves = ((_int_or(host.get("n"), 0),) if host.get("n") else ())
        elif tag == "staffGrp":
            # only the staves DIRECTLY in this group: a nested group is a
            # part of its own and carries its own label
            staves = tuple(_int_or(sd.get("n"), 0)
                           for sd in host.findall(f"{_MEI_NS}staffDef")
                           if sd.get("n"))
        else:
            continue
        if not staves:
            continue                     # no @n anywhere: names no staff
        for cls in LABEL_CLASSES:
            label = host.find(f"{_MEI_NS}{cls}")
            if label is not None:
                result[cls].append(StaffLabel(
                    text="".join(label.itertext()).strip(),
                    staves=staves, on_group=(tag == "staffGrp")))
    return {cls: tuple(labels) for cls, labels in result.items()}
