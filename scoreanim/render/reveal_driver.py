"""Spanners reveal by clip-grow, not by triggers.

A slur, a hairpin, a tie — anything in REVEALED_KINDS — is not driven by
the trigger schedule at all. Each one belongs to a (system, part), and
that pair has a reveal curve saying how far across the system the ink
has been uncovered at time t (core/animation/reveal.py). This module
holds that whole concern: the index from key to items, the resolved
curves, and the edge cache that keeps an idle frame cheap.

A revealed item whose (system, part) key matches NO reveal track can
never receive an edge; since the FINDING-2 fix (2026-07-22) its clip
children default to hidden (fail-safe — only the floor ghost shows) and
construction warns loudly on stderr, one line per uncovered key
(``uncovered_reveal_keys`` carries them for tests and callers).
"""
from __future__ import annotations

import sys
from collections import defaultdict
from typing import Mapping, Sequence

from scoreanim.core.animation import (REVEALED_KINDS, RevealCurve, RevealMode,
                                      SystemRevealTrack, reveal_x)
from scoreanim.core.score.identity import ElementId
from scoreanim.core.timing import SwingRegion, TempoMap
from scoreanim.render.items import ElementItem


class RevealDriver:
    """The reveal half of the applier: which items each curve reaches,
    and where their clip edge sits at time t."""

    def __init__(self, items: Mapping[ElementId, ElementItem],
                 reveal_tracks: Sequence[SystemRevealTrack] = ()) -> None:
        # Per-part edges: one part's tied group holds only that part's
        # spanners (ruling A, 2026-07-12).
        self._tracks = tuple(reveal_tracks)
        track_keys = {(tr.system, tr.part) for tr in self._tracks}
        by_key: dict[tuple, list[ElementItem]] = defaultdict(list)
        uncovered: dict[tuple, list[ElementId]] = defaultdict(list)
        for eid, item in items.items():
            if (item.identity is None
                    or item.identity.kind not in REVEALED_KINDS):
                continue
            key = (item.system, item.identity.part)
            if item.system is not None and key in track_keys:
                by_key[key].append(item)
            else:
                # no track can ever reach this item: its clip children
                # stay at the hidden construction default (FINDING-2
                # fix — fail safe, never silently visible from t=0)
                uncovered[key].append(eid)
        self._by_key: dict[tuple, tuple[ElementItem, ...]] = {
            k: tuple(v) for k, v in by_key.items()}
        self.uncovered_keys: dict[tuple, tuple[ElementId, ...]] = {
            k: tuple(v) for k, v in uncovered.items()}
        for (system, part), eids in sorted(self.uncovered_keys.items(),
                                           key=repr):
            print(f"reveal warning [curve-less-key]: system {system} "
                  f"part {part} matches no reveal curve — "
                  f"{len(eids)} spanner(s) stay hidden: "
                  f"{', '.join(str(e) for e in eids)}", file=sys.stderr)
        self._curves: tuple[RevealCurve, ...] = ()
        self._last_edges: dict[tuple, float] = {}  # (system, part) → edge

    def resolve(self, tempo_map: TempoMap,
                swing: Sequence[SwingRegion] = ()) -> None:
        """Re-time every anchor onto the seconds axis: swing warp
        upstream of the tempo map, the same one seam the triggers use."""
        self._curves = tuple(track.resolve(tempo_map, swing)
                             for track in self._tracks)

    def invalidate(self) -> None:
        """Forget the cached edges, so the next apply writes every one of
        them. A full refresh does this: the scene may have moved under
        us."""
        self._last_edges.clear()

    def apply(self, t_score_seconds: float, mode: RevealMode) -> int:
        """Edges fan out only where a system's edge actually moved —
        STEPPED edges hold between onsets, so idle cost stays flat.
        Returns items touched."""
        changed = 0
        for curve in self._curves:
            key = (curve.system, curve.part)
            edge = reveal_x(curve, t_score_seconds, mode)
            if self._last_edges.get(key) == edge:
                continue
            self._last_edges[key] = edge
            for item in self._by_key.get(key, ()):
                if item.set_reveal_edge(edge):
                    changed += 1
        return changed
