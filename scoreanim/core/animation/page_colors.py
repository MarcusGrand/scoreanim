"""Light mode or dark mode: the two colours the whole page is drawn in.

A score is either black on white or white on a dark blue-grey. That is
the whole setting — one choice, not two colour pickers. Per-colour
fine-tuning may come back later, and the sparse entry has room for it,
but the intent stored today is the MODE (rule 5: the document holds
intent, and the two colours are derived from it).

This is appearance, not motion — it is a recolour of the scene items
when the document changes, never per-frame work — but it lives here
because it reads a `StyleRules` entry, like its neighbours `read_volume`
and `read_pulse`.

Named `page_colors` rather than `colors` on purpose: this codebase
already has element colours (a part tint, a per-element override), and
those are a different thing. These two are document-wide, and they reach
EVERYTHING — staff lines, clefs, rests and barlines included, not just
`TINTED_KINDS`. A white-on-dark page needs white staff lines or there is
no staff.

Light is the default and stores nothing at all, so a document that never
touches the setting renders exactly as it did before this existed.

**Validation happens here, at consumption**, which is the `style.volume`
precedent: the command that writes the entry only checks that the value
is a string. The difference from `read_volume` and `read_pulse` is that
those raise on nonsense (`float("abc")` is an error) and this one does
not — an unreadable mode falls back to light. That is deliberate. A
hand-edited file must not be able to produce a score nobody can see.
"""
from __future__ import annotations

from dataclasses import dataclass

from typing import Mapping

LIGHT = "light"
DARK = "dark"

# Light is the app's original look, and the pair a printed score has.
LIGHT_BACKGROUND = "#ffffff"
LIGHT_INK = "#000000"

# Dark is white notation on a dark blue-grey rather than on black:
# pure black is harsh under a white staff, and this is the tone the
# app's own dark chrome already uses (`ui/lane_style.BG`), so the page
# and the timeline below it belong to the same picture.
DARK_BACKGROUND = "#1d1f24"
DARK_INK = "#ffffff"

_MODES = {LIGHT: (LIGHT_BACKGROUND, LIGHT_INK),
          DARK: (DARK_BACKGROUND, DARK_INK)}


@dataclass(frozen=True)
class PageColors:
    """The two colours the mode resolves to, always a lowercase
    "#rrggbb" string — so a caller can hand either straight to QColor
    without checking anything."""
    mode: str = LIGHT
    background: str = LIGHT_BACKGROUND
    ink: str = LIGHT_INK

    @property
    def is_default(self) -> bool:
        """Nothing to apply: light is what a fresh scene is already
        built in, so the recolour pass can skip the sweep entirely."""
        return self.mode == LIGHT

    @property
    def is_dark(self) -> bool:
        return self.mode == DARK


def colors_for(mode: str) -> PageColors:
    """The pair a known mode resolves to. Unknown modes are the caller's
    problem — `read_colors` is the one that has to be forgiving."""
    background, ink = _MODES[mode]
    return PageColors(mode=mode, background=background, ink=ink)


def read_colors(raw: Mapping[str, object] | None) -> PageColors:
    """The document's sparse `style.colors` entry, made safe.

    Anything that is not a mode this build knows — a missing key, a
    number, a mode from a newer build — is light, which is the look
    every file written before this existed has always had."""
    mode = (raw or {}).get("mode")
    if isinstance(mode, str) and mode.strip().lower() in _MODES:
        return colors_for(mode.strip().lower())
    return colors_for(LIGHT)
