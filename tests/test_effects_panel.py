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
from scoreanim.core.project import (SetDefaultEffect,  # noqa: E402
                                    SetEffectParam, SetPulseParam,
                                    SetVolumeParam)
from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.panels import EffectsPanel  # noqa: E402
from scoreanim.ui.panels.effect_blocks import BLOCKS  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp):
    state = AppState()
    return EffectsPanel(state), state


# Each preset's knobs live in its own block, keyed by the param they
# edit (ui/panels/effect_knobs.py) — these three just say it shorter.

def spin(widget, preset, key):
    return widget.blocks[preset].spins[key]


def box(widget, preset, key):
    return widget.blocks[preset].boxes[key]


def field(widget, preset, key):
    return widget.blocks[preset].fields[key]


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
    spin(widget, "pop", "scale").setValue(2.0)
    field(widget, "pop", "scale").commit()
    assert state.committed.style.effect_params["pop"]["scale"] == 2.0
    field(widget, "pop", "scale").commit()                   # epsilon no-op
    spin(widget, "pop", "settle").setValue(0.5)
    field(widget, "pop", "settle").commit()
    assert state.doc.style.effect_params["pop"]["settle"] == 0.5
    assert state.undo_text() == "set effect parameter"
    state.undo()
    assert "settle" not in state.doc.style.effect_params["pop"]
    state.undo()
    assert not state.can_undo                    # two gestures, two steps


def test_note_value_and_peak_offset_commit(panel) -> None:
    widget, state = panel
    box(widget, "pop", "note_value").setChecked(True)
    assert state.doc.style.effect_params["pop"]["note_value"] is True
    spin(widget, "pop", "peak_offset").setValue(-100)    # ms in the UI
    field(widget, "pop", "peak_offset").commit()
    assert state.doc.style.effect_params["pop"]["peak_offset"] == \
        pytest.approx(-0.1)                      # seconds in the doc
    field(widget, "pop", "peak_offset").commit()         # epsilon no-op
    state.undo()
    state.undo()
    assert not state.can_undo                    # two gestures, two steps


def test_fade_knobs_commit_fade_params(panel) -> None:
    widget, state = panel
    spin(widget, "fade", "duration").setValue(1.5)
    field(widget, "fade", "duration").commit()
    assert state.committed.style.effect_params["fade"]["duration"] == 1.5
    assert state.undo_text() == "set effect parameter"
    field(widget, "fade", "duration").commit()           # epsilon no-op
    box(widget, "fade", "note_value").setChecked(True)
    assert state.doc.style.effect_params["fade"]["note_value"] is True
    # fade's knobs are fade's own — pop is untouched
    assert "pop" not in state.doc.style.effect_params
    state.undo()
    state.undo()
    assert not state.can_undo                    # two gestures, two steps


def test_every_number_field_previews_while_you_type(panel) -> None:
    """The stage shows the knob on every keystroke: the previewed
    document carries it while the committed one does not, and the whole
    typing session still lands as ONE undo entry."""
    widget, state = panel

    def pop(doc, key):
        return doc.style.effect_params.get("pop", {}).get(key)

    def fade(doc, key):
        return doc.style.effect_params.get("fade", {}).get(key)

    def drop(doc, key):
        return doc.style.effect_params.get("drop", {}).get(key)

    def slide(doc, key):
        return doc.style.effect_params.get("slide", {}).get(key)

    def swell(doc, key):
        return doc.style.effect_params.get("swell", {}).get(key)

    cases =((spin(widget, "pop", "scale"),
              field(widget, "pop", "scale"), 2.5,
              lambda doc: pop(doc, "scale"), 2.5),
             (spin(widget, "pop", "settle"),
              field(widget, "pop", "settle"), 0.75,
              lambda doc: pop(doc, "settle"), 0.75),
             (spin(widget, "pop", "peak_offset"),          # ms in, s out
              field(widget, "pop", "peak_offset"), -100,
              lambda doc: pop(doc, "peak_offset"), pytest.approx(-0.1)),
             (spin(widget, "fade", "duration"),
              field(widget, "fade", "duration"), 1.25,
              lambda doc: fade(doc, "duration"), 1.25),
             (spin(widget, "drop", "start_size"),
              field(widget, "drop", "start_size"), 5.0,
              lambda doc: drop(doc, "start_size"), 5.0),
             (spin(widget, "drop", "duration"),
              field(widget, "drop", "duration"), 1.0,
              lambda doc: drop(doc, "duration"), 1.0),
             (spin(widget, "slide", "direction"),
              field(widget, "slide", "direction"), 180,
              lambda doc: slide(doc, "direction"), 180),
             (spin(widget, "slide", "distance"),
              field(widget, "slide", "distance"), 450.0,
              lambda doc: slide(doc, "distance"), 450.0),
             (spin(widget, "slide", "duration"),
              field(widget, "slide", "duration"), 0.8,
              lambda doc: slide(doc, "duration"), 0.8),
             (spin(widget, "swell", "size"),
              field(widget, "swell", "size"), 2.0,
              lambda doc: swell(doc, "size"), 2.0),
             (spin(widget, "swell", "peak"),               # % in, fraction out
              field(widget, "swell", "peak"), 75,
              lambda doc: swell(doc, "peak"), pytest.approx(0.75)),
             (spin(widget, "swell", "duration"),
              field(widget, "swell", "duration"), 1.75,
              lambda doc: swell(doc, "duration"), 1.75),
             (widget.volume.spins["amount"],
              widget.volume.fields["amount"], 0.7,
              lambda doc: doc.style.volume.get("amount"), 0.7),
             (widget.volume.spins["loud"],
              widget.volume.fields["loud"], 2.5,
              lambda doc: doc.style.volume.get("loud"), 2.5),
             # per cent in the box, a fraction in the document
             (widget.pulse.spins["amount"],
              widget.pulse.fields["amount"], 8,
              lambda doc: doc.style.pulse.get("amount"), 0.08),
             (widget._floor_spin, widget._floor, 0.4,
              lambda doc: doc.style.floor_opacity, 0.4))
    for knob, live, typed, read, expected in cases:
        before = read(state.committed)
        knob.setValue(typed)                     # typing, box still focused
        assert read(state.doc) == expected       # the stage was told
        assert read(state.committed) == before   # nothing committed yet
        assert not state.can_undo

        live.commit()                            # Enter / click away
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

    spin(widget, "pop", "scale").setValue(3.0)         # typing
    widget.sync_from_document(state.doc)         # what the window does
    assert spin(widget, "pop", "scale").value() == 3.0
    assert spin(widget, "pop", "scale").isEnabled()
    assert state.undo_text() == "set default effect"   # nothing new committed

    field(widget, "pop", "scale").commit()
    assert state.committed.style.effect_params["pop"]["scale"] == 3.0
    state.undo()                                 # the edit is over
    widget.sync_from_document(state.doc)
    assert spin(widget, "pop", "scale").value() == 1.25
    assert not field(widget, "pop", "scale").previewing()


