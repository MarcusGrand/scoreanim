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
    widget._amplitude.commit()
    assert state.committed.style.effect_params["pop"]["scale"] == 2.0
    widget._amplitude.commit()                   # epsilon no-op
    widget._settle_spin.setValue(0.5)
    widget._settle.commit()
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
    widget._peak.commit()
    assert state.doc.style.effect_params["pop"]["peak_offset"] == \
        pytest.approx(-0.1)                      # seconds in the doc
    widget._peak.commit()                        # epsilon no-op
    state.undo()
    state.undo()
    assert not state.can_undo                    # two gestures, two steps


def test_fade_knobs_commit_fade_params(panel) -> None:
    widget, state = panel
    widget._fade_spin.setValue(1.5)
    widget._fade.commit()
    assert state.committed.style.effect_params["fade"]["duration"] == 1.5
    assert state.undo_text() == "set effect parameter"
    widget._fade.commit()                        # epsilon no-op
    widget._fade_note_value_box.setChecked(True)
    assert state.doc.style.effect_params["fade"]["note_value"] is True
    # fade's knobs are fade's own — pop is untouched
    assert "pop" not in state.doc.style.effect_params
    state.undo()
    state.undo()
    assert not state.can_undo                    # two gestures, two steps


def test_the_five_number_fields_preview_while_you_type(panel) -> None:
    """The stage shows the knob on every keystroke: the previewed
    document carries it while the committed one does not, and the whole
    typing session still lands as ONE undo entry."""
    widget, state = panel

    def pop(doc, key):
        return doc.style.effect_params.get("pop", {}).get(key)

    def fade(doc, key):
        return doc.style.effect_params.get("fade", {}).get(key)

    cases = ((widget._amplitude_spin, widget._amplitude, 2.5,
              lambda doc: pop(doc, "scale"), 2.5),
             (widget._settle_spin, widget._settle, 0.75,
              lambda doc: pop(doc, "settle"), 0.75),
             (widget._peak_spin, widget._peak, -100,      # ms in, s out
              lambda doc: pop(doc, "peak_offset"), pytest.approx(-0.1)),
             (widget._fade_spin, widget._fade, 1.25,
              lambda doc: fade(doc, "duration"), 1.25),
             (widget._floor_spin, widget._floor, 0.4,
              lambda doc: doc.style.floor_opacity, 0.4))
    for spin, field, typed, read, expected in cases:
        before = read(state.committed)
        spin.setValue(typed)                     # typing, box still focused
        assert read(state.doc) == expected       # the stage was told
        assert read(state.committed) == before   # nothing committed yet
        assert not state.can_undo

        field.commit()                           # Enter / click away
        assert read(state.committed) == expected
        assert state.can_undo
        state.undo()                             # exactly one entry each
        assert not state.can_undo
        widget.sync_from_document(state.doc)


def test_typing_a_knob_back_to_its_start_commits_nothing(panel) -> None:
    widget, state = panel
    start = state.doc.style.floor_opacity         # 0.3, the default
    widget._floor_spin.setValue(0.4)
    assert state.doc is not state.committed      # a preview is live
    widget._floor_spin.setValue(start)           # back where it started
    assert state.doc is state.committed          # preview dropped
    widget._floor.commit()
    assert not state.can_undo and not state.is_dirty


def test_a_resync_does_not_fight_a_live_knob(panel) -> None:
    """A preview emits document_changed, which comes straight back here
    as a resync — it must not rewrite the number under the cursor, and it
    must not gray the field out from under it either."""
    widget, state = panel
    widget._effect_combo.setCurrentText("pop")
    widget._commit_effect()

    widget._amplitude_spin.setValue(3.0)         # typing
    widget.sync_from_document(state.doc)         # what the window does
    assert widget._amplitude_spin.value() == 3.0
    assert widget._amplitude_spin.isEnabled()
    assert state.undo_text() == "set default effect"   # nothing new committed

    widget._amplitude.commit()
    assert state.committed.style.effect_params["pop"]["scale"] == 3.0
    state.undo()                                 # the edit is over
    widget.sync_from_document(state.doc)
    assert widget._amplitude_spin.value() == 1.25
    assert not widget._amplitude.previewing()


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
    widget._floor.commit()
    assert state.doc.style.floor_opacity == 0.25
    assert state.undo_text() == "set floor opacity"
    widget._floor.commit()                       # epsilon no-op
    widget._sweep_box.setChecked(True)
    assert state.doc.style.reveal_mode is RevealMode.CONTINUOUS
    assert state.undo_text() == "set reveal mode"
    state.undo()
    state.undo()
    assert not state.can_undo


def _shown(widget, *children) -> bool:
    """Would these controls be on screen if the panel were? The panel is
    never shown in the tests, so plain isVisible() says False for
    everything."""
    return all(child.isVisibleTo(widget) for child in children)


def _row_of(widget, child) -> int:
    """The form row a control sits on — found through its container when
    it shares the row with another control."""
    for candidate in (child, child.parentWidget()):
        row, _role = widget._form.getWidgetPosition(candidate)
        if row >= 0:
            return row
    raise AssertionError(f"{child} is not in the form")


