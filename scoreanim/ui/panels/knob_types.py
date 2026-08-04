"""What a knob IS, and where its value lives — the data half of a knob
group.

Effects are data (rule 6), and so are their knobs. A preset with options
is a list of the types below plus one entry in the panel's table — never
a second code path. `ui/panels/effect_knobs.py` is the other half: the
widgets those types build and the commands they commit.

Four kinds cover everything the presets ask for so far:

- `Number` — a spinbox that previews as you type (`ui/live_field.py`).
  `factor` is UI units per document unit, which is how Peak offset
  shows whole milliseconds over seconds in the document.
- `Check` — a checkbox, which has no half-typed state and so commits
  outright. `beside` puts it on another knob's row instead of its own,
  the way "Entire note value" sits beside the duration it replaces.
- `Color` — a swatch button that opens the colour dialog, storing
  "#rrggbb" (the selection panel's pattern). Like a checkbox it has no
  half-chosen state: the dialog either returns a colour or it does not.
- `Choice` — a dropdown over a few named options, storing the chosen
  option's own word — the glow's two shapes.
- `grayed_by` on a Number names the key that renders it obsolete: a
  duration grays out while its "Entire note value" is on (Marcus,
  2026-07-25). `enabled_by` is its mirror — the knob is live only while
  another key is on, which is how Quiet and Loud wait for Amount.
- `forced_by` on a Check names the key that turns it on regardless: the
  box then shows checked and grayed, because that IS what the effect is
  doing (Marcus, 2026-08-01 — "Follow volume" forces "Entire note
  value"). The document is left alone; core is still the one that
  decides, and this only stops the panel from saying otherwise.

Every knob carries its own default — the value the consumer falls back
to when the document is sparse. That default is what the panel shows,
what a no-op guard compares against, and what tells Reset whether there
is anything to clear.

WHERE a group's values live is the group's `store`. A preset's knobs
read `style.effect_params[preset]` and commit `SetEffectParam`; the
volume response reads `style.volume` and commits `SetVolumeParam`. Same
widgets, same live-field rules, same one-command-per-gesture — only the
document field differs, so it is a small object, not a second class.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from scoreanim.core.project import Command, ProjectDoc, SetEffectParam


@dataclass(frozen=True)
class Number:
    """A number knob. `integer` picks a whole-number box (Peak offset in
    ms); everything else is a two-decimal float box."""
    label: str
    key: str
    default: float
    minimum: float
    maximum: float
    step: float
    tooltip: str
    suffix: str = ""
    factor: float = 1.0             # UI units per document unit
    integer: bool = False
    grayed_by: str | None = None    # the key that makes this knob obsolete
    enabled_by: str | None = None   # the key that has to be on for this one


@dataclass(frozen=True)
class Check:
    """A checkbox knob. `beside` names the knob whose row it shares; on
    its own it takes a full row with no label. `forced_by` names the key
    that turns this one on whatever the document says."""
    text: str
    key: str
    default: bool
    tooltip: str
    beside: str | None = None
    forced_by: str | None = None


@dataclass(frozen=True)
class Color:
    """A colour knob: a swatch showing the colour, opening the colour
    dialog. Stored as "#rrggbb"."""
    label: str
    key: str
    default: str
    tooltip: str
    title: str = "Colour"           # the dialog's own title


@dataclass(frozen=True)
class Choice:
    """A few named options, one of them stored. `options` is
    (what the document holds, what the user reads)."""
    label: str
    key: str
    default: str
    options: tuple[tuple[str, str], ...]
    tooltip: str


Knob = Number | Check | Color | Choice


class KnobStore(Protocol):
    """Where one group's values live in the document, and what one edit
    of them costs — the only thing that differs between groups."""

    def stored(self, doc: ProjectDoc) -> Mapping[str, object]:
        """This group's raw entry; empty when the document is silent."""

    def has_values(self, doc: ProjectDoc) -> bool:
        """Anything stored at all — what lights Reset up."""

    def command(self, key: str, value: float | int | bool | None) -> Command:
        """The ONE command a gesture on this group commits."""


@dataclass(frozen=True)
class EffectParamStore:
    """One preset's knobs: the sparse `style.effect_params` map."""
    preset: str

    def stored(self, doc: ProjectDoc) -> Mapping[str, object]:
        return doc.style.effect_params.get(self.preset, {})

    def has_values(self, doc: ProjectDoc) -> bool:
        return self.preset in doc.style.effect_params

    def command(self, key: str,
                value: float | int | bool | None) -> Command:
        return SetEffectParam(self.preset, key, value)
