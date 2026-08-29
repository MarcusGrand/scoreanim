"""Style controls for the current selection (M3.3) — closes BACKLOG 9.

The per-element override model, `SetElementStyle`, and its serialization
have existed and been tested since Phase 5.3; what was missing was a way
to point at an element. M2 built that, so this is the editing UI the
backlog item has been waiting for. No new document semantics.

Three decisions are baked in here, all ruled 2026-07-27:

**Scope (closes M4's F5).** M4 dropped the per-part effect submenu, and
per-part effect rules have been honored and round-tripped but
UNAUTHORABLE since. Rule 13 says a selection carries its part, so the
scope switch gives those rules their home: the same two controls write
either the element override or the part rule. It governs colour as well
as effect, because a switch that silently applied to one of two adjacent
widgets would be worse than one that means what it says.

**The `:seg` fan-out.** On a spanner broken across systems, an element
override targets one segment. It now writes the whole family
(`core/editing/segments.py`), so colouring a hairpin does not mean
hunting down every system it crosses. Still ONE undo entry.

**It writes the AUTHORED channel only.** M2.8 made `ElementItem` compose
authored colour under the transient selection tint, and the two must
stay distinguishable (rule 13). So this executes commands and lets
`DocumentSync.sync_styles` — which owns the diff cache — push colour
through `set_color`. Nothing here touches the tint, and a user who
colours an element the selection orange still sees it selected, via the
`SELECTION_ALT_COLOR` fallback M2.8 measured.
"""
from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QButtonGroup, QColorDialog, QComboBox,
                               QFormLayout, QHBoxLayout, QLabel, QPushButton,
                               QRadioButton, QVBoxLayout, QWidget)

from scoreanim.core.animation import PRESETS, ElementStyle
from scoreanim.core.animation.style import takes_part_color
from scoreanim.core.editing import family_of
from scoreanim.core.project import (SetElementStyle, SetPartColor,
                                    SetPartEffect)
from scoreanim.core.selection import Selection
from scoreanim.ui import panel_style, tips
from scoreanim.ui.app_state import AppState

_INHERIT = "(inherit)"          # no override at this scope

# Why a control here is dead. Both are facts about what was picked, so
# they name the pick rather than telling the user to try again.
_NO_PART = "This object belongs to the score, not to one part"
_NO_COLOUR = "This kind of ink is always drawn in the page's own colour"


