"""A clef, a key signature and a time signature never run an effect.

The policy set is the whole switch (core/animation/plain_kinds.py), so
these tests are about the two things it promises: every signature kind
comes back as the plain appear preset whatever was asked for, and
nothing else is touched.
"""

import pytest

from scoreanim.core.animation import DEFAULT_EFFECT
from scoreanim.core.animation.plain_kinds import PLAIN_KINDS, effect_name_for
from scoreanim.core.animation.schedule import SIG_KINDS
from scoreanim.core.score.identity import ElementIdentity, ElementKind

# Everything a document, a part rule or an element override can ask for.
ASKED = ["fade", "pop", "drop+fade", "slide", "swell", "glow"]

# Kinds that must come through untouched: real musical events and the
# ink that belongs to a bar rather than to a beat.
PASS_THROUGH = [ElementKind.NOTEHEAD, ElementKind.REST, ElementKind.DYNAMIC,
                ElementKind.TEXT, ElementKind.SLASH, ElementKind.ACCIDENTAL]


def _identity(kind: ElementKind) -> ElementIdentity:
    return ElementIdentity(element_id=f"p1:m1:{kind.name.lower()}",
                           kind=kind, part="p1", part_name="Flute",
                           staff=1, voice=1, onset=0.0)


def test_the_set_is_the_schedule_s_signature_kinds() -> None:
    """Borrowed, not re-listed, so the two cannot drift apart."""
    assert PLAIN_KINDS is SIG_KINDS
    assert PLAIN_KINDS == {ElementKind.CLEF, ElementKind.KEY_SIG,
                           ElementKind.METER_SIG}


@pytest.mark.parametrize("kind", sorted(SIG_KINDS, key=lambda k: k.name))
@pytest.mark.parametrize("asked", ASKED)
def test_every_signature_kind_just_appears(kind, asked) -> None:
    assert effect_name_for(_identity(kind), asked) == DEFAULT_EFFECT


@pytest.mark.parametrize("kind", PASS_THROUGH)
@pytest.mark.parametrize("asked", ASKED)
def test_everything_else_passes_through(kind, asked) -> None:
    assert effect_name_for(_identity(kind), asked) == asked


def test_no_name_passes_through() -> None:
    """None means "nothing resolved" and stays that way for ordinary
    ink; a signature still lands on the appear preset."""
    assert effect_name_for(_identity(ElementKind.NOTEHEAD), None) is None
    assert effect_name_for(_identity(ElementKind.KEY_SIG),
                           None) == DEFAULT_EFFECT


def test_no_identity_passes_through() -> None:
    """Stage furniture carries no identity at all."""
    assert effect_name_for(None, "fade") == "fade"
    assert effect_name_for(None, None) is None
