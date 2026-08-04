"""The break passes: system and page breaks in the canonical MusicXML.

Split out of `musicxml_rewrite` (2026-08-03) when that module went past
the size ceiling. Nothing changed but the address — `musicxml_prep`
re-exports every name here, so no caller moved.

These passes are what turns the document's break INTENT into `<print
new-system>` / `<print new-page>` attributes, plus the never-clip
repagination that rule 7 owns. They share the module family's shape: a
tree in, mutated in place, nothing returned but incidental counts.

The two enums live here rather than in `core/project` because they are
the `<print>` attribute's own vocabulary, and the pass that writes the
attribute is the one that should name it.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from enum import Enum
from typing import Mapping


class SystemBreak(str, Enum):
    """What the user asked of one measure's system break (M5).

    This is the `<print new-system>` vocabulary, so it lives with the pass
    that writes the attribute and is re-exported from `musicxml_prep` as
    the prep seam's public face. Unlike the `*Spec` dataclasses it has NO
    neutral twin in `core/project`: a two-valued vocabulary has no fields
    to twin, and the layering already permits `core/project` to import
    `core/score` (the `PartId` shape). One enum, no conversion at the
    seam.
    """
    FORCE = "force"          # start a system at this measure
    SUPPRESS = "suppress"    # do NOT start a system at this measure


class PageBreak(str, Enum):
    """What the user asked of one measure's page break (M6).

    `SystemBreak`'s twin, for the `<print new-page>` attribute, and the
    same reasoning applies: it lives with the pass that writes the
    attribute, is re-exported from `musicxml_prep`, and has no neutral
    twin in `core/project` because a two-valued vocabulary has no fields
    to twin.

    Kept a SEPARATE enum from `SystemBreak` rather than one shared
    Force/Suppress vocabulary: the two maps are different documents
    fields with different meanings at the seam, and a mis-keyed value
    should be a type error rather than a silently plausible one.
    """
    FORCE = "force"          # start a page at this measure
    SUPPRESS = "suppress"    # do NOT start a page at this measure


def _wanted_break_attrs(sys_mode: SystemBreak | None,
                        page_mode: PageBreak | None,
                        encoded_system: str | None,
                        encoded_page: str | None
                        ) -> tuple[str | None, str | None]:
    """THE coherence rule for one measure (M6, D3): what `new-system`
    and `new-page` should become, given both overrides and what the file
    already says. `None` means "do not touch this attribute".

    Pure and total — every combination of (system override, page
    override, encoded state) has an answer here, and `_apply_breaks` only
    executes it. That is deliberate: §3.4 measured the incoherent
    combination resolving in OPPOSITE directions under the two possible
    pass orderings, so the answer must be STATED rather than fall out of
    which pass happens to run last.

    The rule, in the order it is applied:

    1. **Page FORCE wins outright**, including over a coincident system
       SUPPRESS: a page break implies a system break, so `new-page="yes"`
       and `new-system="yes"` are asserted together. Refusing the system
       break while asserting the page break is not a layout — it is a
       contradiction, and the positive assertion is the one that can be
       honored.
    2. **Page SUPPRESS preserves the system break it is removing.** This
       is the §3.1 A3/A4 fix and the exact mirror of M5's D7: Dorico
       encodes a page break as `new-page` ALONE, so clearing it would
       clear the measure's only break marker and silently merge two
       systems the user never asked to merge. So the suppression also
       asserts `new-system="yes"` — UNLESS the user has separately asked
       to suppress the system break too, which is a coherent pair (both
       negative) and means exactly what it says.
       A page SUPPRESS where nothing is encoded to suppress writes
       nothing at all, so the canonical XML stays a true delta.
    3. **With no page override, the system rules of M5 apply unchanged**,
       D7 included: a system SUPPRESS also clears a coincident
       `new-page`, because leaving it would make the suppression a lie.
    """
    if page_mode is PageBreak.FORCE:                       # (1)
        return "yes", "yes"
    if page_mode is PageBreak.SUPPRESS:                    # (2)
        if encoded_page != "yes":
            return _system_only(sys_mode, encoded_system, encoded_page)
        return ("no" if sys_mode is SystemBreak.SUPPRESS else "yes"), "no"
    if page_mode is not None:
        raise ValueError(f"unknown page break mode {page_mode!r}")
    return _system_only(sys_mode, encoded_system, encoded_page)          # (3)


def _system_only(sys_mode: SystemBreak | None,
                 encoded_system: str | None,
                 encoded_page: str | None) -> tuple[str | None, str | None]:
    """Rule 3 of `_wanted_break_attrs` — M5's system-break behaviour,
    unchanged, including D7's coincident-page clearing."""
    if sys_mode is None:
        return None, None
    if sys_mode is SystemBreak.FORCE:
        return "yes", None
    if sys_mode is SystemBreak.SUPPRESS:
        if encoded_system == "yes" or encoded_page == "yes":
            return "no", ("no" if encoded_page == "yes" else None)
        # nothing encoded to suppress: writing "no" would assert a
        # negative the file never claimed, so write nothing (the
        # override is inert, and reported as such)
        return None, None
    raise ValueError(f"unknown system break mode {sys_mode!r}")