def _label_of(widget, child) -> str:
    from PySide6.QtWidgets import QFormLayout
    item = widget._form.itemAt(_row_of(widget, child),
                               QFormLayout.ItemRole.LabelRole)
    return item.widget().text()


def test_pop_options_hide_until_pop_is_in_use(panel) -> None:
    """A preset's options only show while something resolves to it
    (Marcus, 2026-07-31): no default, no part/element rule — no pop
    block at all, heading and rows together."""
    widget, state = panel
    assert not _shown(widget, widget._amplitude_spin, widget._settle_spin,
                      widget._note_value_box, widget._peak_spin)
    widget._effect_combo.setCurrentText("pop")
    widget._commit_effect()
    assert _shown(widget, widget._amplitude_spin, widget._settle_spin,
                  widget._note_value_box, widget._peak_spin)
    assert not _shown(widget, widget._fade_spin)   # fade's turn to hide
    # the heading rides with its block
    from PySide6.QtWidgets import QFormLayout
    head_row = widget._rows_by_preset["pop"][0]
    head = widget._form.itemAt(head_row,
                               QFormLayout.ItemRole.SpanningRole).widget()
    assert head.text() == "Pop" and _shown(widget, head)
    # a PART rule alone also brings the block back (params apply to it)
    from scoreanim.core.project import SetPartEffect
    from scoreanim.core.score.identity import PartId
    state.undo()
    widget.sync_from_document(state.doc)
    assert not _shown(widget, widget._amplitude_spin, head)
    state.execute(SetPartEffect(PartId("P1"), "pop"))
    widget.sync_from_document(state.doc)
    assert _shown(widget, widget._amplitude_spin, head)


def test_two_effects_in_use_show_both_blocks(panel) -> None:
    """Two named blocks, so two rows called Duration never read as one
    effect's pair of knobs."""
    from scoreanim.core.project import SetPartEffect
    from scoreanim.core.score.identity import PartId
    widget, state = panel
    widget._effect_combo.setCurrentText("fade")
    widget._commit_effect()
    state.execute(SetPartEffect(PartId("P1"), "pop"))
    widget.sync_from_document(state.doc)
    assert _shown(widget, widget._fade_spin, widget._amplitude_spin)
    assert _row_of(widget, widget._settle_spin) != \
        _row_of(widget, widget._fade_spin)


def test_duration_terminology_and_row_pairing(panel) -> None:
    """Both effects call it Duration, and 'Entire note value' sits on
    that very row — the alternative to typing a number, not a separate
    option floating below it."""
    widget, _ = panel
    for spin, box in ((widget._settle_spin, widget._note_value_box),
                      (widget._fade_spin, widget._fade_note_value_box)):
        assert _label_of(widget, spin) == "Duration"
        assert _row_of(widget, spin) == _row_of(widget, box)
        assert box.text() == "Entire note value"


def test_pop_duration_grays_while_note_value_is_on(panel) -> None:
    widget, state = panel
    widget._effect_combo.setCurrentText("pop")
    widget._commit_effect()
    assert widget._settle_spin.isEnabled()
    widget._note_value_box.setChecked(True)      # commits + regrays
    assert not widget._settle_spin.isEnabled()
    assert widget._amplitude_spin.isEnabled()    # only Duration is obsolete
    assert widget._peak_spin.isEnabled()
    widget._note_value_box.setChecked(False)
    assert widget._settle_spin.isEnabled()
    # the resync path drives the same state
    state.execute(SetEffectParam("pop", "note_value", True))
    widget.sync_from_document(state.doc)
    assert not widget._settle_spin.isEnabled()


def test_fade_options_hide_until_fade_is_in_use(panel) -> None:
    """The same ruling one preset over: pop being in use does not bring
    fade's block on screen."""
    widget, state = panel
    assert not _shown(widget, widget._fade_spin, widget._fade_note_value_box)
    widget._effect_combo.setCurrentText("pop")
    widget._commit_effect()
    assert not _shown(widget, widget._fade_spin)
    widget._effect_combo.setCurrentText("fade")
    widget._commit_effect()
    assert _shown(widget, widget._fade_spin, widget._fade_note_value_box)
    assert not _shown(widget, widget._amplitude_spin)
    # a PART rule alone also brings the block back
    from scoreanim.core.project import SetPartEffect
    from scoreanim.core.score.identity import PartId
    state.undo()
    state.undo()
    widget.sync_from_document(state.doc)
    assert not _shown(widget, widget._fade_spin)
    state.execute(SetPartEffect(PartId("P1"), "fade"))
    widget.sync_from_document(state.doc)
    assert _shown(widget, widget._fade_spin)


def test_a_live_field_is_never_hidden_from_under_the_cursor(panel) -> None:
    """Hiding drops focus, and focus-out commits — the trap set_enabled
    already avoids. Nothing a knob itself types can change which effect
    is in use, so this is a guard rather than a daily path; it is asked
    directly here. Once the edit ends, the hide lands."""
    widget, state = panel
    widget._effect_combo.setCurrentText("fade")
    widget._commit_effect()
    widget._fade_spin.setValue(1.5)              # typing
    assert widget._fade.previewing()
    widget._set_group_visible("fade", False)     # refused mid-edit
    assert _shown(widget, widget._fade_spin)
    widget._fade.commit()                        # Enter / click away
    widget._set_group_visible("fade", False)
    assert not _shown(widget, widget._fade_spin)


