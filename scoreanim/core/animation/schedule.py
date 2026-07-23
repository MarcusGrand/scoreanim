"""Trigger schedule: when each animated element fires, in beats.

Built once per (score, join) from the Layout identities plus the
ScoreModel join mapping; pure data downstream. The three rules that make
it musically correct on real Dorico exports (spikes/NOTES.md):

1. Grow-with-playhead (ruling A/B revised 2026-07-22): every notehead —
   INCLUDING a tie 'stop'/'continue' — fires at its OWN notated onset.
   A held note is re-notated at each barline; those continuation noteheads
   fill in as the playhead reaches them, and the tie ink over them grows
   left-to-right against the reveal edge (reveal.py). Previously a tied
   continuation inherited its chain-start trigger ("a tied group is one
   event") — which drew the whole held span at once, so a 14-beat held
   note's tie painted to the system's end while the playhead was mid-
   system (the complex3 Oboe/Clarinet phantom). Scrubbing into a held
   note now lands it filled-in up to the playhead (the audio position),
   not fully lit. The default "appear" effect is an opacity fade, so a
   continuation REVEALS rather than re-attacks; onset-less broken :seg
   tie/slur segments carry no ScoreNote, never reach this table, and stay
   edge-driven.

2. Grace timing. Grace ScoreNotes carry the principal's onset, but the
   layout identity carries Verovio's fractional qstamp (just before the
   beat) — the musically right trigger, so graces use ``identity.onset``.

3. Attachment grouping. Stems/flags/accidentals/articulations/dots carry
   their owner's onset but no owner id, so they resolve through a group
   table keyed (part, staff, voice, quantized onset) built from the
   noteheads. A group with ANY fresh notehead triggers at the notated
   onset (a chord containing one tied-over note still articulates);
   only an all-tied group inherits the earliest chain-start trigger.
   Beams/ties/slurs resolve through the same table at their start onset;
   a lookup miss (e.g. synthesized slashes) falls back to
   ``identity.onset``.

4. Rests are retrospective ink (ruling 2026-07-12, second session): a
   rest appearing ON its beat reads as an event happening at silence.
   A rest's trigger is when its silence resolves — the next note in
   its (part, staff, voice) scope (staff fallback) or the end of its
   own bar, whichever comes first; never before its own onset. The
   whole-bar rest is the degenerate case (no next note in the bar →
   the barline); consecutive empty bars each complete at their own
   barline. Needs ``measures`` for the bar-end cap; without them
   (synthetic tests) only the next-note half applies.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping, Sequence

from scoreanim.core.engraving.types import Layout
from scoreanim.core.score.identity import (Beats, ElementId, ElementIdentity,
                                           ElementKind)
from scoreanim.core.score.model import MeasureInfo, ScoreNote

_Q = 4096                    # exact for binary subdivisions (join convention)
_MEASURE_RE = re.compile(r":m(\d+):")    # the minted-id measure segment


def quantize_beats(beats: Beats) -> int:
    """Shared beat quantizer: simultaneity is decided at 1/4096-beat
    resolution everywhere (schedule grouping, reveal anchors)."""
    return round(beats * _Q)


# Animation is a DENYLIST, not an allowlist (ruling 2026-07-20, revising
# the Phase 10R taxonomy). EVERY object on the page animates with the
# appear/effect system EXCEPT the true scaffold below; clefs, key
# signatures, tuplet brackets/numbers, ornaments — anything with an
# onset — are animated ink. An allowlist shipped every new kind
# static-until-remembered, which is exactly how coverage gaps kept
# appearing; the denylist inverts the default so new kinds animate for
# free. The scaffold is: staff lines, barlines, group symbols/brackets,
# and between-system dividers — plus page furniture (part labels,
# pgHead/pgFoot, measure numbers), which the adapter mints onset-less so
# the onset gate excludes it. Clip-revealed spanners (REVEALED_KINDS)
# are animated ink too, but via the reveal EDGE, not the opacity
# trigger, so is_animated excludes them here. Note ANIMATED ≠ TINTED
# (ruling D — TINTED_KINDS unchanged, clefs/keysigs stay black).
STATIC_KINDS = frozenset({
    ElementKind.STAFF_LINES, ElementKind.BARLINE,
    ElementKind.GROUP_SYMBOL, ElementKind.SYSTEM_DIVIDER,
})

# Spanner kinds revealed by clip-grow (opacity pinned 1.0). Defined here,
# the base animation module, so is_animated can exclude them from the
# opacity path; reveal.py re-exports it (its clip machinery is the
# authority on HOW they reveal).
REVEALED_KINDS = frozenset({ElementKind.SLUR, ElementKind.TIE,
                            ElementKind.HAIRPIN})

# Signature kinds (bar-level glyphs on the measure-start onset chain).
# A DISPLACED sig — one whose onset is not its own drawn measure's
# start, i.e. an end-of-system courtesy retimed to its CHANGE measure
# on the next system/page (FINDING-4 ruling 2026-07-23) — never drives
# a trigger's page/system hint: at the change downbeat its drawn page
# would drag the min() hint backward and delay the page turn. Like
# tie/rest-retimed ink, it lights where it is drawn but the VIEW
# follows the music. A sig lighting at its own drawn downbeat still
# drives hints as before — system-start restatements are the only
# fresh elements at rest-heavy system starts (bigband1 m9, complex2
# m48), and excluding them would hint the PREVIOUS system there. The
# adapter and the live-oracle import this set (the STATIC_KINDS
# precedent: schedule.py is the kind-policy authority).
SIG_KINDS = frozenset({ElementKind.CLEF, ElementKind.KEY_SIG,
                       ElementKind.METER_SIG})

# Opacity-animated kinds = everything that is neither scaffold nor a
# clip-revealed spanner. DERIVED from the denylist (introspection and
# back-compat); the denylist is the authority, so a new ElementKind
# joins this set automatically.
ANIMATED_KINDS = frozenset(
    k for k in ElementKind
    if k not in STATIC_KINDS and k not in REVEALED_KINDS)


def is_animated(identity: ElementIdentity) -> bool:
    """Opacity-animated = not scaffold, not a clip-revealed spanner, and
    carries an onset. Onset-less scaffold and page furniture (the adapter
    mints those onset-less) stay static through the onset gate."""
    return (identity.kind not in STATIC_KINDS
            and identity.kind not in REVEALED_KINDS
            and identity.onset is not None)


@dataclass(frozen=True)
class Trigger:
    beats: Beats
    page: int                            # page of this beat's FRESH onsets
    element_ids: tuple[ElementId, ...]
    system: int = 1                      # system, same fresh rule as page
                                         # (defaulted last: Phase 7.3 field,
                                         # synthetic construction survives)


@dataclass(frozen=True)
class TriggerSchedule:
    triggers: tuple[Trigger, ...]        # sorted by beats
    beat_values: tuple[float, ...]       # parallel array for bisect
    beats_by_element: Mapping[ElementId, Beats]


def build_trigger_schedule(layout: Layout,
                           mapping: Mapping[ElementId, ScoreNote],
                           measures: Sequence[MeasureInfo] = ()
                           ) -> TriggerSchedule:
    ident_by_id = {el.identity.element_id: el.identity
                   for el in layout.elements}

    # -- rule 1 + 2: each notehead triggers at its OWN notated onset --------
    # Grow-with-playhead (ruling A/B revised 2026-07-22): a tied
    # continuation fires at its own notated onset, NOT the chain start — so
    # a held note's re-notated barline noteheads FILL IN as the playhead
    # reaches each barline (with the tie ink growing between them), instead
    # of the whole held span appearing at once (the complex3 Oboe/Clarinet
    # phantom: a 14-beat held-note tie drawn to the system end while the
    # playhead was mid-system). Scrubbing into a held note lands it filled-in
    # up to the playhead, matching the audio position; the default "appear"
    # effect is a fade, so a continuation reveals rather than re-attacks.
    # Grace notes still use the layout's fractional qstamp (rule 2).
    note_trigger: dict[ElementId, Beats] = {}
    for eid, note in mapping.items():
        if eid not in ident_by_id:
            continue
        ident = ident_by_id[eid]
        note_trigger[eid] = (ident.onset if note.grace
                             and ident.onset is not None else note.onset)

    # -- rule 3: group table from the noteheads ----------------------------
    group_triggers: dict[tuple, list[tuple[Beats, Beats]]] = defaultdict(list)
    for eid, trigger in note_trigger.items():
        ident = ident_by_id[eid]
        own = ident.onset
        if own is None:                  # defensive; noteheads always carry one
            continue
        key = (ident.part, ident.staff, ident.voice, quantize_beats(own))
        group_triggers[key].append((trigger, own))

    group_trigger: dict[tuple, Beats] = {}
    for key, pairs in group_triggers.items():
        fresh = [own for trigger, own in pairs
                 if quantize_beats(trigger) == quantize_beats(own)]
        group_trigger[key] = fresh[0] if fresh \
            else min(trigger for trigger, _ in pairs)

    # -- rule 4: rests trigger when their silence resolves ------------------
    notes_by_voice: dict[tuple, list[tuple[Beats, Beats]]] = defaultdict(list)
    notes_by_staff: dict[tuple, list[tuple[Beats, Beats]]] = defaultdict(list)
    for eid, trigger in note_trigger.items():
        ident = ident_by_id[eid]
        if ident.onset is None:
            continue
        entry = (ident.onset, trigger)
        notes_by_voice[(ident.part, ident.staff, ident.voice)].append(entry)
        notes_by_staff[(ident.part, ident.staff)].append(entry)
    for scope_list in (*notes_by_voice.values(), *notes_by_staff.values()):
        scope_list.sort()
    bar_bounds = sorted({m.start for m in measures}
                        | {m.start + m.quarter_length for m in measures})

    def _rest_trigger(ident: ElementIdentity) -> Beats | None:
        candidates: list[Beats] = []
        for scope in (notes_by_voice.get((ident.part, ident.staff,
                                          ident.voice)),
                      notes_by_staff.get((ident.part, ident.staff))):
            if not scope:
                continue
            i = bisect_right(scope, (ident.onset, float("inf")))
            if i < len(scope):
                candidates.append(scope[i][1])   # next note's TRIGGER
                break
        i = bisect_right(bar_bounds, ident.onset)
        if i < len(bar_bounds):
            candidates.append(bar_bounds[i])     # own bar's end
        if not candidates:
            return None                          # fall back to own onset
        # a next note's trigger may be tie-gated into the past (another
        # voice's chain); the rest still never shows before its own beat
        return max(ident.onset, min(candidates))

    rest_trigger: dict[ElementId, Beats] = {}
    for el in layout.elements:
        ident = el.identity
        if (ident.kind in (ElementKind.REST, ElementKind.MREST)
                and ident.onset is not None):
            trigger = _rest_trigger(ident)
            if trigger is not None:
                rest_trigger[ident.element_id] = trigger

    # -- assemble all animated elements ------------------------------------
    measure_start_q = {n: quantize_beats(m.start)
                       for n, m in enumerate(measures, start=1)}

    def _displaced_sig(ident: ElementIdentity) -> bool:
        # A retimed courtesy sig: onset != its own drawn measure's start
        # (see the SIG_KINDS note above). With no measures supplied
        # (synthetic tests) nothing is displaced — the pre-FINDING-4
        # behavior.
        if ident.kind not in SIG_KINDS or ident.onset is None:
            return False
        m = _MEASURE_RE.search(str(ident.element_id))
        start_q = measure_start_q.get(int(m.group(1))) if m else None
        return start_q is not None and start_q != quantize_beats(ident.onset)

    by_qbeat: dict[int, dict] = {}
    beats_by_element: dict[ElementId, Beats] = {}
    for el in layout.elements:
        ident = el.identity
        if not is_animated(ident):
            continue
        eid = ident.element_id
        own = ident.onset
        assert own is not None           # guaranteed by is_animated
        if eid in note_trigger:
            trigger = note_trigger[eid]
        elif eid in rest_trigger:
            trigger = rest_trigger[eid]
        else:
            key = (ident.part, ident.staff, ident.voice, quantize_beats(own))
            trigger = group_trigger.get(key, own)
        beats_by_element[eid] = trigger
        bucket = by_qbeat.setdefault(quantize_beats(trigger), {
            "beats": trigger, "ids": [], "fresh_pages": set(), "pages": set(),
            "fresh_systems": set(), "systems": set()})
        bucket["ids"].append(eid)
        bucket["pages"].add(el.page)
        if el.system is not None:
            bucket["systems"].add(el.system)
        if (quantize_beats(trigger) == quantize_beats(own)
                and not _displaced_sig(ident)):
            bucket["fresh_pages"].add(el.page)
            if el.system is not None:
                bucket["fresh_systems"].add(el.system)

    triggers = tuple(
        Trigger(beats=b["beats"],
                page=min(b["fresh_pages"] or b["pages"]),
                system=min(b["fresh_systems"] or b["systems"] or {1}),
                element_ids=tuple(b["ids"]))
        for _, b in sorted(by_qbeat.items()))
    return TriggerSchedule(
        triggers=triggers,
        beat_values=tuple(t.beats for t in triggers),
        beats_by_element=beats_by_element,
    )