def test_peak_offset_tooltip_states_early_visibility(panel) -> None:
    widget, _ = panel
    tip = spin(widget, "pop", "peak_offset").toolTip()
    assert "including when the note appears" in tip


def test_sync_reflects_document_and_never_reexecutes(panel) -> None:
    widget, state = panel
    for cmd in (SetEffectParam("pop", "scale", 3.0),
                SetEffectParam("pop", "settle", 1.0),
                SetEffectParam("pop", "note_value", True),
                SetEffectParam("pop", "peak_offset", 0.25)):
        state.execute(cmd)
    widget.sync_from_document(state.doc)
    assert spin(widget, "pop", "scale").value() == 3.0
    assert spin(widget, "pop", "settle").value() == 1.0
    assert box(widget, "pop", "note_value").isChecked()
    assert spin(widget, "pop", "peak_offset").value() == 250   # seconds → ms
    depth = 0
    while state.can_undo:
        state.undo()
        depth += 1
    assert depth == 4                            # resync added nothing
    widget.sync_from_document(state.doc)         # back to defaults
    assert spin(widget, "pop", "scale").value() == 1.25
    assert spin(widget, "pop", "settle").value() == 0.25
    assert not box(widget, "pop", "note_value").isChecked()
    assert spin(widget, "pop", "peak_offset").value() == 0
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
    knobs = (spin(widget, "pop", "scale"), spin(widget, "pop", "settle"),
             box(widget, "pop", "note_value"),
             spin(widget, "pop", "peak_offset"))
    assert not _shown(widget, *knobs)
    widget._effect_combo.setCurrentText("pop")
    widget._commit_effect()
    assert _shown(widget, *knobs)
    assert not _shown(widget,
                      spin(widget, "fade", "duration"))   # fade's turn
    # the heading rides with its block
    from PySide6.QtWidgets import QFormLayout
    head_row = widget.blocks["pop"].rows[0]
    head = widget._form.itemAt(head_row,
                               QFormLayout.ItemRole.SpanningRole).widget()
    assert head.text() == "Pop" and _shown(widget, head)
    # a PART rule alone also brings the block back (params apply to it)
    from scoreanim.core.project import SetPartEffect
    from scoreanim.core.score.identity import PartId
    state.undo()
    widget.sync_from_document(state.doc)
    assert not _shown(widget, spin(widget, "pop", "scale"), head)
    state.execute(SetPartEffect(PartId("P1"), "pop"))
    widget.sync_from_document(state.doc)
    assert _shown(widget, spin(widget, "pop", "scale"), head)


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
    assert _shown(widget, spin(widget, "fade", "duration"),
                  spin(widget, "pop", "scale"))
    assert _row_of(widget, spin(widget, "pop", "settle")) != \
        _row_of(widget, spin(widget, "fade", "duration"))


def test_duration_terminology_and_row_pairing(panel) -> None:
    """Both effects call it Duration, and 'Entire note value' sits on
    that very row — the alternative to typing a number, not a separate
    option floating below it."""
    widget, _ = panel
    for knob, check in ((spin(widget, "pop", "settle"),
                         box(widget, "pop", "note_value")),
                        (spin(widget, "fade", "duration"),
                         box(widget, "fade", "note_value"))):
        assert _label_of(widget, knob) == "Duration"
        assert _row_of(widget, knob) == _row_of(widget, check)
        assert check.text() == "Entire note value"


def test_pop_duration_grays_while_note_value_is_on(panel) -> None:
    widget, state = panel
    widget._effect_combo.setCurrentText("pop")
    widget._commit_effect()
    assert spin(widget, "pop", "settle").isEnabled()
    box(widget, "pop", "note_value").setChecked(True)      # commits + regrays
    assert not spin(widget, "pop", "settle").isEnabled()
    assert spin(widget, "pop", "scale").isEnabled()   # only Duration goes
    assert spin(widget, "pop", "peak_offset").isEnabled()
    box(widget, "pop", "note_value").setChecked(False)
    assert spin(widget, "pop", "settle").isEnabled()
    # the resync path drives the same state
    state.execute(SetEffectParam("pop", "note_value", True))
    widget.sync_from_document(state.doc)
    assert not spin(widget, "pop", "settle").isEnabled()


def test_fade_options_hide_until_fade_is_in_use(panel) -> None:
    """The same ruling one preset over: pop being in use does not bring
    fade's block on screen."""
    widget, state = panel
    assert not _shown(widget, spin(widget, "fade", "duration"),
                      box(widget, "fade", "note_value"))
    widget._effect_combo.setCurrentText("pop")
    widget._commit_effect()
    assert not _shown(widget, spin(widget, "fade", "duration"))
    widget._effect_combo.setCurrentText("fade")
    widget._commit_effect()
    assert _shown(widget, spin(widget, "fade", "duration"),
                  box(widget, "fade", "note_value"))
    assert not _shown(widget, spin(widget, "pop", "scale"))
    # a PART rule alone also brings the block back
    from scoreanim.core.project import SetPartEffect
    from scoreanim.core.score.identity import PartId
    state.undo()
    state.undo()
    widget.sync_from_document(state.doc)
    assert not _shown(widget, spin(widget, "fade", "duration"))
    state.execute(SetPartEffect(PartId("P1"), "fade"))
    widget.sync_from_document(state.doc)
    assert _shown(widget, spin(widget, "fade", "duration"))


def test_a_live_field_is_never_hidden_from_under_the_cursor(panel) -> None:
    """Hiding drops focus, and focus-out commits — the trap set_enabled
    already avoids. Nothing a knob itself types can change which effect
    is in use, so this is a guard rather than a daily path; it is asked
    directly here. Once the edit ends, the hide lands."""
    widget, state = panel
    widget._effect_combo.setCurrentText("fade")
    widget._commit_effect()
    spin(widget, "fade", "duration").setValue(1.5)              # typing
    assert field(widget, "fade", "duration").previewing()
    widget.blocks["fade"].set_visible(widget._form, False)   # refused
    assert _shown(widget, spin(widget, "fade", "duration"))
    field(widget, "fade", "duration").commit()       # Enter / click away
    widget.blocks["fade"].set_visible(widget._form, False)
    assert not _shown(widget, spin(widget, "fade", "duration"))


def test_fade_time_grays_while_fade_note_value_is_on(panel) -> None:
    widget, state = panel
    widget._effect_combo.setCurrentText("fade")
    widget._commit_effect()
    assert spin(widget, "fade", "duration").isEnabled()
    box(widget, "fade", "note_value").setChecked(True)     # commits + regrays
    assert not spin(widget, "fade", "duration").isEnabled()
    assert box(widget, "fade", "note_value").isEnabled()   # only the time
    box(widget, "fade", "note_value").setChecked(False)
    assert spin(widget, "fade", "duration").isEnabled()
    # pop's note-value is not fade's: it grays pop's Duration only
    state.execute(SetEffectParam("pop", "note_value", True))
    widget.sync_from_document(state.doc)
    assert spin(widget, "fade", "duration").isEnabled()
    # the resync path drives the same state
    state.execute(SetEffectParam("fade", "note_value", True))
    widget.sync_from_document(state.doc)
    assert not spin(widget, "fade", "duration").isEnabled()