def _apply_breaks(root: ET.Element,
                  system_overrides: Mapping[int, SystemBreak],
                  page_overrides: Mapping[int, PageBreak] | None = None
                  ) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Apply the user's break intent to `<print>` (M5 systems, M6 pages).

    A deliberate twin of `_repaginate` — part 1 only (Verovio reads print
    layout from the first part, spike section D), keyed by 1-based
    document ordinal (never the printed number, adapter item 12),
    creating `<print>` when a positive assertion needs one — with one
    difference that matters: it is STORED intent, not a derived plan, so
    unlike `_repaginate` it never strips the encoded breaks first. It is
    a sparse DELTA, on both axes: a measure with no override keeps
    whatever the file encodes.

    **ONE pass over both maps, not two racing ones** (D3). The two
    override maps write two attributes of the SAME `<print>` element, and
    §3.4 measured what two passes cost: whichever ran first, the second
    found the element already rewritten and reported the user's override
    as inert — `break-override-inert` firing on gestures that had worked
    perfectly. Computing both attributes in one visit removes those false
    warnings by construction rather than by ordering luck, and puts the
    semantic couplings between the two axes in one readable place
    (`_wanted_break_attrs`).

    Returns `(inert_system_ordinals, inert_page_ordinals)`, each in score
    order — the two D8 warnings' input. An override is inert when this
    pass changed nothing on ITS OWN attribute: an ordinal past the end of
    a score since shortened (the loop never reaches it), a suppression
    whose encoded break has gone, or an assertion the file already made.
    It deliberately does NOT mean "had no visible effect", which only a
    second no-override load could establish — nor "was overruled", which
    is never-clip's business and gets its own code (D8).
    """
    page_overrides = page_overrides or {}
    if not system_overrides and not page_overrides:
        return (), ()
    parts = root.findall("part")
    if not parts:
        return tuple(sorted(system_overrides)), tuple(sorted(page_overrides))

    inert_system = set(system_overrides)
    inert_page = set(page_overrides)
    for ordinal, measure in enumerate(parts[0].findall("measure"), start=1):
        sys_mode = system_overrides.get(ordinal)
        page_mode = page_overrides.get(ordinal)
        if sys_mode is None and page_mode is None:
            continue
        pr = measure.find("print")
        want_system, want_page = _wanted_break_attrs(
            sys_mode, page_mode,
            None if pr is None else pr.get("new-system"),
            None if pr is None else pr.get("new-page"))
        if want_system is None and want_page is None:
            continue
        if pr is None:
            pr = ET.Element("print")
            measure.insert(0, pr)
        # An override is credited only with its OWN attribute changing,
        # so a page FORCE that also asserts the implied system break does
        # not silently "un-inert" a system override that wrote nothing.
        if want_system is not None and pr.get("new-system") != want_system:
            pr.set("new-system", want_system)
            inert_system.discard(ordinal)
        if want_page is not None and pr.get("new-page") != want_page:
            pr.set("new-page", want_page)
            inert_page.discard(ordinal)
    return tuple(sorted(inert_system)), tuple(sorted(inert_page))


def _promote_page_breaks_to_system(root: ET.Element) -> int:
    """Say out loud the system break every encoded page break implies
    (M6.0, BACKLOG 16 — measured in spikes/page_breaks.py section F).

    Dorico encodes a page break as `new-page="yes"` ALONE: the measure
    carries no `new-system`, because starting a page starts a system by
    definition. That makes the page attribute the measure's ONLY break
    marker, so anything that clears it silently takes the system break
    with it — and `_repaginate` clears every one of them before
    asserting its own plan. The consequence, on `main` before this pass:
    forcing a system break anywhere on a score with page-only markers
    repaginates, and the encoded system structure collapses (testscore
    m19 went from five systems to four, merging 1+2 and 3+4 — spike F2).

    That contradicts rule 7(a)'s own wording, which says repagination
    KEEPS the encoded system breaks. This pass makes the wording true:
    every `new-page="yes"` also gets `new-system="yes"` before anything
    can strip it, so a re-derived page plan can never change system
    content. Measured a total no-op at baseline on all four fixtures —
    systems, pages and element ids identical, goldens unmoved (spike F1)
    — because the two attributes already agree wherever both are read.

    Returns how many measures were promoted. All parts, not just part 1:
    Verovio reads print layout from the first part, but a promotion is
    harmless anywhere and leaving later parts inconsistent with part 1
    would be a trap for the next reader.
    """
    promoted = 0
    for part in root.findall("part"):
        for measure in part.findall("measure"):
            pr = measure.find("print")
            if (pr is not None and pr.get("new-page") == "yes"
                    and pr.get("new-system") != "yes"):
                pr.set("new-system", "yes")
                promoted += 1
    return promoted


def _repaginate(root: ET.Element, break_measures: tuple[int, ...]) -> None:
    """Replace the encoded PAGE breaks with our own (Phase 10R, rule-7
    amendment): keep every encoded system break, strip all new-page
    attributes, and set new-page="yes" at the given system-start
    measures. Part 1 only — Verovio reads print layout from the first
    part (spike section D). Called only when the measured first pass
    overflowed; the plan is derived data, never stored (rule 5).

    "Keep every encoded system break" is only true because of the
    promotion below (M6.0): a page-only marker's system break has to be
    said out loud before the strip, or the strip takes it away."""
    parts = root.findall("part")
    if not parts:
        return
    _promote_page_breaks_to_system(root)
    for part in parts:
        for measure in part.findall("measure"):
            pr = measure.find("print")
            if pr is not None and pr.get("new-page"):
                del pr.attrib["new-page"]
    wanted = set(break_measures)
    # Measure identity is the 1-based document-order ordinal everywhere (see
    # verovio.mei_index._parse_mei): `break_measures` come from the adapter's
    # ordinal-keyed system_of_measure, so match by ordinal here — the printed
    # `number` is neither unique nor consistent (Dorico's "X0"/"X1" bars).
    for ordinal, measure in enumerate(parts[0].findall("measure"), start=1):
        if ordinal in wanted:
            pr = measure.find("print")
            if pr is None:
                pr = ET.Element("print")
                measure.insert(0, pr)
            pr.set("new-page", "yes")
