"""Attribution post-passes: in-place mutation of the decomposed
accumulators, ORDER-SENSITIVE (the pipeline in provider._engrave_prepared
names the order and why it is load-bearing).

_reclaim_spanner_ink moves slur/tie curves out of foreign same-id groups
back onto their own elements (FINDING-5); _rehome_stray_paths splits
foreign-system ink out of colliding groups; _attribute_ledger_dashes
gives id-less dashes their owner's onset/voice;
_attribute_spanner_segments pairs continuation ink with source spanners;
_flag_implausible_ties suppresses engraving-artifact ties. Also the
tstamp arithmetic helpers the spanner passes and identity minting share.

Inputs: the accumulator list + _LoadState. Outputs: none — the passes
mutate accumulators in place (paths/bbox/owner_onset/layer on dashes,
source_vid/seg_index on continuation segments; reclaiming and rehoming
APPEND new accumulators, reclaiming also DROPS ink-less spanner
placeholders). _LoadState READS: mei, onset_by_id, measure_start,
measure_duration, prep, system_of_measure, staff_centers_by_system.
WRITES: warnings ("reclaimed-spanner-ink", "stray-path",
"segment-count-mismatch", "dropped-spanner", "implausible-tie"),
suppressed_spanners.
"""

from __future__ import annotations

from collections import defaultdict

from scoreanim.core.engraving.svg_geom import path_bbox
from scoreanim.core.engraving.types import (LoadWarning, PathPrimitive,
                                            Rect)
from scoreanim.core.engraving.verovio.decompose import (_ElementAccumulator,
                                                        _text_prim_bbox)
from scoreanim.core.engraving.verovio.kinds import _SPANNER_CLASSES
from scoreanim.core.engraving.verovio.records import _LoadState
from scoreanim.core.score.identity import Beats, ElementKind

# ---------------------------------------------------------------------------
# System partition (shared by reclaiming and rehoming): which system's
# vertical band a y coordinate falls in, per page.
# ---------------------------------------------------------------------------

def _system_partition(
        accumulators: list[tuple[int, _ElementAccumulator]],
) -> dict[int, list[tuple[int, float, float]]]:
    """Per-page vertical partition into systems from the staff-line
    bands. Page-local coords: the same system index sits at similar y on
    different pages, so partition per page."""
    bands: dict[int, dict[int, tuple[float, float]]] = {}
    for page, acc in accumulators:
        if (acc.svg_class == "staff" and acc.system is not None
                and acc.bbox is not None):
            per = bands.setdefault(page, {})
            lo, hi = per.get(acc.system, (acc.bbox.y, acc.bbox.y2))
            per[acc.system] = (min(lo, acc.bbox.y), max(hi, acc.bbox.y2))
    return {page: sorted(((s, lo, hi) for s, (lo, hi) in per.items()),
                         key=lambda t: t[1])
            for page, per in bands.items()}


def _system_at(ordered: dict[int, list[tuple[int, float, float]]],
               page: int, y: float) -> int | None:
    """The system whose vertical partition (staff band, split at the
    midpoint of each inter-system gap) contains y."""
    rows = ordered.get(page)
    if not rows:
        return None
    for i, (sysn, _lo, hi) in enumerate(rows):
        upper = (float("inf") if i == len(rows) - 1
                 else (hi + rows[i + 1][1]) / 2.0)
        if y < upper:
            return sysn
    return rows[-1][0]


