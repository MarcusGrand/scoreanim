"""The Volume response block: where its values live, and its three
knobs.

Data and one small store, riding the same `KnobGroup` machinery every
preset's options use (`ui/panels/effect_knobs.py`) — same live fields,
same one command per gesture, same gray-out. The only thing that
differs is the document field, which is what the store says.

Unlike a preset's block this one is always on screen: it is not an
effect, so the "show the options of the effect you are using" rule has
nothing to say about it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from scoreanim.core.animation.intensity import (DEFAULT_AMOUNT, DEFAULT_LOUD,
                                                DEFAULT_QUIET)
from scoreanim.core.project import Command, ProjectDoc, SetVolumeParam
from scoreanim.ui.panels.knob_types import Number

TITLE = "Volume response"


@dataclass(frozen=True)
class VolumeStore:
    """The sparse `style.volume` map."""

    def stored(self, doc: ProjectDoc) -> Mapping[str, object]:
        return doc.style.volume

    def has_values(self, doc: ProjectDoc) -> bool:
        return bool(doc.style.volume)

    def command(self, key: str,
                value: float | int | bool | None) -> Command:
        return SetVolumeParam(key, value)


# Amount comes first because it is the switch: at 0 the other two are
# grayed out, since they describe a range nothing is being read onto.
KNOBS: tuple[Number, ...] = (
    Number("Amount", "amount", DEFAULT_AMOUNT, 0.0, 1.0, 0.1,
           "How much the recording's loudness changes how strongly a "
           "note animates — 0 is off, every note animates the same"),
    Number("Quiet", "quiet", DEFAULT_QUIET, 0.0, 5.0, 0.05,
           "How strongly the quietest beats animate: below 1 they are "
           "more subtle than authored, above 1 more prominent",
           enabled_by="amount"),
    Number("Loud", "loud", DEFAULT_LOUD, 0.0, 5.0, 0.05,
           "How strongly the loudest beats animate: above 1 they are "
           "more prominent than authored",
           enabled_by="amount"),
)
