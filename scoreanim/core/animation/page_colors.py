"""The two colours the whole page is drawn in: the paper and the ink.

A score can be black paper with white notation, or any other pair. This
is appearance, not motion — it is a recolour of the scene items when the
document changes, never per-frame work — but it lives here because it
reads a `StyleRules` entry, like its neighbours `read_volume` and
`read_pulse`.

Named `page_colors` rather than `colors` on purpose: this codebase
already has element colours (a part tint, a per-element override), and
those are a different thing. These two are document-wide, and they reach
EVERYTHING — staff lines, clefs, rests and barlines included, not just
`TINTED_KINDS`. A white-on-black page needs white staff lines or there is
no staff.

The defaults are the look the app has always had, and a document that
never touches the entry stores nothing at all, so it renders exactly as
it did before this existed.

**Validation happens here, at consumption**, which is the `style.volume`
precedent: the command that writes the entry only checks that a value is
a string. The difference from `read_volume` and `read_pulse` is that
those raise on nonsense (`float("abc")` is an error) and this one does
not — an unreadable colour falls back to its own default, and the other
colour is unaffected. That is deliberate. A hand-edited file must not be
able to produce a score nobody can see.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

DEFAULT_BACKGROUND = "#ffffff"      # white paper
DEFAULT_INK = "#000000"             # black notation

_HEX_DIGITS = "0123456789abcdef"


@dataclass(frozen=True)
class PageColors:
    """The document's two colours, always a normalized lowercase
    "#rrggbb" string — so a caller can hand either straight to QColor
    without checking anything."""
    background: str = DEFAULT_BACKGROUND
    ink: str = DEFAULT_INK

    @property
    def is_default(self) -> bool:
        """Nothing to apply: this is the look a fresh scene is already
        built in, so the recolour pass can skip the sweep entirely."""
        return (self.background == DEFAULT_BACKGROUND
                and self.ink == DEFAULT_INK)


def read_colors(raw: Mapping[str, object] | None) -> PageColors:
    """The document's sparse `style.colors` entry, made safe.

    Each key falls back on its own: an unreadable ink still leaves a
    good background, so one bad value in a hand-edited file costs one
    colour rather than the whole page."""
    raw = raw or {}
    return PageColors(background=_hex(raw.get("background"),
                                      DEFAULT_BACKGROUND),
                      ink=_hex(raw.get("ink"), DEFAULT_INK))


def _hex(value: object, default: str) -> str:
    """A "#rgb" or "#rrggbb" colour as normalized lowercase "#rrggbb".
    Anything else — a colour name, the wrong length, a stray character,
    a number, a missing key — is the default.

    Hand-rolled rather than handed to QColor because core is pure Python
    (rule 1), and QColor would accept names like "red" that nothing else
    in this codebase's stored colours uses."""
    if not isinstance(value, str):
        return default
    text = value.strip().lower()
    if not text.startswith("#"):
        return default
    text = text[1:]
    if len(text) == 3:                          # #rgb shorthand
        text = "".join(c * 2 for c in text)
    if len(text) != 6 or any(c not in _HEX_DIGITS for c in text):
        return default
    return "#" + text