def test_sync_reflects_fade_params(panel) -> None:
    widget, state = panel
    for cmd in (SetEffectParam("fade", "duration", 2.0),
                SetEffectParam("fade", "note_value", True)):
        state.execute(cmd)
    widget.sync_from_document(state.doc)
    assert spin(widget, "fade", "duration").value() == 2.0
    assert box(widget, "fade", "note_value").isChecked()
    depth = 0
    while state.can_undo:
        state.undo()
        depth += 1
    assert depth == 2                            # resync added nothing
    widget.sync_from_document(state.doc)         # back to the default
    assert spin(widget, "fade", "duration").value() == 0.4
    assert not box(widget, "fade", "note_value").isChecked()


def test_drop_knobs_commit_drop_params(panel) -> None:
    widget, state = panel
    spin(widget, "drop", "start_size").setValue(5.0)
    field(widget, "drop", "start_size").commit()
    assert state.committed.style.effect_params["drop"]["start_size"] == 5.0
    field(widget, "drop", "start_size").commit()         # epsilon no-op
    spin(widget, "drop", "duration").setValue(1.0)
    field(widget, "drop", "duration").commit()
    assert state.doc.style.effect_params["drop"]["duration"] == 1.0
    assert state.undo_text() == "set effect parameter"
    # bounce starts ON, so unchecking is what writes a param
    assert box(widget, "drop", "bounce").isChecked()
    box(widget, "drop", "bounce").setChecked(False)
    assert state.doc.style.effect_params["drop"]["bounce"] is False
    # drop's knobs are drop's own
    assert set(state.doc.style.effect_params) == {"drop"}
    for _ in range(3):
        assert state.can_undo
        state.undo()
    assert not state.can_undo                    # three gestures, three steps


def test_drop_options_hide_until_drop_is_in_use(panel) -> None:
    """The same ruling a third time: the panel shows the options of the
    effect in use, not every effect there is."""
    widget, state = panel
    knobs = (spin(widget, "drop", "start_size"),
             spin(widget, "drop", "duration"),
             box(widget, "drop", "bounce"))
    assert not _shown(widget, *knobs)
    widget._effect_combo.setCurrentText("drop")
    widget._commit_effect()
    assert _shown(widget, *knobs)
    assert not _shown(widget, spin(widget, "pop", "scale"))
    # nothing inside the block grays out: drop has no obsoleting option
    assert all(knob.isEnabled() for knob in knobs)
    # a PART rule alone also brings the block back
    from scoreanim.core.project import SetPartEffect
    from scoreanim.core.score.identity import PartId
    state.undo()
    widget.sync_from_document(state.doc)
    assert not _shown(widget, *knobs)
    state.execute(SetPartEffect(PartId("P1"), "drop"))
    widget.sync_from_document(state.doc)
    assert _shown(widget, *knobs)


def test_sync_reflects_drop_params(panel) -> None:
    widget, state = panel
    for cmd in (SetEffectParam("drop", "start_size", 8.0),
                SetEffectParam("drop", "duration", 2.0),
                SetEffectParam("drop", "bounce", False)):
        state.execute(cmd)
    widget.sync_from_document(state.doc)
    assert spin(widget, "drop", "start_size").value() == 8.0
    assert spin(widget, "drop", "duration").value() == 2.0
    assert not box(widget, "drop", "bounce").isChecked()
    depth = 0
    while state.can_undo:
        state.undo()
        depth += 1
    assert depth == 3                            # resync added nothing
    widget.sync_from_document(state.doc)         # back to the defaults
    assert spin(widget, "drop", "start_size").value() == 3.0
    assert spin(widget, "drop", "duration").value() == 0.35
    assert box(widget, "drop", "bounce").isChecked()


def test_drop_params_alone_light_the_reset_button(panel) -> None:
    widget, state = panel
    assert not widget._reset_button.isEnabled()
    state.execute(SetEffectParam("drop", "bounce", False))
    widget.sync_from_document(state.doc)
    assert widget._reset_button.isEnabled()


def test_slide_knobs_commit_slide_params(panel) -> None:
    widget, state = panel
    spin(widget, "slide", "direction").setValue(90)
    field(widget, "slide", "direction").commit()
    assert state.committed.style.effect_params["slide"]["direction"] == 90
    field(widget, "slide", "direction").commit()         # epsilon no-op
    spin(widget, "slide", "distance").setValue(500.0)
    field(widget, "slide", "distance").commit()
    assert state.doc.style.effect_params["slide"]["distance"] == 500.0
    spin(widget, "slide", "duration").setValue(1.0)
    field(widget, "slide", "duration").commit()
    assert state.doc.style.effect_params["slide"]["duration"] == 1.0
    assert state.undo_text() == "set effect parameter"
    # bounce starts OFF, so checking it is what writes a param
    assert not box(widget, "slide", "bounce").isChecked()
    box(widget, "slide", "bounce").setChecked(True)
    assert state.doc.style.effect_params["slide"]["bounce"] is True
    # slide's knobs are slide's own
    assert set(state.doc.style.effect_params) == {"slide"}
    for _ in range(4):
        assert state.can_undo
        state.undo()
    assert not state.can_undo                    # four gestures, four steps


def test_slide_options_hide_until_slide_is_in_use(panel) -> None:
    widget, state = panel
    knobs = (spin(widget, "slide", "direction"),
             spin(widget, "slide", "distance"),
             spin(widget, "slide", "duration"),
             box(widget, "slide", "bounce"))
    assert not _shown(widget, *knobs)
    widget._effect_combo.setCurrentText("slide")
    widget._commit_effect()
    assert _shown(widget, *knobs)
    assert not _shown(widget, spin(widget, "drop", "start_size"))
    # nothing inside the block grays out: slide has no obsoleting option
    assert all(knob.isEnabled() for knob in knobs)
    # a PART rule alone also brings the block back
    from scoreanim.core.project import SetPartEffect
    from scoreanim.core.score.identity import PartId
    state.undo()
    widget.sync_from_document(state.doc)
    assert not _shown(widget, *knobs)
    state.execute(SetPartEffect(PartId("P1"), "slide"))
    widget.sync_from_document(state.doc)
    assert _shown(widget, *knobs)


