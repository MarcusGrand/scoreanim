"""How a selection LOOKS: the tint colors, as pure data.

Rule 13 — the way selection looks is transient render state, so it never
goes near the document. It lives here rather than in the Qt layer for
the usual reason (rule 1): the interesting decision is a small piece of
logic, and it should be testable headless.

Colors are "#rrggbb" strings; the render layer turns them into QColors.

THE CONSTANT TO CHANGE IS ``SELECTION_COLOR``.

The second color is not a style choice, it is a collision handler. A
user can give an element its own color (a part tint today, a per-element
override with M3), and if that authored color is already the selection
color then tinting changes nothing and the selection becomes invisible
on the object it names. So when the two are too close to tell apart, the
tint falls back to a color that cannot collide with a near-orange.

The threshold below is a JUDGMENT, not a measurement — there is no
experiment in this project that yields it. It was chosen off the
distance table in tests/test_selection_highlight.py, which is the honest
form of the argument: these pairs read as the same color, those do not.
"""

from __future__ import annotations

# The selection tint. One constant, one place.
SELECTION_COLOR = "#ff6a00"

# Used ONLY when the element's authored color is too close to
# SELECTION_COLOR to be told apart from it. Deliberately across the
# wheel from it, so it cannot in turn collide with the near-oranges that
# are the only colors that get here.
SELECTION_ALT_COLOR = "#0a84ff"

# Redmean distance below which two colors are treated as the same color.
# Range of the metric is 0 .. ~765. See the module docstring.
_COLLISION_DISTANCE = 120.0

# Opacity a selected element is held at or above, whatever the animation
# is doing to it. Not decoration: the document's ghost floor may be 0
# (an invisible ghost score), so without a floor of its own a selection
# on pre-trigger ink would be a tint nobody can see. A selected element
# therefore stops fully dimming — which is the intended reading, since
# it is the one element the user is currently pointing at.
SELECTION_MIN_OPACITY = 0.85


def selection_color_for(authored: str | None) -> str:
    """The tint to paint on an element whose authored color is
    ``authored`` (None = the default black ink)."""
    if authored is None:
        return SELECTION_COLOR
    if color_distance(authored, SELECTION_COLOR) < _COLLISION_DISTANCE:
        return SELECTION_ALT_COLOR
    return SELECTION_COLOR


def color_distance(a: str, b: str) -> float:
    """"Redmean" distance between two #rrggbb colors — the cheap
    low-cost approximation of perceived difference (it weights the
    channels by where the pair sits on the red axis, which plain
    Euclidean RGB does not). Boring and dependency-free; we need an
    ordering, not colorimetry."""
    r1, g1, b1 = _rgb(a)
    r2, g2, b2 = _rgb(b)
    rbar = (r1 + r2) / 2.0
    dr, dg, db = r1 - r2, g1 - g2, b1 - b2
    return ((2 + rbar / 256.0) * dr * dr
            + 4 * dg * dg
            + (2 + (255 - rbar) / 256.0) * db * db) ** 0.5


def _rgb(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    if len(text) == 3:                       # #rgb shorthand
        text = "".join(c * 2 for c in text)
    if len(text) != 6:
        raise ValueError(f"not a #rrggbb color: {value!r}")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