# ---------------------------------------------------------------------------
# Spanner-ink reclaim (FINDING-5, 2026-07-23): under the hide-empty-
# staves MEI optimize round-trip Verovio reuses one xml:id across
# element types AND draws a slur/tie's curve inside the foreign group
# carrying its id — the spanner's own <g>, nested in the right measure,
# renders EMPTY. Decompose's subtree claim hands the curve to that
# stem/flag/dots/barline/text element, so the curve would fire at the
# HOST's onset (the recurring early-slur), and the reused id masks the
# dropped-spanner warning. Every flat load is clean — the artifact is
# exclusive to the optimize round-trip.
#
# The reclaim: a literal <path> bézier inside a non-spanner group
# (indexed by decompose as ``literal_curves``; host-own ink is rects/
# lines/ellipse-paths/<use> glyphs) that shares a slur/tie's id is moved
# back. Ink lying in the spanner's own system folds into its (kept-
# empty) accumulator, which then mints normally — measure from its own
# <g>, staff/voice/onset from the MEI start note. Ink lying in ANOTHER
# system becomes a pre-attributed continuation segment there (the ink of
# a broken spanner belongs to that system's :seg element — the
# (system, part) reveal-edge invariant; folding it into the start-system
# element would just make rehome split it back out as anonymous ink).
# Placeholders that end ink-less are dropped again unless a reclaimed
# segment needs their identity, so flat loads are untouched. One warning
# per reclaimed spanner (ruling b).
# ---------------------------------------------------------------------------

_RECLAIM_TAGS = ("slur", "tie", "lv")    # curve-shaped drawn spanners;
                                         # hairpin ink is straight lines,
                                         # indistinguishable from host ink


def _reclaim_spanner_ink(
        accumulators: list[tuple[int, _ElementAccumulator]],
        st: _LoadState) -> None:
    ordered = _system_partition(accumulators)
    by_vid: dict[str, list[tuple[int, _ElementAccumulator]]] = \
        defaultdict(list)
    for page, acc in accumulators:
        if acc.verovio_id and not acc.continuation:
            by_vid[acc.verovio_id].append((page, acc))

    needed_sources: set[str] = set()
    new_segs: list[tuple[int, _ElementAccumulator]] = []
    for vid, tag in sorted(st.mei.spanner_tags.items()):
        if tag not in _RECLAIM_TAGS:
            continue
        entries = by_vid.get(vid, [])
        targets = [(p, a) for p, a in entries
                   if a.svg_class in _SPANNER_CLASSES]
        hosts = [(p, a) for p, a in entries
                 if a.svg_class not in _SPANNER_CLASSES]
        if targets and targets[0][1].paths:
            continue                     # spanner has its own ink
        if not targets:
            # Not even an empty <g> for the spanner (bigband: vz2tmdv).
            # If a same-id host holds a stolen curve, synthesize the
            # placeholder from the MEI start note so the ink still has
            # a home; without stolen ink there is nothing to do (the
            # drawn-check warns dropped-spanner).
            if not any(host.literal_curves for _, host in hosts):
                continue
            note = st.mei.notes.get(st.mei.spanners.get(vid,
                                                        (None, None))[0]
                                    or "")
            measure = note.measure if note is not None \
                else hosts[0][1].measure
            target = _ElementAccumulator(
                verovio_id=vid, svg_class=tag,
                kind=ElementKind.SLUR if tag == "slur" else ElementKind.TIE,
                measure=measure, staff=None, layer=None, owner_onset=None,
                system=st.system_of_measure.get(measure)
                if measure is not None else None)
            accumulators.append((hosts[0][0], target))
        else:
            target = targets[0][1]

        moved: list[tuple[int, PathPrimitive, Rect]] = []
        host_names: list[str] = []
        for host_page, host in hosts:
            if not host.literal_curves:
                continue
            stolen_idx = set(host.literal_curves)
            stolen = [host.paths[i] for i in sorted(stolen_idx)]
            host.paths[:] = [p for i, p in enumerate(host.paths)
                             if i not in stolen_idx]
            host.literal_curves.clear()
            host.bbox = None
            for prim in host.paths:
                host.add_bbox(prim.transform.apply_rect(path_bbox(prim.d)))
            for text in host.texts:
                host.add_bbox(_text_prim_bbox(text))
            for prim in stolen:
                moved.append((host_page, prim,
                              prim.transform.apply_rect(path_bbox(prim.d))))
            host_names.append(f"{host.svg_class or host.kind.name.lower()} "
                              f"m{host.measure}")
        if not moved:
            continue

        segs_made = 0
        for host_page, prim, box in moved:
            curve_sys = _system_at(ordered, host_page, box.center.y)
            if curve_sys is None or curve_sys == target.system:
                target.literal_curves.append(len(target.paths))
                target.paths.append(prim)
                target.add_bbox(box)
            else:
                seg = _ElementAccumulator(
                    verovio_id="", svg_class=target.svg_class,
                    kind=target.kind, measure=None, staff=None, layer=None,
                    owner_onset=None, system=curve_sys, continuation=True,
                    source_vid=vid)
                seg.literal_curves.append(0)
                seg.paths.append(prim)
                seg.bbox = box
                new_segs.append((host_page, seg))
                needed_sources.add(vid)
                segs_made += 1

        start_id, _ = st.mei.spanners.get(vid, (None, None))
        note = st.mei.notes.get(start_id or "")
        if note is not None:
            info = st.prep.part_for_staff(note.staff)
            where = (f"from {info.part_id} m{note.measure} "
                     f"s{note.staff - info.first_staff + 1}")
        else:
            where = "with unresolved start"
        st.warnings.append(LoadWarning(
            "reclaimed-spanner-ink",
            f"{tag} {where}: {len(moved)} curve path(s) drawn inside "
            f"foreign group(s) sharing its reused id "
            f"({', '.join(host_names)}) — reclaimed onto the {tag}'s own "
            f"element"
            + (f" ({segs_made} as continuation segment(s))" if segs_made
               else "")
            + " (Verovio id-reuse artifact under hide-empty-staves)"))

    accumulators.extend(new_segs)
    # Drop the placeholders nothing was reclaimed into — decompose keeps
    # empty spanner groups only for this pass. A placeholder whose ink
    # lives entirely in reclaimed segments survives ink-less: identity
    # minting still registers it so its segments inherit the right ids
    # (no element is built for it — Verovio drew no start-system ink).
    accumulators[:] = [
        (p, a) for p, a in accumulators
        if a.continuation or a.svg_class not in _SPANNER_CLASSES
        or a.paths or a.texts or a.verovio_id in needed_sources]