def test_sync_reflects_slide_params(panel) -> None:
    widget, state = panel
    for cmd in (SetEffectParam("slide", "direction", 270),
                SetEffectParam("slide", "distance", 800.0),
                SetEffectParam("slide", "duration", 2.0),
                SetEffectParam("slide", "bounce", True)):
        state.execute(cmd)
    widget.sync_from_document(state.doc)
    assert spin(widget, "slide", "direction").value() == 270
    assert spin(widget, "slide", "distance").value() == 800.0
    assert spin(widget, "slide", "duration").value() == 2.0
    assert box(widget, "slide", "bounce").isChecked()
    depth = 0
    while state.can_undo:
        state.undo()
        depth += 1
    assert depth == 4                            # resync added nothing
    widget.sync_from_document(state.doc)         # back to the defaults
    assert spin(widget, "slide", "direction").value() == 0
    assert spin(widget, "slide", "distance").value() == 120.0
    assert spin(widget, "slide", "duration").value() == 0.35
    assert not box(widget, "slide", "bounce").isChecked()


def test_swell_knobs_commit_swell_params(panel) -> None:
    widget, state = panel
    spin(widget, "swell", "size").setValue(2.0)
    field(widget, "swell", "size").commit()
    assert state.committed.style.effect_params["swell"]["size"] == 2.0
    field(widget, "swell", "size").commit()              # epsilon no-op
    # per cent in the box, a fraction in the document
    spin(widget, "swell", "peak").setValue(25)
    field(widget, "swell", "peak").commit()
    assert state.doc.style.effect_params["swell"]["peak"] == \
        pytest.approx(0.25)
    spin(widget, "swell", "duration").setValue(1.5)
    field(widget, "swell", "duration").commit()
    assert state.doc.style.effect_params["swell"]["duration"] == 1.5
    assert state.undo_text() == "set effect parameter"
    # note_value starts ON here — the one preset it defaults to — so
    # UNchecking it is what writes a param
    assert box(widget, "swell", "note_value").isChecked()
    box(widget, "swell", "note_value").setChecked(False)
    assert state.doc.style.effect_params["swell"]["note_value"] is False
    # swell's knobs are swell's own
    assert set(state.doc.style.effect_params) == {"swell"}
    for _ in range(4):
        assert state.can_undo
        state.undo()
    assert not state.can_undo                    # four gestures, four steps


def test_swell_options_hide_until_swell_is_in_use(panel) -> None:
    widget, state = panel
    knobs = (spin(widget, "swell", "size"),
             spin(widget, "swell", "peak"),
             spin(widget, "swell", "duration"),
             box(widget, "swell", "note_value"))
    assert not _shown(widget, *knobs)
    widget._effect_combo.setCurrentText("swell")
    widget._commit_effect()
    assert _shown(widget, *knobs)
    assert not _shown(widget, spin(widget, "drop", "start_size"))
    # the duration opens GRAYED: "Entire note value" is on by default,
    # so the number it would type is already obsolete
    assert not spin(widget, "swell", "duration").isEnabled()
    assert spin(widget, "swell", "size").isEnabled()
    box(widget, "swell", "note_value").setChecked(False)
    assert spin(widget, "swell", "duration").isEnabled()


def test_sync_reflects_swell_params(panel) -> None:
    widget, state = panel
    for cmd in (SetEffectParam("swell", "size", 2.5),
                SetEffectParam("swell", "peak", 0.8),
                SetEffectParam("swell", "duration", 2.0),
                SetEffectParam("swell", "note_value", False)):
        state.execute(cmd)
    widget.sync_from_document(state.doc)
    assert spin(widget, "swell", "size").value() == 2.5
    assert spin(widget, "swell", "peak").value() == 80
    assert spin(widget, "swell", "duration").value() == 2.0
    assert not box(widget, "swell", "note_value").isChecked()
    depth = 0
    while state.can_undo:
        state.undo()
        depth += 1
    assert depth == 4                            # resync added nothing
    widget.sync_from_document(state.doc)         # back to the defaults
    assert spin(widget, "swell", "size").value() == 1.4
    assert spin(widget, "swell", "peak").value() == 50
    assert spin(widget, "swell", "duration").value() == 0.8
    assert box(widget, "swell", "note_value").isChecked()


def test_follow_volume_commits_and_shows_with_the_swell(panel) -> None:
    widget, state = panel
    check = box(widget, "swell", "follow")
    assert check.text() == "Follow volume"
    assert not check.isChecked()                 # off by default
    assert not _shown(widget, check)             # and hidden until in use
    widget._effect_combo.setCurrentText("swell")
    widget._commit_effect()
    assert _shown(widget, check)
    check.setChecked(True)
    assert state.doc.style.effect_params["swell"]["follow"] is True
    assert state.undo_text() == "set effect parameter"


def test_follow_grays_the_peak_and_forces_the_note_value(panel) -> None:
    """Peak means nothing while following — the top is a stretch, not a
    point — and the note-value stretch is on whatever the box said, so
    the box says so too (Marcus, 2026-08-01)."""
    widget, state = panel
    widget._effect_combo.setCurrentText("swell")
    widget._commit_effect()
    note_value = box(widget, "swell", "note_value")
    assert spin(widget, "swell", "peak").isEnabled()
    assert note_value.isEnabled()

    box(widget, "swell", "follow").setChecked(True)
    assert not spin(widget, "swell", "peak").isEnabled()
    assert note_value.isChecked() and not note_value.isEnabled()
    assert not spin(widget, "swell", "duration").isEnabled()
    assert spin(widget, "swell", "size").isEnabled()   # the plateau's height

    # even when the document says otherwise: follow is what decides
    state.execute(SetEffectParam("swell", "note_value", False))
    widget.sync_from_document(state.doc)
    assert note_value.isChecked() and not note_value.isEnabled()
    assert not spin(widget, "swell", "duration").isEnabled()

    # and turning follow off hands the boxes straight back
    state.execute(SetEffectParam("swell", "follow", False))
    widget.sync_from_document(state.doc)
    assert spin(widget, "swell", "peak").isEnabled()
    assert note_value.isEnabled() and not note_value.isChecked()
    assert spin(widget, "swell", "duration").isEnabled()


def test_swell_params_alone_light_the_reset_button(panel) -> None:
    widget, state = panel
    assert not widget._reset_button.isEnabled()
    state.execute(SetEffectParam("swell", "size", 2.0))
    widget.sync_from_document(state.doc)
    assert widget._reset_button.isEnabled()


def test_slide_params_alone_light_the_reset_button(panel) -> None:
    widget, state = panel
    assert not widget._reset_button.isEnabled()
    state.execute(SetEffectParam("slide", "bounce", True))
    widget.sync_from_document(state.doc)
    assert widget._reset_button.isEnabled()


