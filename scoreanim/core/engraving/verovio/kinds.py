"""Policy tables for the Verovio adapter — data only, no logic.

XML namespaces, the SVG-class → ElementKind map, container/spanner/text
class sets, timemap-key classes, text-style sets, scale constants, and
the accidental → alter table. Every other stage module reads these; this
module imports nothing but the neutral identity types.
"""

from __future__ import annotations

from scoreanim.core.score.identity import ElementKind

_MEI_NS = "{http://www.music-encoding.org/ns/mei}"
_SVG_NS = "{http://www.w3.org/2000/svg}"
_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
_XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

# SVG class (first token) → ElementKind for emitted elements.
_KIND_BY_CLASS: dict[str, ElementKind] = {
    "note": ElementKind.NOTEHEAD,
    "rest": ElementKind.REST,
    "mRest": ElementKind.MREST,
    "multiRest": ElementKind.MREST,
    "stem": ElementKind.STEM,
    "flag": ElementKind.FLAG,
    "dots": ElementKind.OTHER,
    "beam": ElementKind.BEAM,
    "slur": ElementKind.SLUR,
    "tie": ElementKind.TIE,
    "lv": ElementKind.TIE,
    "hairpin": ElementKind.HAIRPIN,
    "accid": ElementKind.ACCIDENTAL,
    "artic": ElementKind.ARTICULATION,
    # tremolo stroke groups (Phase 11): id-bearing, the stroke <use>
    # (SMuFL E22x) is a DIRECT child, so bTrem/fTrem must EMIT their own
    # element or the stroke folds into the static staff scaffold (the
    # BACKLOG-6 shape). Carries its child note's onset, animates untinted
    # (ruling a). fTrem never occurs in either fixture — defensive.
    "bTrem": ElementKind.TREMOLO,
    "fTrem": ElementKind.TREMOLO,
    # cross-measure/cross-staff beam (Phase 11): id-bearing with direct
    # polygon children; onset/extent come from its MEI @startid/@endid,
    # NOT the layer-beam table (beamSpan is a measure-level spanner)
    "beamSpan": ElementKind.BEAM,
    "dynam": ElementKind.DYNAMIC,
    "clef": ElementKind.CLEF,
    "keySig": ElementKind.KEY_SIG,
    "meterSig": ElementKind.METER_SIG,
    "barLine": ElementKind.BARLINE,
    "staff": ElementKind.STAFF_LINES,
    "harm": ElementKind.CHORD_SYMBOL,
    "verse": ElementKind.LYRIC,
    "syl": ElementKind.LYRIC,
    "tempo": ElementKind.TEXT,
    "dir": ElementKind.TEXT,
    "reh": ElementKind.TEXT,
    "label": ElementKind.TEXT,
    "labelAbbr": ElementKind.TEXT,
    "pgHead": ElementKind.TEXT,
    "pgFoot": ElementKind.TEXT,
    "mNum": ElementKind.TEXT,
    "tuplet": ElementKind.OTHER,
    "tupletNum": ElementKind.OTHER,
    "tupletBracket": ElementKind.OTHER,
    "arpeg": ElementKind.OTHER,
    "fermata": ElementKind.ARTICULATION,
    "trill": ElementKind.OTHER,
    "mordent": ElementKind.OTHER,
    "turn": ElementKind.OTHER,
    "octave": ElementKind.OTHER,
    "breath": ElementKind.OTHER,
    # the system-left vertical line joining a system's staves IS a
    # barline — scaffold, static by the denylist (ruling 2026-07-20).
    # It owns only that path; measures/staves nest as their own elements.
    "system": ElementKind.BARLINE,
    "grpSym": ElementKind.GROUP_SYMBOL,  # staff-group bracket/brace (Phase 8);
                                         # joined-barline connector paths land
                                         # inside the ordinary barLine groups
                                         # (spikes/NOTES.md Phase 8), so no
                                         # further class is needed
    # id-less between-system divider glyph; drawn only under condensed
    # layout, which condense:"encoded" disables — defensive (Phase 10)
    "systemDivider": ElementKind.SYSTEM_DIVIDER,
    # bracket/line spanner group: id-bearing, empty on the Phase 10
    # fixture; if a future score inks it, it renders as static OTHER
    # instead of tripping the unknown-class guard
    "bracketSpan": ElementKind.OTHER,
}

# Transparent grouping classes: never emitted, provide context only.
# keyAccid/fig fold their glyphs into the enclosing keySig / harm element;
# space and the milestone markers contain nothing drawable. ledgerLines
# is NOT here: its dashes are emitted per-path as LEDGER_LINES elements
# and attributed to noteheads afterwards (BACKLOG 6).
_CONTAINER_CLASSES = {
    "measure", "layer", "chord", "graceGrp", "notehead",
    "page-margin", "definition-scale", "section", "pb", "sb", "ending",
    "keyAccid", "fig", "mdiv", "score", "svg", "space",
    "pageMilestoneEnd", "systemMilestoneEnd", "pageElement",
    "mSpace",           # invisible measure space (Phase 10 fixture) —
                        # nothing drawable, the `space` precedent
}

# Short kind tag used inside minted ElementIds.
_ID_TAG = {k: k.name.lower() for k in ElementKind}

# SVG classes that are drawn spanners. A system-broken spanner renders as
# one id-bearing <g> in its start measure plus one id-less <g> per
# continuation system (Phase 5 spike, spikes/spanner_split.py).
_SPANNER_CLASSES = {"slur", "tie", "hairpin", "lv"}

# Page furniture: TEXT sub-classes that stay STATIC under the Phase 10R
# animate-everything ruling (part labels, page header/footer, measure
# numbers are navigation furniture, not musical objects). They mint
# onset=None, which is what the schedule's onset gate excludes.
_STATIC_TEXT_CLASSES = {"label", "labelAbbr", "pgHead", "pgFoot", "mNum"}

# Scale-to-fit (Phase 12.5): Verovio's default scale is 100; a system
# taller than its page is shrunk to `100 · page_h / bottom · _FIT_MARGIN`
# so nothing is clipped (rule 7). The margin absorbs the small part of the
# layout — top/bottom page margins — that does not scale perfectly linearly.
_DEFAULT_SCALE = 100
_FIT_MARGIN = 0.96

# SVG classes whose Verovio id is genuinely a timemap key (notes and
# rests). Note-owned fragments (stems, flags, accidentals, beams, …)
# derive their onset from their owner, NOT their own id — and MUST NOT
# consult the id tables, because Verovio reuses SVG group ids across
# element types under condensed layout (hide-empty-staves): an m1 stem
# and an m44 note can share an id, so a naive id lookup would give the
# stem the note's late onset (Phase 10R bug, spikes/NOTES.md).
_TIMEMAP_CLASSES = {"note", "rest", "mRest", "multiRest"}

# Verovio styles its SVG through one small stylesheet instead of element
# attributes; its effective rules are baked into the primitives so the
# redraw needs no CSS: every shape strokes in currentColor, and text
# weight/style follow the owning class.
_BOLD_TEXT_CLASSES = {"ending", "fing", "reh", "tempo"}
_ITALIC_TEXT_CLASSES = {"dir", "dynam", "mNum"}

_ACCID_TO_ALTER = {
    None: 0.0, "": 0.0, "n": 0.0, "s": 1.0, "f": -1.0,
    "ss": 2.0, "x": 2.0, "ff": -2.0,
}
