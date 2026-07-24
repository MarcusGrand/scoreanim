"""Effects panel (M4.8), offscreen: each control commits exactly one
command per user gesture with the right payload, resync never
re-executes (undo-stack depth unchanged), the Peak-offset tooltip
states the early-visibility consequence, and the Floor/Sweep controls
that moved in keep their inspector-era behavior verbatim.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import DEFAULT_EFFECT, RevealMode  # noqa: E402
from scoreanim.core.project import SetEffectParam  # noqa: E402
from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.panels import EffectsPanel  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp):
    state = AppState()
    return EffectsPanel(state), state


def test_effect_dropdown_commits_default_effect(panel) -> None:
    widget, state = panel
    assert widget._effect_combo.currentText() == DEFAULT_EFFECT
    widget._effect_combo.setCurrentText("pop")
    widget._commit_effect()
    assert state.doc.style.default_effect == "pop"
    assert state.undo_text() == "set default effect"
    widget._commit_effect()                      # same value → no-op
    state.undo()
    assert not state.can_undo                    # exactly one command
    assert state.doc.style.default_effect is None
    widget.sync_from_document(state.doc)
    assert widget._effect_combo.currentText() == DEFAULT_EFFECT


def test_amplitude_and_settle_commit_pop_params(panel) -> None:
    widget, state = panel
    widget._amplitude_spin.setValue(2.0)
    widget._commit_amplitude()
    assert state.doc.style.effect_params["pop"]["scale"] == 2.0
    widget._commit_amplitude()                   # epsilon no-op
    widget._settle_spin.setValue(0.5)
    widget._commit_settle()
    assert state.doc.style.effect_params["pop"]["settle"] == 0.5
    assert state.undo_text() == "set effect parameter"
    state.undo()
    assert "settle" not in state.doc.style.effect_params["pop"]
    state.undo()
    assert not state.can_undo                    # two gestures, two steps


def test_note_value_and_peak_offset_commit(panel) -> None:
    widget, state = panel
    widget._note_value_box.setChecked(True)
    assert state.doc.style.effect_params["pop"]["note_value"] is True
    widget._peak_spin.setValue(-100)             # ms in the UI
    widget._commit_peak()
    assert state.doc.style.effect_params["pop"]["peak_offset"] == \
        pytest.approx(-0.1)                      # seconds in the doc
    widget._commit_peak()                        # epsilon no-op
    state.undo()
    state.undo()
    assert not state.can_undo                    # two gestures, two steps


def test_peak_offset_tooltip_states_early_visibility(panel) -> None:
    widget, _ = panel
    tip = widget._peak_spin.toolTip()
    assert "including when the note appears" in tip


def test_sync_reflects_document_and_never_reexecutes(panel) -> None:
    widget, state = panel
    for cmd in (SetEffectParam("pop", "scale", 3.0),
                SetEffectParam("pop", "settle", 1.0),
                SetEffectParam("pop", "note_value", True),
                SetEffectParam("pop", "peak_offset", 0.25)):
        state.execute(cmd)
    widget.sync_from_document(state.doc)
    assert widget._amplitude_spin.value() == 3.0
    assert widget._settle_spin.value() == 1.0
    assert widget._note_value_box.isChecked()
    assert widget._peak_spin.value() == 250      # seconds → ms
    depth = 0
    while state.can_undo:
        state.undo()
        depth += 1
    assert depth == 4                            # resync added nothing
    widget.sync_from_document(state.doc)         # back to defaults
    assert widget._amplitude_spin.value() == 1.25
    assert widget._settle_spin.value() == 0.25
    assert not widget._note_value_box.isChecked()
    assert widget._peak_spin.value() == 0
    assert not state.can_undo


def test_unknown_stored_effect_name_is_displayed(panel) -> None:
    """A default_effect from a newer build shows as itself (the stored
    intent) instead of silently displaying the wrong preset."""
    from scoreanim.core.project import SetDefaultEffect
    widget, state = panel
    state.execute(SetDefaultEffect("shimmer"))
    widget.sync_from_document(state.doc)
    assert widget._effect_combo.currentText() == "shimmer"


def test_floor_and_sweep_moved_in_verbatim(panel) -> None:
    widget, state = panel
    widget._floor_spin.setValue(0.25)
    widget._commit_floor()
    assert state.doc.style.floor_opacity == 0.25
    assert state.undo_text() == "set floor opacity"
    widget._commit_floor()                       # epsilon no-op
    widget._sweep_box.setChecked(True)
    assert state.doc.style.reveal_mode is RevealMode.CONTINUOUS
    assert state.undo_text() == "set reveal mode"
    state.undo()
    state.undo()
    assert not state.can_undo


def test_five_knob_undo_walk(panel) -> None:
    """The §4 exit shape: default effect, amplitude, settle, note-value,
    peak offset — five gestures, five individual undo steps."""
    widget, state = panel
    widget._effect_combo.setCurrentText("pop")
    widget._commit_effect()
    widget._amplitude_spin.setValue(2.0)
    widget._commit_amplitude()
    widget._settle_spin.setValue(0.5)
    widget._commit_settle()
    widget._note_value_box.setChecked(True)
    widget._peak_spin.setValue(-100)
    widget._commit_peak()
    for _ in range(5):
        assert state.can_undo
        state.undo()
    assert not state.can_undo
    assert state.doc.style.default_effect is None
    assert state.doc.style.effect_params == {}