def test_fade_time_grays_while_fade_note_value_is_on(panel) -> None:
    widget, state = panel
    widget._effect_combo.setCurrentText("fade")
    widget._commit_effect()
    assert widget._fade_spin.isEnabled()
    widget._fade_note_value_box.setChecked(True)     # commits + regrays
    assert not widget._fade_spin.isEnabled()
    assert widget._fade_note_value_box.isEnabled()   # only the time is obsolete
    widget._fade_note_value_box.setChecked(False)
    assert widget._fade_spin.isEnabled()
    # pop's note-value is not fade's: it grays pop's Duration only
    state.execute(SetEffectParam("pop", "note_value", True))
    widget.sync_from_document(state.doc)
    assert widget._fade_spin.isEnabled()
    # the resync path drives the same state
    state.execute(SetEffectParam("fade", "note_value", True))
    widget.sync_from_document(state.doc)
    assert not widget._fade_spin.isEnabled()


def test_sync_reflects_fade_params(panel) -> None:
    widget, state = panel
    for cmd in (SetEffectParam("fade", "duration", 2.0),
                SetEffectParam("fade", "note_value", True)):
        state.execute(cmd)
    widget.sync_from_document(state.doc)
    assert widget._fade_spin.value() == 2.0
    assert widget._fade_note_value_box.isChecked()
    depth = 0
    while state.can_undo:
        state.undo()
        depth += 1
    assert depth == 2                            # resync added nothing
    widget.sync_from_document(state.doc)         # back to the default
    assert widget._fade_spin.value() == 0.4
    assert not widget._fade_note_value_box.isChecked()


def test_reset_clears_pop_and_fade_together(panel) -> None:
    """One Reset really resets what the panel shows: both presets'
    params go, in ONE undo step."""
    widget, state = panel
    widget._effect_combo.setCurrentText("fade")
    widget._commit_effect()
    widget._fade_spin.setValue(1.5)
    widget._fade.commit()
    state.execute(SetEffectParam("pop", "scale", 2.0))
    assert widget._reset_button.isEnabled()
    before = state.doc
    widget._commit_reset()
    assert state.doc.style.default_effect is None
    assert state.doc.style.effect_params == {}
    assert widget._fade_spin.value() == 0.4
    assert not widget._reset_button.isEnabled()
    state.undo()                                 # ONE step restores both
    assert state.doc == before


def test_fade_params_alone_light_the_reset_button(panel) -> None:
    widget, state = panel
    assert not widget._reset_button.isEnabled()
    state.execute(SetEffectParam("fade", "duration", 1.0))
    widget.sync_from_document(state.doc)
    assert widget._reset_button.isEnabled()


def test_reset_restores_pre_m4_defaults_in_one_step(panel) -> None:
    widget, state = panel
    assert not widget._reset_button.isEnabled()  # already at defaults
    widget._commit_reset()
    assert not state.can_undo                    # no-op ran no command
    widget._effect_combo.setCurrentText("pop")
    widget._commit_effect()
    widget._amplitude_spin.setValue(2.0)
    widget._amplitude.commit()
    widget._note_value_box.setChecked(True)
    widget._peak_spin.setValue(-100)
    widget._peak.commit()
    assert widget._reset_button.isEnabled()
    depth_before = 4
    widget._commit_reset()
    # the doc is back at the pre-M4 defaults and the panel shows them
    assert state.doc.style.default_effect is None
    assert state.doc.style.effect_params == {}
    assert widget._effect_combo.currentText() == DEFAULT_EFFECT
    assert widget._amplitude_spin.value() == 1.25
    assert not widget._note_value_box.isChecked()
    assert widget._peak_spin.value() == 0
    assert not widget._reset_button.isEnabled()
    assert state.undo_text() == "reset effect settings"
    state.undo()                                 # ONE step restores all
    assert state.doc.style.default_effect == "pop"
    assert state.doc.style.effect_params["pop"]["scale"] == 2.0
    depth = 0
    while state.can_undo:
        state.undo()
        depth += 1
    assert depth == depth_before


def test_five_knob_undo_walk(panel) -> None:
    """The §4 exit shape: default effect, amplitude, settle, note-value,
    peak offset — five gestures, five individual undo steps."""
    widget, state = panel
    widget._effect_combo.setCurrentText("pop")
    widget._commit_effect()
    widget._amplitude_spin.setValue(2.0)
    widget._amplitude.commit()
    widget._settle_spin.setValue(0.5)
    widget._settle.commit()
    widget._note_value_box.setChecked(True)
    widget._peak_spin.setValue(-100)
    widget._peak.commit()
    for _ in range(5):
        assert state.can_undo
        state.undo()
    assert not state.can_undo
    assert state.doc.style.default_effect is None
    assert state.doc.style.effect_params == {}
