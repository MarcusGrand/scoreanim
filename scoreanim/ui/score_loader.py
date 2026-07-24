"""The load pipeline (M1.7): engrave → decompose → join → wire, plus
the engrave-input diff that decides when a document change needs a
re-engrave.

Owns no widgets and never reaches into the window: `load()` returns a
`LoadedScore` bundle the window installs whole. The `_applied_*`
caches record the engrave inputs of the LAST load, so
`needs_reengrave(doc)` is the single trigger for the staff-group /
part-label / hide-empty-staves / condense re-engrave. A re-engrave is
~0.6 s on the GUI thread (engrave + scene rebuild), so the commands
that trip it must arrive via execute(), never preview().
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

from scoreanim.core.animation import (FLOOR_OPACITY, StyleRules,
                                      build_reveal_tracks,
                                      build_trigger_schedule)
from scoreanim.core.engraving.systems import system_bands
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.project import (DEFAULT_BPM, ProjectDoc, StageConfig,
                                    default_stage_config, page_content_top)
from scoreanim.core.score.join import join_notes
from scoreanim.core.score.model import build_score_model
from scoreanim.core.score.musicxml_prep import (PartCondenseSpec,
                                                PartGroupSpec, PartTextSpec)
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
    warnings: tuple              # LoadWarnings (flag-and-continue)
    overflow: bool               # a system overflowed → offer Score Setup
    status_line: str             # the timing/join status message


class ScoreLoader:
    """Engrave→decompose→join→wire, with the applied-input diff."""

    def __init__(self) -> None:
        self._applied_groups: tuple = ()   # staff groups the engrave used
        self._applied_text_overrides: dict = {}   # label overrides ditto
        self._applied_hide_empty = False   # hide-empty-staves ditto
        self._applied_hide_first = False   # hide-first-system ditto
        self._applied_condense: tuple = ()   # condense groups ditto

    def needs_reengrave(self, doc: ProjectDoc) -> bool:
        """Staff groups, part-label overrides, hide-empty-staves (and
        its first-system extension), and condense groups are engraving
        inputs: a change (execute, undo, OR redo) re-derives the
        engraved world. The diff keeps every other command at its
        current cost."""
        return (doc.staff_groups != self._applied_groups
                or dict(doc.text_overrides) != self._applied_text_overrides
                or doc.hide_empty_staves != self._applied_hide_empty
                or doc.hide_first_system != self._applied_hide_first
                or doc.condense_groups != self._applied_condense)

    def load(self, path: Path, params: EngravingParams,
             stage: StageConfig | None,
             style: StyleRules,
             groups: tuple = (),
             text_overrides: dict | None = None,
             hide_empty_staves: bool = False,
             condense_groups: tuple = (),
             hide_first_system: bool = False) -> LoadedScore:
        """Engrave + decompose + join + wire the animation. `groups` is
        doc.staff_groups — injected as <part-group> at the prep seam;
        `text_overrides` is doc.text_overrides — part labels rewritten
        there (Phase 9.3); `condense_groups` is doc.condense_groups —
        contiguous like parts merged onto one staff there (Phase 12.3);
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
        t0 = time.perf_counter()
        # strict=False (app path, Phase 11.4): an unknown drawable SVG
        # class degrades to a warned static element instead of failing the
        # open. The status bar shows the warning count.
        engraved = VerovioEngravingProvider().load_detailed(
            path, params, specs, text_specs, hide_empty_staves,
            condense_specs, strict=False,
            hide_first_system=hide_first_system)
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
        if engraved.warnings:
            # flag-and-continue (Phase 10 ruling b): e.g. ties the
            # engraver dropped — the score loads, the anomaly is visible
            join_note += f" · {len(engraved.warnings)} load warning(s)"
            for w in engraved.warnings:
                print(f"load warning [{w.code}]: {w.message}",
                      file=sys.stderr)
        schedule = build_trigger_schedule(engraved.layout, report.mapping,
                                          model.measures)
        score_end = max((m.start + m.quarter_length for m in model.measures),
                        default=0.0)
        reveal_tracks = build_reveal_tracks(engraved.layout, schedule,
                                            score_end)
        # retained for export: the private export scenes+applier build
        # from the SAME inputs as the live ones (render/export.py)
        animation_inputs = AnimationInputs(
            engraved.layout, stage, schedule, tuple(reveal_tracks))
        applier = AnimationApplier(scenes.items, schedule,
                                   TempoMap([TempoEvent(0.0, DEFAULT_BPM)]),
                                   style, reveal_tracks)
        # per-system band rects for system-at-a-time framing (Phase 7.4)
        # — derived from the Layout, never persisted (rule 5)
        band_by_system = {b.system: b
                          for b in system_bands(engraved.layout)}
        t3 = time.perf_counter()

        self._applied_groups = groups
        self._applied_text_overrides = text_overrides
        self._applied_hide_empty = hide_empty_staves
        self._applied_hide_first = hide_first_system
        self._applied_condense = condense_groups

        return LoadedScore(
            scenes=scenes, stage=stage,
            animation_inputs=animation_inputs, applier=applier,
            measures=model.measures, parts=engraved.prepared.parts,
            band_by_system=band_by_system, warnings=engraved.warnings,
            # a system still overflowing its page after repagination means
            # the score needs staff-count reduction — the Score Setup
            # trigger (Phase 12.4)
            overflow=any(w.code == "system-overflow"
                         for w in engraved.warnings),
            status_line=(
                f"engrave+decompose {t1 - t0:.2f}s · "
                f"scene build {t2 - t1:.2f}s · "
                f"animation prep {t3 - t2:.2f}s · "
                f"{len(scenes.items)} elements on "
                f"{scenes.page_count} pages{join_note}"))