# ---------------------------------------------------------------------------
# Ledger-dash attribution (BACKLOG 6): a dash carries no id and no onset;
# it dims with the ink it serves. Owner = the notehead in the same
# (page, measure, staff) whose bbox overlaps the dash horizontally, on the
# correct side of the staff; a dash serving several heads (chords,
# multi-ledger stacks) takes the earliest onset so it never lights late.
# Verovio also draws ledger dashes through RESTS displaced off the staff
# (two-voice measures — Phase 10 triage, spikes/video_test_triage.py);
# a dash no notehead claims falls through to a rest tier with the same
# geometry rule. Tie resolution then happens for free: the dash inherits
# the owner's (onset, voice), which is exactly the schedule's
# attachment-group key — REST and LEDGER_LINES both animate.
# ---------------------------------------------------------------------------

def _attribute_ledger_dashes(
        accumulators: list[tuple[int, _ElementAccumulator]],
        st: _LoadState) -> None:
    notes_by_scope: dict[tuple, list[tuple[Rect, Beats, int]]] = \
        defaultdict(list)
    rests_by_scope: dict[tuple, list[tuple[Rect, Beats, int]]] = \
        defaultdict(list)
    for page, acc in accumulators:
        if acc.bbox is None:
            continue
        if acc.svg_class == "note":
            onset = st.onset_by_id.get(acc.verovio_id)
            mei_note = st.mei.notes.get(acc.verovio_id)
            if onset is None or mei_note is None:
                continue                 # _build_elements raises for these
            notes_by_scope[(page, acc.measure, acc.staff)].append(
                (acc.bbox, onset, mei_note.layer))
        elif acc.svg_class in ("rest", "mRest"):
            # whole-bar rests join the rest tier (Phase 11): a two-voice
            # measure displaces an mRest off the staff onto a ledger dash
            # exactly like an ordinary rest (complex1 p3 m13 staff 8)
            onset = st.onset_by_id.get(acc.verovio_id)
            if onset is None:
                continue                 # not in the timemap: no trigger
            rests_by_scope[(page, acc.measure, acc.staff)].append(
                (acc.bbox, onset, acc.layer if acc.layer is not None else 0))

    def matching(pool: list[tuple[Rect, Beats, int]],
                 dash: _ElementAccumulator) -> list[tuple[Beats, int]]:
        dash_cy = dash.bbox.y + dash.bbox.h / 2      # type: ignore[union-attr]
        out: list[tuple[Beats, int]] = []
        for bbox, onset, layer in pool:
            if (bbox.x + bbox.w <= dash.bbox.x
                    or dash.bbox.x + dash.bbox.w <= bbox.x):
                continue                 # no horizontal overlap
            owner_cy = bbox.y + bbox.h / 2
            # a dash above the staff is owned by ink at or above it
            # (y-down coordinates); intermediate dashes under a high note
            # pass this too. Mirror rule below the staff.
            if dash.ledger_dir == "above" and owner_cy > dash_cy + bbox.h / 2:
                continue
            if dash.ledger_dir == "below" and owner_cy < dash_cy - bbox.h / 2:
                continue
            out.append((onset, layer))
        return out

    for page, acc in accumulators:
        if acc.kind is not ElementKind.LEDGER_LINES or acc.bbox is None:
            continue
        scope = (page, acc.measure, acc.staff)
        candidates = (matching(notes_by_scope.get(scope, []), acc)
                      or matching(rests_by_scope.get(scope, []), acc))
        if not candidates:
            raise ValueError(
                f"page {page} m{acc.measure} staff {acc.staff}: ledger dash "
                f"at x={acc.bbox.x:.0f} matches no notehead or rest — "
                f"attribution failed")
        acc.owner_onset, acc.layer = min(candidates)


