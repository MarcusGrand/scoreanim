"""The ink that never runs an effect: it just appears.

A clef, a key signature and a time signature are not musical events.
Nothing happens on the beat they are drawn on — they are there to be
read, not to be heard. So a key signature that fades in, or a time
signature that slides into place, tells the eye that something happened
where nothing did (Marcus, 2026-08-31).

These kinds therefore ignore whatever effect the document, the part or
an element override asks for, and always run the plain "appear" preset:
the step from the floor opacity to full at their trigger. No ramp, no
pop, no drop, no slide, no swell. They are already dark — the glow has
its own allowlist next door (`glow_scope.GLOWING_KINDS`), and no
signature is on it.

THIS SET IS THE WHOLE SWITCH. Nothing downstream branches on a kind or
on an effect's name: the render layer runs the resolved name through
`effect_name_for` and uses whatever comes back (rule 6 — effects stay
data). If clefs should animate again, taking CLEF out of `PLAIN_KINDS`
is the entire edit.
"""
from __future__ import annotations

from scoreanim.core.animation.presets import DEFAULT_EFFECT
from scoreanim.core.animation.schedule import SIG_KINDS
from scoreanim.core.score.identity import ElementIdentity

# The bar-level glyphs, borrowed from the schedule rather than re-listed
# so the two sets cannot drift apart: clef, key signature, meter
# signature.
PLAIN_KINDS = SIG_KINDS


def effect_name_for(identity: ElementIdentity | None,
                    resolved_name: str | None) -> str | None:
    """The effect name this element really runs.

    A plain kind gets the appear preset whatever was asked for.
    Everything else — and an item with no identity at all, which is
    stage furniture — is passed through untouched.
    """
    if identity is not None and identity.kind in PLAIN_KINDS:
        return DEFAULT_EFFECT
    return resolved_name
