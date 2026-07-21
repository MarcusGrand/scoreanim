"""Verovio adapter: MusicXML → identity-tagged, paged Layout (plan D2/D3/D5).

Verovio types, ids, and SVG never leak past this module (CLAUDE.md rule 4).
ElementIds are minted here from musical identity (part/measure/staff/voice/
kind/index), so they are deterministic across loads and survive engraving
reflows. A fixed xmlIdSeed keeps Verovio's internal ids reproducible for
the timemap ↔ SVG ↔ MEI cross-referencing inside a load.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path

import verovio

from scoreanim.core.animation.schedule import REVEALED_KINDS, STATIC_KINDS
from scoreanim.core.engraving.provider import EngravingProvider
from scoreanim.core.engraving.systems import plan_page_breaks, system_bands
from scoreanim.core.engraving.svg_geom import (ellipse_path, line_path,
                                               parse_transform, path_bbox,
                                               polygon_path, rect_path)
from scoreanim.core.engraving.types import (TRANSPOSE_TO_SOUNDING_PITCH,
                                            Affine, EngravingParams, Layout,
                                            LoadWarning, PageGeometry,
                                            PathPrimitive, Point, Rect,
                                            RenderedElement, RenderPrimitive,
                                            TextPrimitive, TextRun)
from scoreanim.core.score.identity import (Beats, ElementId, ElementIdentity,
                                           ElementKind, PartId)
from scoreanim.core.score.musicxml_prep import (PartCondenseSpec,
                                                PartGroupSpec, PartInfo,
                                                PartTextSpec, PreparedScore,
                                                prepare)
from scoreanim.core.engraving.verovio.kinds import (
    _ACCID_TO_ALTER, _BOLD_TEXT_CLASSES, _CONTAINER_CLASSES, _DEFAULT_SCALE,
    _FIT_MARGIN, _ID_TAG, _ITALIC_TEXT_CLASSES, _KIND_BY_CLASS, _MEI_NS,
    _SPANNER_CLASSES, _STATIC_TEXT_CLASSES, _SVG_NS, _TIMEMAP_CLASSES,
    _XLINK_HREF, _XML_ID)
from scoreanim.core.engraving.verovio.mei_index import (
    _MeiIndex, _MeiNote, _container_ns, _int_or, _parse_mei,
    _set_scoredef_optimize, _walk_layer)
from scoreanim.core.engraving.verovio.records import (
    AdapterNoteRecord, EngravedScore, _LoadState)
from scoreanim.core.engraving.verovio.decompose import (
    _ElementAccumulator, _PageDecomposer, _RunAttrs)
from scoreanim.core.engraving.verovio.attribution import (
    _attribute_ledger_dashes, _attribute_spanner_segments,
    _flag_implausible_ties, _rehome_stray_paths,
    _tstamp2_end_measure, _tstamp_extent)



# ---------------------------------------------------------------------------
# Load orchestration
# ---------------------------------------------------------------------------

class VerovioEngravingProvider(EngravingProvider):
    """MusicXML → Layout via Verovio, honoring encoded breaks and rendering
    at concert pitch (octave-only transpositions neutralized in prep)."""

    def load(self, score_path: Path, params: EngravingParams,
             groups: tuple[PartGroupSpec, ...] = (),
             texts: tuple[PartTextSpec, ...] = (),
             hide_empty_staves: bool = False,
             condense: tuple[PartCondenseSpec, ...] = (),
             strict: bool = True) -> Layout:
        return self.load_detailed(score_path, params, groups, texts,
                                  hide_empty_staves, condense, strict).layout

    def load_detailed(self, score_path: Path, params: EngravingParams,
                      groups: tuple[PartGroupSpec, ...] = (),
                      texts: tuple[PartTextSpec, ...] = (),
                      hide_empty_staves: bool = False,
                      condense: tuple[PartCondenseSpec, ...] = (),
                      strict: bool = True) -> EngravedScore:
        # strict (Phase 11.4): when False (the app path) an unknown
        # drawable SVG class degrades to a static OTHER element plus a
        # "unknown-class" warning instead of raising; True (the default,
        # and pytest / the doctor's --strict) keeps coverage gaps loud.
        prep = prepare(score_path, groups, texts, condense)
        extra: list[LoadWarning] = []
        effective_hide = hide_empty_staves
        engraved, first_measure = self._engrave_prepared(
            score_path, prep, params, effective_hide, strict)
        if engraved is None:
            # Hiding made a slash- or bar-repeat-region staff vanish
            # (Verovio judges both empty — MEI <space>). Both are
            # first-class (rule 10 family), so they win over the option:
            # engrave flat, flagged (spikes/NOTES.md Phase 10R / 12).
            effective_hide = False
            extra.append(LoadWarning(
                "hide-unavailable",
                "a slash- or bar-repeat-region staff would be hidden; "
                "empty-staff hiding skipped for this score"))
            engraved, first_measure = self._engrave_prepared(
                score_path, prep, params, effective_hide, strict)
            assert engraved is not None

        # Never-clip guard (Phase 10R, rule-7 amendment): when the
        # encoded page breaks cannot hold their systems (e.g. Dorico
        # breaks computed assuming hidden staves), keep the encoded
        # SYSTEM breaks and repaginate ourselves at the prep seam.
        # Page-scoped ids (score:p{n}:…) shift — accepted; musical ids
        # are pagination-independent.
        page_h = engraved.layout.pages[0].height
        bands = system_bands(engraved.layout)
        breaks: tuple[int, ...] = ()
        if any(b.rect.y + b.rect.h > page_h for b in bands):
            breaks = plan_page_breaks(bands, page_h, first_measure)
            if breaks:
                prep = prepare(score_path, groups, texts, condense,
                               page_break_measures=breaks)
                engraved, _ = self._engrave_prepared(
                    score_path, prep, params, effective_hide, strict)
                assert engraved is not None    # same flag that succeeded
                extra.append(LoadWarning(
                    "repaginated",
                    f"systems overflowed the encoded page height; "
                    f"{len(breaks)} page break(s) re-derived "
                    f"(before measures "
                    f"{', '.join(str(m) for m in breaks)})"))

            # A single system taller than its page cannot be paginated
            # away (Dorico sized the page for its condensed score). Scale
            # the engraving down uniformly so the tallest system fits —
            # the never-clip completion (Phase 12.5, rule 7). Derived
            # every load from the measured overflow, never stored (rule 5).
            bands = system_bands(engraved.layout)
            bottom = max((b.rect.y + b.rect.h for b in bands), default=0.0)
            if bottom > page_h:
                fit = max(1, int(_DEFAULT_SCALE * page_h / bottom * _FIT_MARGIN))
                prep = prepare(score_path, groups, texts, condense,
                               page_break_measures=breaks)
                engraved, _ = self._engrave_prepared(
                    score_path, prep, params, effective_hide, strict,
                    scale=fit)
                assert engraved is not None
                extra.append(LoadWarning(
                    "scaled-to-fit",
                    f"the tallest system exceeded the page height; the "
                    f"engraving was scaled to {fit}% so nothing is clipped"))
                for b in system_bands(engraved.layout):
                    if b.rect.y + b.rect.h > page_h:
                        extra.append(LoadWarning(
                            "system-overflow",
                            f"system {b.system} still overflows page "
                            f"{b.page} after scale-to-fit"))
        if extra:
            engraved = replace(engraved,
                               warnings=engraved.warnings + tuple(extra))
        return engraved

    @staticmethod
    def _make_toolkit(prep: PreparedScore,
                      params: EngravingParams,
                      scale: int | None = None) -> "verovio.toolkit":
        tk = verovio.toolkit()
        tk.setOptions({
            "breaks": "encoded",
            "font": "Bravura",
            "pageWidth": round(prep.page_width),
            "pageHeight": round(prep.page_height),
            "scaleToPageSize": True,
            "header": "none" if params.suppress_header else "encoded",
            "footer": "encoded",
            "svgHtml5": False,
            "svgViewBox": True,
            "transposeToSoundingPitch": TRANSPOSE_TO_SOUNDING_PITCH,
            "xmlIdSeed": params.xml_id_seed,
            # Verovio's default condense:"auto" silently switches to
            # condensed layout once a score has 2+ staff groups — hiding
            # empty staves per system and drawing systemDividers. That is
            # engraver-derived reflow, which rule 7 forbids; "encoded"
            # honors only what the file encodes. Verified byte-identical
            # for 0- and 1-group renders (Phase 10 triage spike). A fixed
            # rule like transposeToSoundingPitch, not a params field.
            # Hide-empty-staves (Phase 10R) opts IN per score by setting
            # scoreDef@optimize on the MEI round-trip — condense stays
            # "encoded" either way.
            "condense": "encoded",
            # Condensed layouts draw between-system dividers by default;
            # Dorico's default look has none (Phase 10R spike). The
            # SYSTEM_DIVIDER decomposer support stays as defense.
            "systemDivider": "none",
        })
        # Scale-to-fit (Phase 12.5, never-clip completion): a uniform
        # staff-size reduction so a system taller than the page fits
        # (rule 7 — an engraving input like Dorico's rastral size, not
        # window reflow). None keeps Verovio's default (100).
        if scale is not None:
            tk.setOptions({"scale": scale})
        return tk

    def _engrave_prepared(self, score_path: Path, prep: PreparedScore,
                          params: EngravingParams,
                          hide_empty_staves: bool,
                          strict: bool = True,
                          scale: int | None = None
                          ) -> tuple[EngravedScore | None, dict[int, int]]:
        """One full engrave+decompose; also returns the first measure
        of every system (for the repagination planner). The score is
        None only when hide_empty_staves hid a slash-region staff (the
        caller retries flat). `scale` (Phase 12.5) shrinks the engraving
        uniformly so a too-tall system fits the page (never-clip)."""
        tk = self._make_toolkit(prep, params, scale)
        if not tk.loadData(prep.canonical_xml):
            raise ValueError(f"Verovio failed to load {score_path}")
        if hide_empty_staves:
            # Two-pass load: Verovio honors hidden empty staves only via
            # MEI scoreDef@optimize (staff-details print-object and
            # staffDef@visible are ignored). The round-trip is id- and
            # timemap-transparent (Phase 10R spike, section A).
            mei_text = _set_scoredef_optimize(tk.getMEI())
            tk = self._make_toolkit(prep, params, scale)
            if not tk.loadData(mei_text):
                raise ValueError(
                    f"Verovio failed to reload optimized MEI for "
                    f"{score_path}")

        mei = _parse_mei(tk.getMEI())
        timemap = tk.renderToTimemap({"includeMeasures": True,
                                      "includeRests": True})
        onset_by_id: dict[str, Beats] = {}
        measure_start: dict[int, Beats] = {}
        for entry in timemap:
            q = float(entry["qstamp"])
            for vid in entry.get("on", []):
                onset_by_id[vid] = q
            for vid in entry.get("restsOn", []):
                onset_by_id[vid] = q
            m_id = entry.get("measureOn")
            if m_id and m_id in mei.measure_by_id:
                measure_start.setdefault(mei.measure_by_id[m_id], q)

        score_end = max(float(e["qstamp"]) for e in timemap)
        starts = sorted(measure_start.items(), key=lambda kv: kv[1])
        measure_duration = {
            n: (starts[i + 1][1] if i + 1 < len(starts) else score_end) - q
            for i, (n, q) in enumerate(starts)
        }

        state = _LoadState(
            prep=prep, mei=mei, onset_by_id=onset_by_id,
            measure_start=measure_start, measure_duration=measure_duration,
            staff_n_by_id={vid: n.staff for vid, n in mei.notes.items()},
            layer_n_by_id={}, strict=strict,
        )
        # staff/layer container ids appear in both MEI and SVG; index them
        state.staff_n_by_id.update(_container_ns(tk.getMEI(), "staff"))
        state.layer_n_by_id.update(_container_ns(tk.getMEI(), "layer"))

        page_count = tk.getPageCount()
        pages = tuple(PageGeometry(number=p, width=prep.page_width,
                                   height=prep.page_height)
                      for p in range(1, page_count + 1))

        accumulators: list[tuple[int, _ElementAccumulator]] = []
        for page in range(1, page_count + 1):
            for acc in _PageDecomposer(tk.renderToSVG(page), page, state).run():
                accumulators.append((page, acc))

        # staff y-centers per system, for geometric grpSym identity
        for _, acc in accumulators:
            if (acc.svg_class == "staff" and acc.bbox is not None
                    and acc.staff and acc.system is not None):
                state.staff_centers_by_system.setdefault(
                    acc.system, {}).setdefault(
                    acc.staff, acc.bbox.y + acc.bbox.h / 2)

        _rehome_stray_paths(accumulators, state)
        _attribute_ledger_dashes(accumulators, state)
        _attribute_spanner_segments(accumulators, state)
        _flag_implausible_ties(state)
        elements, note_records, staff_geo = _build_elements(accumulators, state)
        first_measure: dict[int, int] = {}
        for measure_n, system_n in state.system_of_measure.items():
            if measure_n < first_measure.get(system_n, 1 << 30):
                first_measure[system_n] = measure_n
        if hide_empty_staves and any(
                (region.part, m, 1) not in staff_geo
                for region in (*prep.slash_regions, *prep.repeat_regions)
                for m in range(region.start_measure, region.stop_measure)):
            return None, first_measure   # caller retries flat (rule 10)
        elements.extend(_synthesize_slashes(state, staff_geo))
        elements.extend(_synthesize_repeats(state, staff_geo))
        layout = Layout(pages=pages, elements=tuple(elements))
        return EngravedScore(layout=layout,
                             note_records=tuple(note_records),
                             prepared=prep,
                             warnings=tuple(state.warnings)), first_measure


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


# ---------------------------------------------------------------------------
# Slash synthesis (CLAUDE.md rule 10, plan D4): Dorico exports slash
# regions as <measure-style><slash/> with no notes; Verovio renders those
# measures empty (MEI <space>). One slash per slash-unit, onsets on the
# beats, positioned on the staff so they render and animate like notes.
# ---------------------------------------------------------------------------

# Slash notehead as a parallelogram with horizontal end caps (approximates
# SMuFL noteheadSlashHorizontalEnds), in staff-space units, y-down, origin
# at the glyph's horizontal center on the middle staff line.
_SLASH_D = "M0.475 -1 L0.675 -1 L-0.475 1 L-0.675 1 Z"


def _synthesize_slashes(st: _LoadState,
                        staff_geo: dict[tuple, tuple[int, int | None, Rect]]
                        ) -> list[RenderedElement]:
    out: list[RenderedElement] = []
    glyph_bbox = path_bbox(_SLASH_D)
    for region in st.prep.slash_regions:
        info = next(p for p in st.prep.parts if p.part_id == region.part)
        for m in range(region.start_measure, region.stop_measure):
            start = st.measure_start[m]
            count = round(st.measure_duration[m] / region.slash_unit_quarters)
            if count <= 0:
                raise ValueError(f"slash region {region.part} m{m}: "
                                 f"non-positive slash count")
            # v1 limitation: slash regions on the part's first staff
            page, system, staff_bbox = staff_geo[(region.part, m, 1)]
            staff_space = staff_bbox.h / 4
            mid_y = staff_bbox.y + staff_bbox.h / 2
            slot_w = staff_bbox.w / count
            for k in range(count):
                cx = staff_bbox.x + (k + 0.5) * slot_w
                onset = start + k * region.slash_unit_quarters
                tf = Affine(a=staff_space, d=staff_space, e=cx, f=mid_y)
                bbox = tf.apply_rect(glyph_bbox)
                identity = ElementIdentity(
                    element_id=ElementId(f"{region.part}:m{m}:slash:{k}"),
                    kind=ElementKind.SLASH,
                    part=region.part, part_name=info.name,
                    staff=1, voice=None, onset=onset,
                )
                out.append(RenderedElement(
                    identity=identity, page=page, x=cx, y=mid_y,
                    bbox=bbox, anchor=bbox.center,
                    glyph=RenderPrimitive(paths=(
                        PathPrimitive(d=_SLASH_D, transform=tf),)),
                    system=system,
                ))
    return out


# Measure-repeat symbol (approximates SMuFL repeat1Bar): a bold oblique
# stroke with a dot in the upper-left and lower-right quadrants, in
# staff-space units, y-down, origin at the glyph's center on the middle
# staff line.
_REPEAT_D = ("M0.25 -1.1 L0.95 -1.1 L-0.25 1.1 L-0.95 1.1 Z "
             "M-0.62 -0.88 L-0.36 -0.62 L-0.62 -0.36 L-0.88 -0.62 Z "
             "M0.62 0.36 L0.88 0.62 L0.62 0.88 L0.36 0.62 Z")


def _synthesize_repeats(st: _LoadState,
                        staff_geo: dict[tuple, tuple[int, int | None, Rect]]
                        ) -> list[RenderedElement]:
    """One % symbol per repeated bar (ruling b — per measure), centered on
    the middle staff line, onset on the bar's downbeat. Verovio draws
    nothing for <measure-repeat> (empty <space>), so this is full
    synthesis in the slash shape (spikes/NOTES.md Phase 12)."""
    out: list[RenderedElement] = []
    glyph_bbox = path_bbox(_REPEAT_D)
    for region in st.prep.repeat_regions:
        info = next(p for p in st.prep.parts if p.part_id == region.part)
        for m in range(region.start_measure, region.stop_measure):
            # v1 limitation: repeat regions on the part's first staff
            page, system, staff_bbox = staff_geo[(region.part, m, 1)]
            staff_space = staff_bbox.h / 4
            cx = staff_bbox.x + staff_bbox.w / 2
            mid_y = staff_bbox.y + staff_bbox.h / 2
            tf = Affine(a=staff_space, d=staff_space, e=cx, f=mid_y)
            bbox = tf.apply_rect(glyph_bbox)
            identity = ElementIdentity(
                element_id=ElementId(f"{region.part}:m{m}:barrepeat"),
                kind=ElementKind.BAR_REPEAT,
                part=region.part, part_name=info.name,
                staff=1, voice=None, onset=st.measure_start[m],
            )
            out.append(RenderedElement(
                identity=identity, page=page, x=cx, y=mid_y,
                bbox=bbox, anchor=bbox.center,
                glyph=RenderPrimitive(paths=(
                    PathPrimitive(d=_REPEAT_D, transform=tf),)),
                system=system,
            ))
    return out


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