def test_reset_clears_every_preset_together(panel) -> None:
    """One Reset really resets what the panel shows: every preset's
    params go, in ONE undo step."""
    widget, state = panel
    widget._effect_combo.setCurrentText("fade")
    widget._commit_effect()
    spin(widget, "fade", "duration").setValue(1.5)
    field(widget, "fade", "duration").commit()
    state.execute(SetEffectParam("pop", "scale", 2.0))
    state.execute(SetEffectParam("drop", "start_size", 5.0))
    state.execute(SetEffectParam("slide", "distance", 900.0))
    state.execute(SetEffectParam("swell", "size", 2.0))
    assert widget._reset_button.isEnabled()
    before = state.doc
    widget._commit_reset()
    assert state.doc.style.default_effect is None
    assert state.doc.style.effect_params == {}
    assert spin(widget, "fade", "duration").value() == 0.4
    assert spin(widget, "drop", "start_size").value() == 3.0
    assert spin(widget, "slide", "distance").value() == 120.0
    assert spin(widget, "swell", "size").value() == 1.4
    assert not widget._reset_button.isEnabled()
    state.undo()                                 # ONE step restores them all
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
    spin(widget, "pop", "scale").setValue(2.0)
    field(widget, "pop", "scale").commit()
    box(widget, "pop", "note_value").setChecked(True)
    spin(widget, "pop", "peak_offset").setValue(-100)
    field(widget, "pop", "peak_offset").commit()
    assert widget._reset_button.isEnabled()
    depth_before = 4
    widget._commit_reset()
    # the doc is back at the pre-M4 defaults and the panel shows them
    assert state.doc.style.default_effect is None
    assert state.doc.style.effect_params == {}
    assert widget._effect_combo.currentText() == DEFAULT_EFFECT
    assert spin(widget, "pop", "scale").value() == 1.25
    assert not box(widget, "pop", "note_value").isChecked()
    assert spin(widget, "pop", "peak_offset").value() == 0
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
    spin(widget, "pop", "scale").setValue(2.0)
    field(widget, "pop", "scale").commit()
    spin(widget, "pop", "settle").setValue(0.5)
    field(widget, "pop", "settle").commit()
    box(widget, "pop", "note_value").setChecked(True)
    spin(widget, "pop", "peak_offset").setValue(-100)
    field(widget, "pop", "peak_offset").commit()
    for _ in range(5):
        assert state.can_undo
        state.undo()
    assert not state.can_undo
    assert state.doc.style.default_effect is None
    assert state.doc.style.effect_params == {}


# -- a second effect to run with the first ("drop+fade") --------------------

def _combine_items(widget) -> list[str]:
    return [widget._combine_combo.itemText(i)
            for i in range(widget._combine_combo.count())]


def test_combine_offers_every_other_preset(panel) -> None:
    """(none) plus every preset except the one already chosen — and the
    list follows the first choice."""
    widget, _state = panel
    assert _combine_items(widget)[0] == "(none)"
    assert DEFAULT_EFFECT not in _combine_items(widget)
    widget._effect_combo.setCurrentText("drop")
    widget._commit_effect()
    assert "drop" not in _combine_items(widget)
    assert {"appear", "fade", "pop", "slide"} <= set(_combine_items(widget))


def test_two_effects_are_stored_as_one_name(panel) -> None:
    widget, state = panel
    widget._effect_combo.setCurrentText("pop")
    widget._commit_effect()
    widget._combine_combo.setCurrentText("fade")
    widget._commit_effect()
    assert state.doc.style.default_effect == "pop+fade"
    assert state.undo_text() == "set default effect"    # ONE command
    widget._commit_effect()                             # same → no-op
    state.undo()
    assert state.doc.style.default_effect == "pop"      # one step back
    # and taking the second one off stores the first alone
    widget.sync_from_document(state.doc)
    widget._combine_combo.setCurrentText("fade")
    widget._commit_effect()
    widget._combine_combo.setCurrentText("(none)")
    widget._commit_effect()
    assert state.doc.style.default_effect == "pop"


def test_a_stored_combination_comes_back_split(panel) -> None:
    from scoreanim.core.project import SetDefaultEffect
    widget, state = panel
    state.execute(SetDefaultEffect("drop+fade"))
    widget.sync_from_document(state.doc)
    assert widget._effect_combo.currentText() == "drop"
    assert widget._combine_combo.currentText() == "fade"


def test_a_longer_hand_edited_name_shows_whole(panel) -> None:
    """More parts than two dropdowns can show: the stored intent is
    displayed as it stands, never silently shortened."""
    from scoreanim.core.project import SetDefaultEffect
    widget, state = panel
    state.execute(SetDefaultEffect("drop+fade+slide"))
    widget.sync_from_document(state.doc)
    assert widget._effect_combo.currentText() == "drop+fade+slide"
    assert widget._combine_combo.currentText() == "(none)"


def test_changing_the_first_effect_drops_a_clashing_second(panel) -> None:
    widget, state = panel
    widget._effect_combo.setCurrentText("drop")
    widget._commit_effect()
    widget._combine_combo.setCurrentText("fade")
    widget._commit_effect()
    widget._effect_combo.setCurrentText("fade")   # now the same as the second
    widget._commit_effect()
    assert widget._combine_combo.currentText() == "(none)"
    assert state.doc.style.default_effect == "fade"


def test_both_parts_of_a_combination_show_their_options(panel) -> None:
    """A preset is in use when it is one PART of the name, so both
    blocks are on screen."""
    widget, state = panel
    widget._effect_combo.setCurrentText("drop")
    widget._commit_effect()
    widget._combine_combo.setCurrentText("fade")
    widget._commit_effect()
    assert _shown(widget, spin(widget, "drop", "start_size"),
                  spin(widget, "fade", "duration"))
    assert not _shown(widget, spin(widget, "pop", "scale"))
    state.undo()                                 # back to drop alone
    widget.sync_from_document(state.doc)
    assert _shown(widget, spin(widget, "drop", "start_size"))
    assert not _shown(widget, spin(widget, "fade", "duration"))


def test_a_part_rule_combination_shows_its_options(panel) -> None:
    """The same membership test reaches part and element rules."""
    from scoreanim.core.project import SetPartEffect
    from scoreanim.core.score.identity import PartId
    widget, state = panel
    state.execute(SetPartEffect(PartId("P1"), "slide+fade"))
    widget.sync_from_document(state.doc)
    assert _shown(widget, spin(widget, "slide", "distance"),
                  spin(widget, "fade", "duration"))


# -- Volume response ------------------------------------------------------

def _vol(widget, key):
    return widget.volume.spins[key]


def test_quiet_and_loud_wait_for_amount(panel) -> None:
    """They describe a range nothing is being read onto while Amount is
    0, so they gray out — the "an option another option renders
    obsolete" rule, from the other side."""
    widget, state = panel
    assert not _vol(widget, "quiet").isEnabled()
    assert not _vol(widget, "loud").isEnabled()
    assert _vol(widget, "amount").isEnabled()    # the switch is never gray

    state.execute(SetVolumeParam("amount", 0.5))
    widget.sync_from_document(state.doc)
    assert _vol(widget, "quiet").isEnabled()
    assert _vol(widget, "loud").isEnabled()

    state.execute(SetVolumeParam("amount", 0.0))
    widget.sync_from_document(state.doc)
    assert not _vol(widget, "quiet").isEnabled()


