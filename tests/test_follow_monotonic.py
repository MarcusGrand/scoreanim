"""View-follow is monotonic non-decreasing over forward time: current_page()
/current_system() must never turn backward while the clock advances, even when
a single trigger's page/system dips (schedule.py aggregates each beat bucket
with min(), and tie/rest/group retiming + sub-beat bucket-merging across a
system break can produce N, N-1, N). A genuine backward seek still resets."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import StyleRules  # noqa: E402
from scoreanim.core.animation.schedule import (Trigger,  # noqa: E402
                                               TriggerSchedule)
from scoreanim.core.timing import TempoEvent, TempoMap  # noqa: E402
from scoreanim.render.animate import AnimationApplier  # noqa: E402

TEMPO = TempoMap([TempoEvent(0.0, 60.0)])   # 1 beat = 1 second


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _schedule(seq: list[tuple[int, int]]) -> TriggerSchedule:
    """seq is [(page, system), ...] on beats 1,2,3,..., one trigger each."""
    triggers = tuple(
        Trigger(beats=float(i + 1), page=page, element_ids=(), system=system)
        for i, (page, system) in enumerate(seq))
    beat_values = tuple(float(i + 1) for i in range(len(seq)))
    return TriggerSchedule(triggers=triggers, beat_values=beat_values,
                           beats_by_element={})


def test_dipping_system_never_turns_backward(qapp) -> None:
    # systems dip: 1, 2, 1, 2, 3 — a retimed foreign element pulled system 1
    # into the third bucket. Follow must read 1, 2, 2, 2, 3 (never back to 1).
    seq = [(1, 1), (1, 2), (1, 1), (2, 2), (2, 3)]
    applier = AnimationApplier({}, _schedule(seq), TEMPO, StyleRules())

    seen_sys: list[int] = []
    seen_page: list[int] = []
    for t in [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]:   # sweep forward past each beat
        applier.apply_at(t)
        seen_sys.append(applier.current_system())
        seen_page.append(applier.current_page())

    assert seen_sys == sorted(seen_sys), f"system turned backward: {seen_sys}"
    assert seen_page == sorted(seen_page), f"page turned backward: {seen_page}"
    # final state reaches the true maximum
    assert applier.current_system() == 3
    assert applier.current_page() == 2


def test_backward_seek_resets_to_earlier_value(qapp) -> None:
    seq = [(1, 1), (1, 2), (2, 3)]
    applier = AnimationApplier({}, _schedule(seq), TEMPO, StyleRules())

    applier.apply_at(3.5)                 # past all triggers
    assert applier.current_system() == 3
    applier.refresh(0.5)                  # seek back before everything
    assert applier.current_system() == 1  # resets, does not stay at 3
    applier.refresh(2.5)                  # seek so two triggers are crossed
    assert applier.current_system() == 2
