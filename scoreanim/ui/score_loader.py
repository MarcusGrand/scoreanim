"""The load pipeline (M1.7): engrave → decompose → join → wire, plus
the engrave-input diff that decides when a document change needs a
re-engrave.

Owns no widgets and never reaches into the window: `load()` returns a
`LoadedScore` bundle the window installs whole. The `_applied_*`
caches record the engrave inputs of the LAST load, so
`needs_reengrave(doc)` is the single trigger for the staff-group /
part-label / hide-empty-staves / condense / system-break re-engrave. A
re-engrave is ~0.6 s on the GUI thread (engrave + scene rebuild; M5
measured 0.25 s on testscore and 1.28 s on bigband1), so the commands
that trip it must arrive via execute(), never preview().
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

from scoreanim.core.animation import (FLOOR_OPACITY, StyleRules,
                                      TriggerSchedule,
                                      build_reveal_tracks,
                                      build_trigger_schedule, glow_scope,
                                      inert_trigger_overrides,
                                      resolve_durations)
from scoreanim.core.engraving.systems import page_of_measure, system_bands
from scoreanim.core.engraving.types import (EngravingParams, Layout,
                                            LoadWarning)
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.project import (DEFAULT_BPM, ProjectDoc, StageConfig,
                                    default_stage_config, page_content_top)
from scoreanim.core.score.join import join_notes
from scoreanim.core.score.model import build_score_model
from scoreanim.core.score.musicxml_prep import (PageBreak, PartCondenseSpec,
                                                PartGroupSpec, PartTextSpec,
                                                SystemBreak)
from scoreanim.core.timing import TempoEvent, TempoMap
from scoreanim.render.animate import AnimationApplier
from scoreanim.render.export import AnimationInputs
from scoreanim.render.scene import ScoreScenes


@dataclass(frozen=True)
class LoadedScore:
    """Everything one load derives. All of it re-derives from
    (score file + engraving inputs) — nothing here is document state
    (rule 5); the window installs the bundle and owns nothing else."""
    scenes: ScoreScenes
    stage: StageConfig           # the config used (seeded when none given)
    animation_inputs: AnimationInputs   # retained for export
    applier: AnimationApplier
    measures: tuple
    parts: tuple
    band_by_system: dict         # per-system band rects (Phase 7.4)
    system_of_measure: dict      # measure ordinal → system index (M5)
    page_of_measure: dict        # measure ordinal → page (M6, derived §1.2)
    warnings: tuple              # LoadWarnings (flag-and-continue)
    overflow: bool               # a system overflowed its page
    status_line: str             # the timing/join status message


@dataclass(frozen=True)
class _RebuildInputs:
    """The last load's non-engraving derivations, retained so a
    trigger-override change can rebuild the schedule live — no Verovio,
    no scene rebuild. The join mapping is the one input `load()` used
    to throw away."""
    layout: Layout
    mapping: dict
    measures: tuple
    durations: dict


class ScoreLoader:
    """Engrave→decompose→join→wire, with the applied-input diff."""

    def __init__(self) -> None:
        self._applied_groups: tuple = ()   # staff groups the engrave used
        self._applied_params = None        # EngravingParams ditto
        self._applied_text_overrides: dict = {}   # label overrides ditto
        self._applied_hide_empty = False   # hide-empty-staves ditto
        self._applied_hide_first = False   # hide-first-system ditto
        self._applied_condense: tuple = ()   # condense groups ditto
        self._applied_breaks: dict = {}    # system-break overrides ditto
        self._applied_page_breaks: dict = {}   # page-break overrides ditto
        self._applied_stem_directions: dict = {}   # hand-flipped stems ditto
        self._applied_trigger_overrides: dict = {}   # hand-moved onsets ditto
        self._retained: _RebuildInputs | None = None   # for rebuild_schedule

    @property
    def applied_breaks(self) -> dict:
        """The system-break overrides the LAST load used — the window
        diffs against it to find which measure a break edit touched, so
        the view can re-anchor there (M5.5, D8)."""
        return dict(self._applied_breaks)

    @property
    def applied_page_breaks(self) -> dict:
        """The page-break overrides the LAST load used — the same diff,
        the other map (M6.5, D11). Both are read by `_break_anchor`,
        which anchors on the lowest ordinal either of them changed."""
        return dict(self._applied_page_breaks)

    def needs_reengrave(self, doc: ProjectDoc) -> bool:
        """Staff groups, the engraving params (the score scale lives
        there), part-label overrides, hide-empty-staves (and its
        first-system extension), condense groups, and system-break
        overrides -- and a hand-flipped stem, which Verovio draws --
        are engraving inputs: a change (execute, undo, OR redo)
        re-derives the engraved world. The diff keeps every other command
        at its current cost."""
        return (doc.staff_groups != self._applied_groups
                or doc.engraving != self._applied_params
                or dict(doc.text_overrides) != self._applied_text_overrides
                or doc.hide_empty_staves != self._applied_hide_empty
                or doc.hide_first_system != self._applied_hide_first
                or doc.condense_groups != self._applied_condense
                or dict(doc.system_break_overrides) != self._applied_breaks
                or dict(doc.page_break_overrides)
                != self._applied_page_breaks
                or dict(doc.stem_directions) != self._applied_stem_directions)

    def needs_reschedule(self, doc: ProjectDoc) -> bool:
        """A trigger-override change re-derives the SCHEDULE only.
        Deliberately not in `needs_reengrave`: the overrides are not
        engraving inputs, so no Verovio and no scene rebuild."""
        return dict(doc.trigger_overrides) != self._applied_trigger_overrides

    def rebuild_schedule(self, doc: ProjectDoc) -> TriggerSchedule | None:
        """The schedule alone, rebuilt from the LAST load's retained
        derivations plus the document's overrides. None before any
        load. Ids that turned stale since the load stay inert here —
        they were warned about then (rule 5's staleness trade)."""
        if self._retained is None:
            return None
        kept = self._retained
        overrides = dict(doc.trigger_overrides)
        schedule = build_trigger_schedule(
            kept.layout, kept.mapping, kept.measures, kept.durations,
            trigger_overrides=overrides)
        self._applied_trigger_overrides = overrides
        return schedule

    def load(self, path: Path, params: EngravingParams,
             stage: StageConfig | None,
             style: StyleRules,
             groups: tuple = (),
             text_overrides: dict | None = None,
             hide_empty_staves: bool = False,
             condense_groups: tuple = (),
             hide_first_system: bool = False,
             system_breaks: dict[int, SystemBreak] | None = None,
             page_breaks: dict[int, PageBreak] | None = None,
             stem_directions: dict | None = None,
             trigger_overrides: dict | None = None
             ) -> LoadedScore:
        """Engrave + decompose + join + wire the animation. `groups` is
        doc.staff_groups — injected as <part-group> at the prep seam;
        `text_overrides` is doc.text_overrides — part labels rewritten
        there (Phase 9.3); `condense_groups` is doc.condense_groups —
        contiguous like parts merged onto one staff there (Phase 12.3);
        `system_breaks` is doc.system_break_overrides — the sparse
        force/suppress delta rewriting <print new-system> there (M5), and
        `page_breaks` its <print new-page> twin (M6), the two written by
        one combined pass; `stem_directions` is doc.stem_directions --
        the stems the user flipped by hand, written as <stem> there
        (2026-08-03), on top of the unconditional pass that drops the
        encoded direction on every single-voice staff;
        `trigger_overrides` is doc.trigger_overrides — hand-moved fire
        times consumed by the schedule, NOT an engraving input
        (2026-08-08);
        geometry re-derives, musical ids survive (rule 5, Phases
        8/9/12). `style` is the CURRENT document style — the applier is
        built with it and set_style'd after any later change."""
        text_overrides = dict(text_overrides or {})
        specs = tuple(PartGroupSpec(parts=g.parts, symbol=g.symbol,
                                    join_barlines=g.join_barlines)
                      for g in groups)
        text_specs = tuple(PartTextSpec(part=pid, name=o.name,
                                        abbreviation=o.abbreviation)
                           for pid, o in sorted(text_overrides.items()))
        condense_specs = tuple(
            PartCondenseSpec(parts=g.parts, name=g.name,
                             abbreviation=g.abbreviation)
            for g in condense_groups)
        system_breaks = dict(system_breaks or {})
        page_breaks = dict(page_breaks or {})
        stem_directions = dict(stem_directions or {})
        trigger_overrides = dict(trigger_overrides or {})
        t0 = time.perf_counter()
        # strict=False (app path, Phase 11.4): an unknown drawable SVG
        # class degrades to a warned static element instead of failing the
        # open. The status bar shows the warning count.
        engraved = VerovioEngravingProvider().load_detailed(
            path, params, specs, text_specs, hide_empty_staves,
            condense_specs, strict=False,
            hide_first_system=hide_first_system,
            system_breaks=system_breaks, page_breaks=page_breaks,
            stem_directions=stem_directions)
        t1 = time.perf_counter()
        if stage is None:
            stage = default_stage_config(engraved.prepared,
                                         page_content_top(engraved.layout))
        # Constructed at the default floor; the window's document-changed
        # pass runs right after install, and the style sync corrects the
        # ghosts to a project-saved floor (same pattern as the applier,
        # built with the current style then set_style'd).
        scenes = ScoreScenes(engraved.layout, stage,
                             ghost_opacity=FLOOR_OPACITY)
        t2 = time.perf_counter()

        model = build_score_model(engraved.prepared, engraved.timeline)
        report = join_notes(model, engraved.note_records)
        join_note = ""
        if not report.is_complete:
            join_note = (f" · JOIN INCOMPLETE ({len(report.unmatched_score)}"
                         f"/{len(report.unmatched_layout)} unmatched)")
        # a stored trigger override whose element is gone, or whose kind
        # cannot be re-timed, is inert: warned here, never repaired
        # (rule 5's staleness trade)
        stale = inert_trigger_overrides(engraved.layout, trigger_overrides)
        warnings = engraved.warnings
        if stale:
            ids = [str(eid) for eid, _ in stale]
            warnings += (LoadWarning(
                "trigger-override-inert",
                f"{len(stale)} moved onset(s) had no element to land on "
                f"({', '.join(ids[:5])}{', …' if len(ids) > 5 else ''})"),)
        if warnings:
            # flag-and-continue (Phase 10 ruling b): e.g. ties the
            # engraver dropped — the score loads, the anomaly is visible
            join_note += f" · {len(warnings)} load warning(s)"
            for w in warnings:
                print(f"load warning [{w.code}]: {w.message}",
                      file=sys.stderr)
        # per-element engraved durations (M4): resolved once here, carried
        # by the schedule so live AND export read the same seam
        durations = resolve_durations(engraved.layout, report.mapping,
                                      engraved.note_durations,
                                      model.measures)
        schedule = build_trigger_schedule(engraved.layout, report.mapping,
                                          model.measures, durations,
                                          trigger_overrides=trigger_overrides)
        score_end = max((m.start + m.quarter_length for m in model.measures),
                        default=0.0)
        reveal_tracks = build_reveal_tracks(engraved.layout, schedule,
                                            score_end)
        # retained for export: the private export scenes+applier build
        # from the SAME inputs as the live ones (render/export.py)
        # who glows, whose halo they share, and how long a tied chain
        # burns: derived here so live and export read one seam
        glow = glow_scope(engraved.layout, report.mapping, durations)
        animation_inputs = AnimationInputs(
            engraved.layout, stage, schedule, tuple(reveal_tracks), glow)
        applier = AnimationApplier(scenes.items, schedule,
                                   TempoMap([TempoEvent(0.0, DEFAULT_BPM)]),
                                   style, reveal_tracks,
                                   scenes.system_groups.values(), glow)
        # per-system band rects for system-at-a-time framing (Phase 7.4)
        # — derived from the Layout, never persisted (rule 5)
        bands = system_bands(engraved.layout)
        band_by_system = {b.system: b for b in bands}
        t3 = time.perf_counter()

        self._applied_groups = groups
        self._applied_params = params
        self._applied_text_overrides = text_overrides
        self._applied_hide_empty = hide_empty_staves
        self._applied_hide_first = hide_first_system
        self._applied_condense = condense_groups
        self._applied_breaks = system_breaks
        self._applied_page_breaks = page_breaks
        self._applied_stem_directions = stem_directions
        self._applied_trigger_overrides = trigger_overrides
        self._retained = _RebuildInputs(layout=engraved.layout,
                                        mapping=dict(report.mapping),
                                        measures=tuple(model.measures),
                                        durations=dict(durations))

        return LoadedScore(
            scenes=scenes, stage=stage,
            animation_inputs=animation_inputs, applier=applier,
            measures=model.measures, parts=engraved.prepared.parts,
            band_by_system=band_by_system,
            system_of_measure=dict(engraved.system_of_measure),
            page_of_measure=page_of_measure(bands,
                                            engraved.system_of_measure),
            warnings=warnings,
            # a system taller than its page means the score needs
            # staff-count reduction. Since Phase 12.5 such a load is
            # rescued by scale-to-fit and "system-overflow" is
            # defensive-only, so both codes count. Reported, not acted
            # on: nothing opens Score Setup by itself (2026-07-30).
            overflow=any(w.code in ("scaled-to-fit", "system-overflow")
                         for w in warnings),
            status_line=(
                f"engrave+decompose {t1 - t0:.2f}s · "
                f"scene build {t2 - t1:.2f}s · "
                f"animation prep {t3 - t2:.2f}s · "
                f"{len(scenes.items)} elements on "
                f"{scenes.page_count} pages{join_note}"))
