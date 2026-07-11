from __future__ import annotations

import pytest

from scoreanim.core.timing import Clock, ManualClock


def test_clock_is_abstract() -> None:
    with pytest.raises(TypeError):
        Clock()  # type: ignore[abstract]


def test_manual_clock_set_and_read() -> None:
    c = ManualClock()
    assert c.now_seconds() == 0.0
    c.set(12.25)
    assert c.now_seconds() == 12.25
    assert isinstance(c, Clock)