def test_the_block_shows_the_document(panel) -> None:
    widget, state = panel
    assert _vol(widget, "amount").value() == pytest.approx(0.0)
    assert _vol(widget, "quiet").value() == pytest.approx(0.5)
    assert _vol(widget, "loud").value() == pytest.approx(1.5)
    state.execute(SetVolumeParam("loud", 2.25))
    widget.sync_from_document(state.doc)
    assert _vol(widget, "loud").value() == pytest.approx(2.25)


def test_the_block_is_always_on_screen(panel) -> None:
    """It is not an effect, so the "show the options of the effect you
    are using" rule has nothing to say about it — it is there whatever
    the default effect is."""
    widget, state = panel
    # non-vacuity: a preset's block IS hidden here, so "visible" means
    # something
    assert not widget.blocks["pop"].header.isVisibleTo(widget)
    assert widget.volume.header.isVisibleTo(widget)
    state.execute(SetDefaultEffect("slide"))
    widget.sync_from_document(state.doc)
    assert not widget.blocks["pop"].header.isVisibleTo(widget)
    assert widget.volume.header.isVisibleTo(widget)


def test_a_volume_setting_alone_lights_the_reset_button(panel) -> None:
    widget, state = panel
    assert not widget._reset_button.isEnabled()
    state.execute(SetVolumeParam("amount", 0.6))
    widget.sync_from_document(state.doc)
    assert widget._reset_button.isEnabled()
    widget._commit_reset()
    assert state.doc.style.volume == {}
    assert not widget._reset_button.isEnabled()


# -- System pulse ---------------------------------------------------------

def _pulse(widget):
    return widget.pulse.spins["amount"]


def test_the_pulse_block_shows_the_document_in_per_cent(panel) -> None:
    """Per cent in the box, a fraction in the document — the swell Peak
    precedent, in both directions."""
    widget, state = panel
    assert _pulse(widget).value() == 0
    state.execute(SetPulseParam("amount", 0.1))
    widget.sync_from_document(state.doc)
    assert _pulse(widget).value() == 10


def test_a_pulse_commit_stores_a_fraction(panel) -> None:
    widget, state = panel
    _pulse(widget).setValue(15)
    widget.pulse.fields["amount"].commit()
    assert state.doc.style.pulse["amount"] == pytest.approx(0.15)


def test_the_pulse_box_stops_at_twenty_per_cent(panel) -> None:
    """A whole system is a big thing to move, so the box will not let
    the page past the range core clamps to anyway."""
    widget, _ = panel
    assert (_pulse(widget).minimum(), _pulse(widget).maximum()) == (0, 20)


def test_the_pulse_block_is_always_on_screen(panel) -> None:
    """It is not an effect, so the "show the options of the effect you
    are using" rule has nothing to say about it."""
    widget, state = panel
    # non-vacuity: a preset's block IS hidden here
    assert not widget.blocks["pop"].header.isVisibleTo(widget)
    assert widget.pulse.header.isVisibleTo(widget)
    state.execute(SetDefaultEffect("slide"))
    widget.sync_from_document(state.doc)
    assert widget.pulse.header.isVisibleTo(widget)


def test_a_pulse_amount_alone_lights_the_reset_button(panel) -> None:
    widget, state = panel
    assert not widget._reset_button.isEnabled()
    state.execute(SetPulseParam("amount", 0.1))
    widget.sync_from_document(state.doc)
    assert widget._reset_button.isEnabled()
    widget._commit_reset()
    assert state.doc.style.pulse == {}
    assert not widget._reset_button.isEnabled()


def test_the_two_pulse_amounts_are_a_pair_of_knobs(panel) -> None:
    """One follows the recording, the other follows the notes — same
    units, same range, so they read as the pair they are."""
    widget, state = panel
    follow, pop = widget.pulse.spins["amount"], widget.pulse.spins["pop_amount"]
    assert (pop.minimum(), pop.maximum()) == (follow.minimum(),
                                              follow.maximum()) == (0, 20)
    assert pop.value() == 0

    pop.setValue(8)
    widget.pulse.fields["pop_amount"].commit()
    assert state.doc.style.pulse == {"pop_amount": pytest.approx(0.08)}
    assert "amount" not in state.doc.style.pulse   # one knob, one key


def test_the_pop_shape_knobs_show_the_document(panel) -> None:
    widget, state = panel
    assert widget.pulse.spins["notes_for_full"].value() == 6
    assert widget.pulse.spins["settle"].value() == pytest.approx(0.25)

    state.execute(SetPulseParam("notes_for_full", 10))
    state.execute(SetPulseParam("settle", 0.4))
    widget.sync_from_document(state.doc)

    assert widget.pulse.spins["notes_for_full"].value() == 10
    assert widget.pulse.spins["settle"].value() == pytest.approx(0.4)


def test_the_pop_shape_knobs_wait_on_the_pop_amount(panel) -> None:
    """They describe a jump nothing is drawing while the amount is 0 —
    the Quiet/Loud precedent in the Volume response block."""
    widget, state = panel
    assert not widget.pulse.spins["notes_for_full"].isEnabled()
    assert not widget.pulse.spins["settle"].isEnabled()
    # and the follow half is not what wakes them
    state.execute(SetPulseParam("amount", 0.1))
    widget.sync_from_document(state.doc)
    assert not widget.pulse.spins["settle"].isEnabled()

    state.execute(SetPulseParam("pop_amount", 0.05))
    widget.sync_from_document(state.doc)
    assert widget.pulse.spins["notes_for_full"].isEnabled()
    assert widget.pulse.spins["settle"].isEnabled()


def test_reset_clears_the_pop_settings_too(panel) -> None:
    widget, state = panel
    state.execute(SetPulseParam("pop_amount", 0.1))
    state.execute(SetPulseParam("notes_for_full", 12))
    widget.sync_from_document(state.doc)
    assert widget._reset_button.isEnabled()

    widget._commit_reset()
    assert state.doc.style.pulse == {}
    assert widget.pulse.spins["pop_amount"].value() == 0
    assert widget.pulse.spins["notes_for_full"].value() == 6


# -- the glow block -------------------------------------------------------

def swatch(widget, preset, key):
    return widget.blocks[preset].swatches[key]