# ---------------------------------------------------------------------------
# Spanner continuation segments (Phase 5, spikes/spanner_split.py): a
# system-broken spanner renders as its id-bearing <g> (start system) plus
# id-less continuation <g>s. Each id-less segment is matched to the
# source spanner it continues — same SVG class, crossing-system
# predicate per class: slurs/hairpins draw a segment in EVERY crossed
# system (start < n <= end); ties draw continuation ink ONLY in their
# END system (Phase 10 triage — the Phase 5 fixture had only 2-system
# spanners, where the two rules coincide). Stacked same-kind candidates
# (several broken ties at once) are disambiguated by vertical order —
# segments and candidate end anchors are paired in y order, which is
# stable because a tie continuation hugs the pitch height of its end
# note. A count mismatch is tolerated: pairs are matched up to the
# shorter list and the mismatch surfaces as a LoadWarning (ruling b),
# never a silent absorption. Spanners the engraver dropped entirely
# (id-bearing <g> with no ink — e.g. Verovio's "ties left open") are
# detected structurally against the MEI and flagged the same way.
# ---------------------------------------------------------------------------

def _attribute_spanner_segments(
        accumulators: list[tuple[int, _ElementAccumulator]],
        st: _LoadState) -> None:
    note_accs: dict[str, _ElementAccumulator] = {
        acc.verovio_id: acc for _, acc in accumulators
        if acc.svg_class == "note"}

    # (svg_class, start_sys, end_sys, sort_key, vid)
    sources: list[tuple[str, int, int, tuple, str]] = []
    for _, acc in accumulators:
        if acc.continuation or acc.svg_class not in _SPANNER_CLASSES:
            continue
        vid = acc.verovio_id
        start_id, end_id = st.mei.spanners.get(vid, (None, None))
        end_sys: int | None = None
        end_y: float | None = None
        # The staff a spanner is DRAWN on is its start note's staff — that's
        # the staff its continuation segments appear on. Prefer it; the end
        # note's staff (below) is only a fallback, and is 0 whenever the end
        # note's accumulator isn't found — which would mis-group the source
        # and defeat staff-based segment pairing.
        start_mei = st.mei.notes.get(start_id or "")
        staff_n = (start_mei.staff or 0) if start_mei is not None else 0
        end_note = note_accs.get(end_id or "")
        if end_note is not None:
            end_sys = end_note.system
            end_y = end_note.bbox.center.y if end_note.bbox else None
            staff_n = staff_n or (end_note.staff or 0)
        elif vid in st.mei.tstamps_by_id:
            m, _, tstamp2 = st.mei.tstamps_by_id[vid]
            end_sys = st.system_of_measure.get(_tstamp2_end_measure(m, tstamp2))
            staff_n = staff_n or st.mei.staff_attr_by_id.get(vid, 0)
        if acc.system is None or end_sys is None or end_sys <= acc.system:
            continue
        sources.append((acc.svg_class, acc.system, end_sys,
                        (staff_n, end_y if end_y is not None else 0.0), vid))

    segments: dict[tuple[str, int], list[_ElementAccumulator]] = \
        defaultdict(list)
    for _, acc in accumulators:
        if acc.continuation:
            if acc.system is None or acc.bbox is None:
                raise ValueError(
                    f"continuation {acc.svg_class} segment without "
                    f"system/bbox — cannot attribute")
            if acc.source_vid:
                continue    # pre-attributed by _reclaim_spanner_ink:
                            # its source is KNOWN, keep it out of the
                            # y-order pairing pool
            segments[(acc.svg_class, acc.system)].append(acc)

    for (cls, sys_n), segs in segments.items():
        if cls in ("tie", "lv"):
            crossing = (s for s in sources
                        if s[0] == cls and s[1] < sys_n and s[2] == sys_n)
        else:
            crossing = (s for s in sources
                        if s[0] == cls and s[1] < sys_n <= s[2])
        # Pair by (staff, end_y): a system-broken spanner continues on its
        # start staff, so sources and their continuation segments must line up
        # in STAFF order. The staff key is now the start-note staff (above),
        # which is reliable even when the end note's accumulator is missing —
        # previously it was the end-note staff, 0 when that note wasn't found,
        # collapsing several sources to an arbitrary end_y=0 order and handing
        # segments the wrong source (a phantom slur on the wrong part's edge).
        candidates = sorted(crossing, key=lambda s: s[3])
        if len(candidates) != len(segs):
            st.warnings.append(LoadWarning(
                "segment-count-mismatch",
                f"system {sys_n}: {len(segs)} {cls} continuation "
                f"segment(s), {len(candidates)} crossing source "
                f"spanner(s) — pairing up to the shorter list"))
        segs.sort(key=lambda a: a.bbox.center.y)       # type: ignore[union-attr]
        for seg, (_, _, _, _, vid) in zip(segs, candidates):
            seg.source_vid = vid

    # Segment index per source, in system order (a spanner across 3+
    # systems has several continuation segments: seg1, seg2, ...).
    # Unmatched segments (source_vid None) are skipped by
    # _build_elements with an unattributed-continuation warning.
    by_source: dict[str, list[_ElementAccumulator]] = defaultdict(list)
    for _, acc in accumulators:
        if acc.continuation and acc.source_vid:
            by_source[acc.source_vid].append(acc)
    for segs in by_source.values():
        segs.sort(key=lambda a: a.system or 0)
        for k, seg in enumerate(segs, start=1):
            seg.seg_index = k

    # Spanners the engraver dropped: the MEI records them but no ink
    # exists under their OWN class family (Verovio's "N ties left open" /
    # "tie ignored" warnings, and testscore's 5 open ties). A foreign
    # group merely REUSING the id must not count as drawn — that masking
    # was FINDING-5's silent half; ink reclaimed into a continuation
    # segment counts via its source vid. Non-spanner-class tags (octave)
    # keep the original any-group test. Flag-and-continue (ruling b);
    # timing is unaffected — tie chains come from the music21 ScoreModel,
    # not drawn ties.
    spanner_inked = {acc.verovio_id for _, acc in accumulators
                     if acc.verovio_id and not acc.continuation
                     and acc.svg_class in _SPANNER_CLASSES
                     and (acc.paths or acc.texts)}
    seg_sources = {acc.source_vid for _, acc in accumulators
                   if acc.continuation and acc.source_vid}
    any_drawn = {acc.verovio_id for _, acc in accumulators
                 if acc.verovio_id}
    for vid, tag in sorted(st.mei.spanner_tags.items()):
        if vid in spanner_inked or vid in seg_sources:
            continue
        if tag not in ("slur", "tie", "lv", "hairpin") and vid in any_drawn:
            continue
        start_id, _ = st.mei.spanners[vid]
        start = st.mei.notes.get(start_id or "")
        if start is not None:
            info = st.prep.part_for_staff(start.staff)
            where = (f"from {info.part_id} m{start.measure} "
                     f"s{start.staff - info.first_staff + 1}")
        else:
            where = "with unresolved start"
        st.warnings.append(LoadWarning(
            "dropped-spanner",
            f"{tag} {where} was not drawn by the engraver"))