class SelectionStyleControls(QWidget):
    """Colour + effect + clear, scoped to the element or its part."""

    def __init__(self, app_state: AppState,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = app_state
        self._scenes = None                 # bound per load, for the family
        self._labels: list[QLabel] = []

        self._element_radio = QRadioButton("This element")
        self._part_radio = QRadioButton("This part")
        self._element_radio.setChecked(True)
        self._scope = QButtonGroup(self)
        self._scope.addButton(self._element_radio)
        self._scope.addButton(self._part_radio)
        tips.describe(self._element_radio,
                      "Write this one object's own override")
        tips.describe(
            self._part_radio,
            "Write the part rule instead of an element override — the "
            "per-part effect authoring M4 deferred")
        scope_row = QHBoxLayout()
        scope_row.setContentsMargins(0, 0, 0, 0)
        scope_row.addWidget(self._element_radio)
        scope_row.addWidget(self._part_radio)
        scope_row.addStretch(1)
        scope_box = QWidget()
        scope_box.setLayout(scope_row)

        self._color_button = QPushButton()
        tips.describe(self._color_button,
                      "Pick the colour this ink is drawn in")
        self._color_button.clicked.connect(self._pick_color)
        self._color_default = QPushButton("Default")
        tips.describe(self._color_default,
                      "Drop the colour override and go back to what is "
                      "inherited")
        self._color_default.clicked.connect(lambda: self._commit_color(None))
        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(panel_style.COLUMN_GAP)
        color_row.addWidget(self._color_button, 1)
        color_row.addWidget(self._color_default)
        color_box = QWidget()
        color_box.setLayout(color_row)

        self._effect = QComboBox()
        tips.describe(self._effect,
                      "The effect this runs instead of the inherited one")
        self._effect.addItem(_INHERIT)
        for name in sorted(PRESETS):
            self._effect.addItem(name)
        self._effect.activated.connect(self._commit_effect)

        self._clear = QPushButton("Clear style overrides")
        tips.describe(
            self._clear,
            "Remove this element's colour and effect override — the "
            "cheap reset that keeps overrides safe to experiment with "
            "(rule 5). A nudge is separate intent and is not cleared "
            "here; undo, or drag it back.")
        self._clear.clicked.connect(self._clear_overrides)

        form = QFormLayout()
        # the padding is paid at the Selection panel's own edge
        panel_style.style_form(form, padding=False)
        # a label says what its field says (E2)
        for text, widget in (("Apply to", self._part_radio),
                             ("Color", self._color_button),
                             ("Effect", self._effect)):
            label = QLabel(text)
            tips.describe(label, tips.live_tip(widget))
            self._labels.append(label)
        form.addRow(self._labels[0], scope_box)
        form.addRow(self._labels[1], color_box)
        form.addRow(self._labels[2], self._effect)
        panel_style.fix_label_column(form)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(panel_style.ROW_GAP)
        root.addLayout(form)
        root.addWidget(self._clear)

        self._scope.buttonClicked.connect(lambda _: self.sync())
        app_state.document_changed.connect(self.sync)
        app_state.selection_changed.connect(self.sync)
        self.sync()

    def bind_scenes(self, scenes) -> None:
        """The loaded element registry, so the `:seg` fan-out only ever
        names ids that exist."""
        self._scenes = scenes

    # -- state -------------------------------------------------------------

    @property
    def _selection(self) -> Selection | None:
        return self._state.selection

    @property
    def _part_scope(self) -> bool:
        return self._part_radio.isChecked()

    def _ids(self) -> tuple:
        """Every element id this write should reach: the selection's
        `:seg` family, intersected with the loaded score."""
        selection = self._selection
        if selection is None:
            return ()
        known = self._scenes.items.keys() if self._scenes is not None \
            else (selection.element_id,)
        return family_of(selection.element_id, known)

    def sync(self) -> None:
        """Re-derive every control from the document (execute, undo and
        redo all arrive here) — the blockSignals idiom the parts menu
        and the effects panel already use."""
        selection = self._selection
        self.setEnabled(selection is not None)
        if selection is None:
            self._set_swatch(None)
            self._set_effect(None)
            return
        # a part scope needs a part; score-level ink (a barline) has none
        tips.gate(self._part_radio, selection.part is not None, _NO_PART)
        if self._part_radio.isChecked() and selection.part is None:
            self._element_radio.setChecked(True)
        # colour is only meaningful where colour reaches (ruling D): a
        # clef or a rest animates but stays black
        colourable = takes_part_color(selection.obj)
        tips.gate(self._color_button, colourable, _NO_COLOUR)
        tips.gate(self._color_default, colourable, _NO_COLOUR)

        rule = self._rule(selection)
        self._set_swatch(rule.color if rule is not None else None)
        self._set_effect(rule.effect if rule is not None else None)

    def _rule(self, selection: Selection) -> ElementStyle | None:
        style = self._state.doc.style
        if self._part_scope:
            return style.parts.get(selection.part)
        return style.elements.get(selection.element_id)

    def _set_swatch(self, color: str | None) -> None:
        self._color_button.setText(color if color else _INHERIT)

    def _set_effect(self, effect: str | None) -> None:
        name = effect or _INHERIT
        self._effect.blockSignals(True)
        if self._effect.findText(name) < 0:
            self._effect.addItem(name)       # an unknown name round-trips
        self._effect.setCurrentText(name)
        self._effect.blockSignals(False)

    # -- writes ------------------------------------------------------------

    def _pick_color(self) -> None:
        selection = self._selection
        if selection is None:
            return
        rule = self._rule(selection)
        initial = QColor(rule.color) if rule is not None and rule.color \
            else QColor("black")
        picked = QColorDialog.getColor(initial, self, "Element color")
        if picked.isValid():
            self._commit_color(picked.name())
        else:
            self.sync()                      # cancelled: nothing changed

    def _commit_color(self, color: str | None) -> None:
        selection = self._selection
        if selection is None:
            return
        if self._part_scope:
            if selection.part is not None:
                self._state.execute(SetPartColor(selection.part, color))
            return
        self._write_elements(color=color)

    def _commit_effect(self) -> None:
        selection = self._selection
        if selection is None:
            return
        name = self._effect.currentText()
        effect = None if name == _INHERIT else name
        if self._part_scope:
            if selection.part is not None:
                self._state.execute(SetPartEffect(selection.part, effect))
            return
        self._write_elements(effect=effect)

    def _write_elements(self, color=..., effect=...) -> None:
        """ONE command for the whole family (rule 8 counts gestures):
        the head id carries the style, the rest ride as `segments`.

        The field being changed is merged over the head's CURRENT rule,
        so setting a colour never silently clears an effect. The head is
        the source, so a family that already disagrees converges on it —
        which is the only sane answer once segments are written together
        anyway."""
        ids = self._ids()
        if not ids:
            return
        current = self._state.doc.style.elements.get(ids[0], ElementStyle())
        self._state.execute(SetElementStyle(
            ids[0],
            ElementStyle(color=current.color if color is ... else color,
                         effect=current.effect if effect is ... else effect),
            segments=ids[1:]))

    def _clear_overrides(self) -> None:
        """The cheap reset rule 5 demands, on the whole family and in one
        undo entry.

        STYLE only. A nudge is a different intent living in a different
        part of the document, and folding it in would either make this
        two undo entries for one click (rule 8) or need a command that
        does not exist. Undo, or drag it back."""
        ids = self._ids()
        if ids:
            self._state.execute(SetElementStyle(ids[0], None,
                                                segments=ids[1:]))