def test_glow_options_hide_until_glow_is_in_use(panel) -> None:
    widget, state = panel
    knobs = (swatch(widget, "glow", "color"),
             spin(widget, "glow", "radius"),
             spin(widget, "glow", "density"),
             spin(widget, "glow", "attack"),
             spin(widget, "glow", "sustain"),
             spin(widget, "glow", "release"),
             box(widget, "glow", "swell_on"),
             spin(widget, "glow", "duration"),
             box(widget, "glow", "note_value"))
    assert not _shown(widget, *knobs)
    widget._effect_combo.setCurrentText("glow")
    widget._commit_effect()
    assert _shown(widget, *knobs)
    assert not _shown(widget, spin(widget, "swell", "size"))
    # the duration opens GRAYED: the note value is on by default here
    assert box(widget, "glow", "note_value").isChecked()
    assert not spin(widget, "glow", "duration").isEnabled()
    box(widget, "glow", "note_value").setChecked(False)
    assert spin(widget, "glow", "duration").isEnabled()


def test_the_glow_block_no_longer_offers_a_strength(panel) -> None:
    """It was a second knob on the axis the envelope's own levels own,
    so the block ends at Colour, Radius, Density, the envelope and the
    duration — every one of them changing one thing."""
    widget, _state = panel
    block = widget.blocks["glow"]
    assert "strength" not in block.spins
    assert "strength" not in block.boxes
    keys = [knob.key for _name, _title, knobs in BLOCKS
            for knob in knobs if _name == "glow"]
    assert "strength" not in keys
    assert keys[:3] == ["color", "radius", "density"]


def test_glow_knobs_commit_glow_params(panel) -> None:
    widget, state = panel
    spin(widget, "glow", "radius").setValue(60.0)
    field(widget, "glow", "radius").commit()
    assert state.committed.style.effect_params["glow"]["radius"] == 60.0
    spin(widget, "glow", "sustain").setValue(50)
    field(widget, "glow", "sustain").commit()
    assert state.doc.style.effect_params["glow"]["sustain"] == 0.5
    spin(widget, "glow", "duration").setValue(1.2)
    field(widget, "glow", "duration").commit()
    assert state.doc.style.effect_params["glow"]["duration"] == 1.2
    # note_value starts ON, so UNchecking it is what writes a param
    box(widget, "glow", "note_value").setChecked(False)
    assert state.doc.style.effect_params["glow"]["note_value"] is False
    assert set(state.doc.style.effect_params) == {"glow"}
    for _ in range(4):
        assert state.can_undo
        state.undo()
    assert not state.can_undo                    # four gestures, four steps


def test_the_envelope_knobs_hold_per_cent_and_store_fractions(panel) -> None:
    """The swell Peak precedent: the box counts in per cent of the note
    and the document keeps a fraction."""
    widget, state = panel
    assert spin(widget, "glow", "attack").value() == 10     # the defaults
    assert spin(widget, "glow", "sustain").value() == 100
    assert spin(widget, "glow", "release").value() == 20
    for key, shown, stored in (("attack", 30, 0.3), ("sustain", 60, 0.6),
                               ("release", 45, 0.45), ("swell_pos", 25, 0.25),
                               ("swell_level", 80, 0.8)):
        spin(widget, "glow", key).setValue(shown)
        field(widget, "glow", key).commit()
        assert state.committed.style.effect_params["glow"][key] == \
            pytest.approx(stored)
    # the checkbox is a flag, not a number
    box(widget, "glow", "swell_on").setChecked(True)
    assert state.doc.style.effect_params["glow"]["swell_on"] is True
    for _ in range(6):
        assert state.can_undo
        state.undo()
    assert not state.can_undo                    # six gestures, six steps


def test_the_swell_knobs_gray_until_the_swell_is_on(panel) -> None:
    widget, state = panel
    widget._effect_combo.setCurrentText("glow")
    widget._commit_effect()
    assert not spin(widget, "glow", "swell_pos").isEnabled()
    assert not spin(widget, "glow", "swell_level").isEnabled()
    box(widget, "glow", "swell_on").setChecked(True)
    assert spin(widget, "glow", "swell_pos").isEnabled()
    assert spin(widget, "glow", "swell_level").isEnabled()


def test_an_old_shape_word_shows_as_the_envelope_it_maps_to(panel) -> None:
    """A project saved before the envelope existed still glows in its
    old shape, so the boxes have to describe that shape rather than the
    plain defaults — the panel never says something the effect is not
    doing."""
    widget, state = panel
    state.execute(SetEffectParam("glow", "shape", "swell"))
    state.execute(SetEffectParam("glow", "peak", 0.25))
    widget.sync_from_document(state.doc)
    assert spin(widget, "glow", "attack").value() == 0
    assert spin(widget, "glow", "sustain").value() == 0
    assert spin(widget, "glow", "release").value() == 0
    assert box(widget, "glow", "swell_on").isChecked()
    assert spin(widget, "glow", "swell_pos").value() == 25
    # and an old "pop" is the other shape it maps to
    state.execute(SetEffectParam("glow", "shape", "pop"))
    widget.sync_from_document(state.doc)
    assert spin(widget, "glow", "attack").value() == 0
    assert spin(widget, "glow", "sustain").value() == 100
    assert spin(widget, "glow", "release").value() == 100
    assert not box(widget, "glow", "swell_on").isChecked()


def test_the_colour_swatch_commits_one_command(panel, monkeypatch) -> None:
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog

    widget, state = panel
    monkeypatch.setattr(QColorDialog, "getColor",
                        staticmethod(lambda *a, **k: QColor("#00ff88")))
    widget.blocks["glow"]._pick_color(widget.blocks["glow"]._by_key["color"])
    assert state.doc.style.effect_params["glow"]["color"] == "#00ff88"
    assert state.undo_text() == "set effect parameter"
    # the swatch shows what the document says
    widget.sync_from_document(state.doc)
    assert swatch(widget, "glow", "color").text() == "#00ff88"
    # cancelling (an invalid colour) commits nothing
    monkeypatch.setattr(QColorDialog, "getColor",
                        staticmethod(lambda *a, **k: QColor()))
    widget.blocks["glow"]._pick_color(widget.blocks["glow"]._by_key["color"])
    state.undo()
    assert not state.can_undo


def test_sync_reflects_glow_params(panel) -> None:
    widget, state = panel
    for cmd in (SetEffectParam("glow", "color", "#123456"),
                SetEffectParam("glow", "radius", 12.0),
                SetEffectParam("glow", "density", 0.25),
                SetEffectParam("glow", "attack", 0.35),
                SetEffectParam("glow", "note_value", False)):
        state.execute(cmd)
    widget.sync_from_document(state.doc)
    assert swatch(widget, "glow", "color").text() == "#123456"
    assert spin(widget, "glow", "radius").value() == 12.0
    assert spin(widget, "glow", "density").value() == 25
    assert spin(widget, "glow", "attack").value() == 35
    assert not box(widget, "glow", "note_value").isChecked()
    depth = 0
    while state.can_undo:
        state.undo()
        depth += 1
    assert depth == 5                            # resync added nothing
    widget.sync_from_document(state.doc)         # back to the defaults
    assert swatch(widget, "glow", "color").text() == "#ffcc66"
    assert spin(widget, "glow", "radius").value() == 24.0
    assert spin(widget, "glow", "attack").value() == 10
    assert box(widget, "glow", "note_value").isChecked()