def _rehome_stray_paths(accumulators: list[tuple[int, _ElementAccumulator]],
                        st: _LoadState) -> None:
    """Re-home a drawable whose geometry lands in a DIFFERENT system than
    its element's attribution. Under hide-empty-staves (the scoreDef
    @optimize round-trip) Verovio reuses one xml:id across element types
    and can emit a spanner's <path> INSIDE a note's <g class="stem|flag">
    group whose id collides — e.g. a tie curve belonging to a LATER
    system nested in an EARLIER note's stem (bigband1, 2026-07-21). The
    stem then inherits that early note's system/onset, so at the stem's
    reveal time the absorbed curve paints down in the later system —
    invisible among the ghosts at the default floor, solid ink at floor 0.

    The per-(system, part) reveal edge assumes an element's ink lies
    within its attributed system; a path crossing systems breaks that
    invariant. We split each stray path out into its own OTHER element
    attributed by GEOMETRY to the system its coordinates occupy (onset =
    that system's first measure, the animate-everything measure-start
    fallback), so it lights in the right place and never leaks. No ink is
    dropped (rule 7); flag-and-continue with one warning per re-homed
    element (ruling b). A no-op on well-formed scores — only an element
    whose bbox straddles a system boundary is examined. Runs AFTER
    _reclaim_spanner_ink, which intercepts the slur/tie share of the
    id-reuse artifact by id; rehome remains the geometric backstop for
    any other cross-system leak."""
    ordered = _system_partition(accumulators)

    def system_at(page: int, y: float) -> int | None:
        return _system_at(ordered, page, y)

    first_of_system: dict[int, int] = {}
    for m, s in st.system_of_measure.items():
        if m < first_of_system.get(s, 1 << 30):
            first_of_system[s] = m

    for page, acc in list(accumulators):
        if (acc.system is None or acc.bbox is None or not acc.paths
                or acc.texts):
            continue
        # cheap pre-filter: only a bbox straddling a system boundary can
        # hold a foreign-system path
        if (system_at(page, acc.bbox.y) == acc.system
                and system_at(page, acc.bbox.y2) == acc.system):
            continue
        strays: dict[int, list[PathPrimitive]] = defaultdict(list)
        kept: list[PathPrimitive] = []
        for prim in acc.paths:
            box = prim.transform.apply_rect(path_bbox(prim.d))
            target = system_at(page, box.center.y)
            if target is not None and target != acc.system:
                strays[target].append(prim)
            else:
                kept.append(prim)
        if not strays:
            continue
        acc.paths[:] = kept
        acc.literal_curves.clear()   # indices stale; sole consumer
                                     # (_reclaim_spanner_ink) already ran
        acc.bbox = None
        for prim in kept:
            acc.add_bbox(prim.transform.apply_rect(path_bbox(prim.d)))
        for target, prims in sorted(strays.items()):
            box = None
            for prim in prims:
                r = prim.transform.apply_rect(path_bbox(prim.d))
                box = r if box is None else box.union(r)
            centers = st.staff_centers_by_system.get(target, {})
            staff_n = (min(centers, key=lambda n: abs(centers[n] - box.center.y))
                       if centers else None)
            # Reveal-clip (TIE) when the ink resolves to a staff/part, so it
            # grows in with the playhead SWEEP at its own x — a spanner
            # curve drawn late in the system must not pop at the system's
            # downbeat (2026-07-21, cursor-in-m26 regression). The onset
            # stays None (edge-driven, like any REVEALED kind); its clip
            # rides the (system, part) reveal curve the part's own notes
            # build. Fall back to a measure-start OTHER only when no staff
            # underlies the ink (no reveal curve to ride — never leak).
            rehomed = _ElementAccumulator(
                verovio_id="", svg_class="",
                kind=ElementKind.TIE if staff_n else ElementKind.OTHER,
                measure=first_of_system.get(target), staff=staff_n,
                layer=None, owner_onset=None, system=target)
            rehomed.paths.extend(prims)
            rehomed.bbox = box
            accumulators.append((page, rehomed))
            st.warnings.append(LoadWarning(
                "stray-path",
                f"{acc.svg_class or acc.kind.name.lower()} on page {page} "
                f"carried {len(prims)} path(s) drawn in system {target}, "
                f"not its own system {acc.system} — re-homed to system "
                f"{target} so it animates in place (Verovio id-reuse "
                f"artifact under hide-empty-staves)"))


