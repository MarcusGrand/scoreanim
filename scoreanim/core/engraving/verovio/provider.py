"""Load orchestration: the Verovio toolkit, the retry loops, and the
pipeline.

VerovioEngravingProvider.load_detailed owns the hide-unavailable /
repagination / scale-to-fit retry loops (rule 7 amendments); its
_engrave_prepared is the ONE function that names the pipeline order.
Stage modules are imported AS MODULES and called module-qualified so the
pipeline reads as its stages and monkeypatching a stage stays possible.
Imports the base seam absolutely — .provider would shadow it.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import verovio

from scoreanim.core.engraving.provider import EngravingProvider
from scoreanim.core.engraving.systems import plan_page_breaks, system_bands
from scoreanim.core.engraving.types import (TRANSPOSE_TO_SOUNDING_PITCH,
                                            EngravingParams, Layout,
                                            LoadWarning, PageGeometry)
from scoreanim.core.engraving.verovio import (attribution, decompose,
                                              identity, kinds, mei_index,
                                              records, synthesis)
from scoreanim.core.score.identity import Beats
from scoreanim.core.score.musicxml_prep import (PartCondenseSpec,
                                                PartGroupSpec, PartTextSpec,
                                                PreparedScore, prepare)


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
                      strict: bool = True) -> records.EngravedScore:
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
                fit = max(1, int(kinds._DEFAULT_SCALE * page_h / bottom
                                 * kinds._FIT_MARGIN))
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
                          ) -> tuple[records.EngravedScore | None, dict[int, int]]:
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
            mei_text = mei_index._set_scoredef_optimize(tk.getMEI())
            tk = self._make_toolkit(prep, params, scale)
            if not tk.loadData(mei_text):
                raise ValueError(
                    f"Verovio failed to reload optimized MEI for "
                    f"{score_path}")

        mei = mei_index._parse_mei(tk.getMEI())
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

        state = records._LoadState(
            prep=prep, mei=mei, onset_by_id=onset_by_id,
            measure_start=measure_start, measure_duration=measure_duration,
            staff_n_by_id={vid: n.staff for vid, n in mei.notes.items()},
            layer_n_by_id={}, strict=strict,
        )
        # staff/layer container ids appear in both MEI and SVG; index them
        state.staff_n_by_id.update(mei_index._container_ns(tk.getMEI(), "staff"))
        state.layer_n_by_id.update(mei_index._container_ns(tk.getMEI(), "layer"))

        page_count = tk.getPageCount()
        pages = tuple(PageGeometry(number=p, width=prep.page_width,
                                   height=prep.page_height)
                      for p in range(1, page_count + 1))

        accumulators: list[tuple[int, decompose._ElementAccumulator]] = []
        for page in range(1, page_count + 1):
            decomposer = decompose._PageDecomposer(tk.renderToSVG(page),
                                                   page, state)
            for acc in decomposer.run():
                accumulators.append((page, acc))

        # staff y-centers per system, for geometric grpSym identity
        for _, acc in accumulators:
            if (acc.svg_class == "staff" and acc.bbox is not None
                    and acc.staff and acc.system is not None):
                state.staff_centers_by_system.setdefault(
                    acc.system, {}).setdefault(
                    acc.staff, acc.bbox.y + acc.bbox.h / 2)

        attribution._rehome_stray_paths(accumulators, state)
        attribution._attribute_ledger_dashes(accumulators, state)
        attribution._attribute_spanner_segments(accumulators, state)
        attribution._flag_implausible_ties(state)
        elements, note_records, staff_geo = identity._build_elements(
            accumulators, state)
        first_measure: dict[int, int] = {}
        for measure_n, system_n in state.system_of_measure.items():
            if measure_n < first_measure.get(system_n, 1 << 30):
                first_measure[system_n] = measure_n
        if hide_empty_staves and any(
                (region.part, m, 1) not in staff_geo
                for region in (*prep.slash_regions, *prep.repeat_regions)
                for m in range(region.start_measure, region.stop_measure)):
            return None, first_measure   # caller retries flat (rule 10)
        elements.extend(synthesis._synthesize_slashes(state, staff_geo))
        elements.extend(synthesis._synthesize_repeats(state, staff_geo))
        layout = Layout(pages=pages, elements=tuple(elements))
        return records.EngravedScore(layout=layout,
                             note_records=tuple(note_records),
                             prepared=prep,
                             warnings=tuple(state.warnings)), first_measure