def test_an_unknown_old_shape_word_shows_the_pop_envelope(panel) -> None:
    """A hand-edited word fell soft to a pop before and still does, so
    that is what the boxes describe."""
    widget, state = panel
    state.execute(SetEffectParam("glow", "shape", "shimmer"))
    widget.sync_from_document(state.doc)
    assert spin(widget, "glow", "attack").value() == 0
    assert spin(widget, "glow", "release").value() == 100
    # and the document is untouched by the resync
    assert state.doc.style.effect_params["glow"]["shape"] == "shimmer"


def test_glow_params_alone_light_the_reset_button(panel) -> None:
    widget, state = panel
    assert not widget._reset_button.isEnabled()
    state.execute(SetEffectParam("glow", "radius", 12.0))
    widget.sync_from_document(state.doc)
    assert widget._reset_button.isEnabled()
    widget._commit_reset()
    assert state.doc.style.effect_params == {}
    assert spin(widget, "glow", "radius").value() == 24.0


# -- the envelope canvas ----------------------------------------------------
#
# The picture of the six shape params, and the other way to author them.
# The widget's own behaviour is tests/test_envelope_editor.py; what these
# pin is the wiring: one undo entry per drag, the boxes and the canvas
# showing the same thing, and the block hiding as a unit.

def canvas(widget, preset):
    return widget.blocks[preset].envelopes["envelope"].canvas


def drag_to(widget, canvas_widget, handle, to_x, to_y, state, steps=4):
    """A whole gesture, with the window's resync wired up the way
    MainWindow wires it — every document change comes back to the panel,
    which is what keeps the boxes on the handle."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from scoreanim.core.editing import handle_points

    def event(kind, x, y):
        return QMouseEvent(kind, QPointF(x, y), Qt.MouseButton.LeftButton,
                           Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)

    state.document_changed.connect(
        lambda: widget.sync_from_document(state.doc))
    x, y = handle_points(canvas_widget.spec, canvas_widget.box())[handle]
    canvas_widget.mousePressEvent(
        event(QMouseEvent.Type.MouseButtonPress, x, y))
    for step in range(1, steps + 1):
        canvas_widget.mouseMoveEvent(event(
            QMouseEvent.Type.MouseMove, x + (to_x - x) * step / steps,
            y + (to_y - y) * step / steps))
    canvas_widget.mouseReleaseEvent(
        event(QMouseEvent.Type.MouseButtonRelease, to_x, to_y))


@pytest.fixture
def glow_canvas(panel):
    """A panel with glow in use and its canvas sized like the panel."""
    widget, state = panel
    state.execute(SetDefaultEffect("glow"))
    widget.sync_from_document(state.doc)
    shown = canvas(widget, "glow")
    shown.resize(250, 130)
    return widget, state, shown


def test_the_envelope_canvas_hides_with_its_block(panel) -> None:
    widget, state = panel
    section = widget.blocks["glow"].envelopes["envelope"].section
    assert not section.isVisible()               # glow is not in use
    assert not section.expanded                  # and it opens closed
    state.execute(SetDefaultEffect("glow"))
    widget.sync_from_document(state.doc)
    widget.show()
    assert section.isVisible()


def test_a_drag_previews_and_lands_as_one_undo_entry(glow_canvas) -> None:
    from scoreanim.core.editing import Handle, x_of

    widget, state, shown = glow_canvas
    depth_before = 1                             # the SetDefaultEffect
    seen = []
    state.document_changed.connect(
        lambda: seen.append(state.doc.style.effect_params
                            .get("glow", {}).get("attack")))
    drag_to(widget, shown, Handle.ATTACK, x_of(0.4, shown.box()),
            shown.box().y, state)
    # the score saw every step of the drag, not just the end of it
    previews = [value for value in seen if value is not None]
    assert len(set(previews)) > 1
    assert state.committed.style.effect_params["glow"]["attack"] == \
        pytest.approx(0.4, abs=0.01)
    assert state.undo_text() == "set effect parameter"
    state.undo()
    assert "attack" not in state.doc.style.effect_params.get("glow", {})
    depth = 0
    while state.can_undo:
        state.undo()
        depth += 1
    assert depth == depth_before                 # one entry for the drag


def test_the_swell_point_moves_two_params_in_one_entry(glow_canvas) -> None:
    from scoreanim.core.editing import Handle, x_of

    widget, state, shown = glow_canvas
    state.execute(SetEffectParam("glow", "swell_on", True))
    widget.sync_from_document(state.doc)
    box_ = shown.box()
    drag_to(widget, shown, Handle.SWELL, x_of(0.62, box_),
            box_.y + 0.5 * box_.h, state)
    params = state.committed.style.effect_params["glow"]
    assert params["swell_pos"] == pytest.approx(0.62, abs=0.01)
    assert params["swell_level"] == pytest.approx(0.5, abs=0.02)
    assert state.undo_text() == "change effect options"
    state.undo()                                 # both go together
    assert "swell_pos" not in state.doc.style.effect_params["glow"]
    assert "swell_level" not in state.doc.style.effect_params["glow"]


def test_the_boxes_follow_the_handle(glow_canvas) -> None:
    """Two views of one set of values: dragging the canvas moves the
    numbers, and typing a number redraws the canvas."""
    from scoreanim.core.editing import Handle, x_of

    widget, state, shown = glow_canvas
    drag_to(widget, shown, Handle.ATTACK, x_of(0.3, shown.box()),
            shown.box().y, state)
    assert spin(widget, "glow", "attack").value() == \
        pytest.approx(30, abs=1)
    spin(widget, "glow", "release").setValue(45)
    field(widget, "glow", "release").commit()
    widget.sync_from_document(state.doc)
    assert shown.spec.release == pytest.approx(0.45)


def test_a_press_that_goes_nowhere_is_not_an_edit(glow_canvas) -> None:
    from scoreanim.core.editing import Handle, handle_points

    widget, state, shown = glow_canvas
    x, y = handle_points(shown.spec, shown.box())[Handle.SUSTAIN]
    drag_to(widget, shown, Handle.SUSTAIN, x, y, state)
    assert "glow" not in state.committed.style.effect_params
    assert state.undo_text() == "set default effect"


def test_reset_clears_a_dragged_envelope(glow_canvas) -> None:
    from scoreanim.core.editing import Handle, x_of

    widget, state, shown = glow_canvas
    drag_to(widget, shown, Handle.ATTACK, x_of(0.3, shown.box()),
            shown.box().y, state)
    assert widget._reset_button.isEnabled()
    widget._commit_reset()
    assert state.doc.style.effect_params == {}
    assert shown.spec.attack == pytest.approx(0.10)     # back to the default