def _flag_implausible_ties(st: _LoadState) -> None:
    """Verovio force-matches some ties it cannot close to DISTANT
    same-pitch notes (video_test: e.g. a "tie" from m5 to m44, 148.5
    quarters — the stacked curves drew as ovals around the destination
    bar). A real tie connects adjacent notes: anything spanning more
    than two of its start measure's durations is an engraving artifact.
    Runs AFTER segment matching (the bogus sources must stay in the
    candidate pool so the y-order pairing of the remaining segments is
    right) and before element construction, which skips the suppressed
    vids and their continuation segments. Flag-and-continue (ruling b):
    one warning per suppressed tie, musical coordinates only."""
    for vid, tag in sorted(st.mei.spanner_tags.items()):
        if tag != "tie":         # lv has no end; slurs/hairpins can be long
            continue
        start_id, end_id = st.mei.spanners[vid]
        start = st.onset_by_id.get(start_id or "")
        end = st.onset_by_id.get(end_id or "")
        note = st.mei.notes.get(start_id or "")
        if start is None or end is None or note is None:
            continue             # ink-less opens hit the dropped path
        limit = 2.0 * st.measure_duration.get(note.measure, 4.0)
        if end - start > limit:
            st.suppressed_spanners.add(vid)
            info = st.prep.part_for_staff(note.staff)
            st.warnings.append(LoadWarning(
                "implausible-tie",
                f"tie from {info.part_id} m{note.measure} "
                f"s{note.staff - info.first_staff + 1} spans "
                f"{end - start:g} quarters (> 2 bars) — suppressed as "
                f"an engraving artifact"))


def _tstamp2_end_measure(start_measure: int, tstamp2: str | None) -> int:
    if tstamp2 and "m+" in tstamp2:
        return start_measure + int(tstamp2.split("m+", 1)[0])
    return start_measure


def _tstamp_extent(entry: tuple[int, str, str | None], st: _LoadState
                   ) -> tuple[Beats, tuple[Beats, Beats]]:
    """Onset/extent in quarters for a timestamp-addressed spanner
    (hairpins: @tstamp/@tstamp2 in meter units, 1-based; tstamp2 grammar
    "<n>m+<beat>" or a bare beat)."""
    m, tstamp, tstamp2 = entry

    def q_at(measure: int, beat: str) -> Beats:
        unit = st.mei.meter_unit_by_measure.get(measure, 4)
        return st.measure_start[measure] + (float(beat) - 1.0) * (4.0 / unit)

    start = q_at(m, tstamp)
    if not tstamp2:
        return start, (start, start)
    if "m+" in tstamp2:
        ahead, beat = tstamp2.split("m+", 1)
        end = q_at(m + int(ahead), beat)
    else:
        end = q_at(m, tstamp2)
    return start, (start, end)
