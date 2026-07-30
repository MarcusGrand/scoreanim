"""In-place text editing (M3.1): double-click a text on the stage, type,
Enter commits.

An AFFORDANCE over machinery that already existed — every route lands in
a Phase 9 command (`core/editing/text_route.py` holds the routing policy
and explains each one). Nothing here adds document semantics.

Two things this module owns that are easy to get wrong:

**It is NOT selection.** D5 stands (ruling 2026-07-27): stage texts stay
unselectable, and nothing here writes `AppState.selection`. Double-click
asks a different question than a click does — "which editable text is
under the cursor" rather than "which object did the user pick" — so it
resolves through its own path, over both engraved TEXT elements and
stage texts. Selection is untouched by an edit.

**A gesture that changes nothing produces no undo entry** (rule 8 in the
direction people forget): opening an editor and closing it, or committing
the text it already had, executes no command at all.

It also owns `open_texts_dialog` — the list view of these same commands,
and the one dialog opener BACKLOG 9b could not rehome, because its data
is the current engraved layout and no component owned that until now.
"""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QObject, QPointF, Qt
from PySide6.QtWidgets import QGraphicsScene, QLineEdit

from scoreanim.core.editing import TextRoute, flat_part_order, route_for
from scoreanim.core.engraving.types import Layout
from scoreanim.core.project import (AddTempoOverlay, EditCondenseGroup,
                                    EditStageText, SetPartText,
                                    page_content_top)
from scoreanim.core.project.stage_config import (is_header_text,
                                                 seed_overlay_text)
from scoreanim.core.score.identity import ElementId, PartId
from scoreanim.render.items import ElementItem
from scoreanim.render.scene import ScoreScenes
from scoreanim.ui.app_state import AppState
from scoreanim.ui.stage_view import StageView
from scoreanim.ui.texts_dialog import TextsDialog

# Minimum width of the inline field, in viewport px. Some engraved texts
# are a few glyphs wide ("f", a rehearsal "A"), and an editor the size of
# its ink is unusable the moment you type a second character.
_MIN_EDITOR_WIDTH = 90


class _InlineField(QLineEdit):
    """Enter/focus-out commit, Esc cancels — the roadmap's contract.

    Esc is handled here rather than at the view so it never reaches
    `StageView.keyPressEvent`, which would deselect as well as cancel.
    """

    def __init__(self, on_commit, on_cancel, parent=None) -> None:
        super().__init__(parent)
        self._on_commit = on_commit
        self._on_cancel = on_cancel
        self.editingFinished.connect(self._on_commit)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            self._on_cancel()
            return
        super().keyPressEvent(event)


class InlineTextEditor(QObject):
    """Double-click → resolve → edit → one command.

    Bound per load (`bind`), the DocumentSync/SelectionController idiom:
    a re-engrave rebuilds every item, so any open editor is closed and
    the cached layout replaced.
    """

    def __init__(self, app_state: AppState, view: StageView,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = app_state
        self._view = view
        self._scenes: ScoreScenes | None = None
        self._layout: Layout | None = None
        self._parts: tuple = ()
        self._field: _InlineField | None = None
        self._target = None
        self._initial = ""

    # -- lifecycle ---------------------------------------------------------

    def bind(self, scenes: ScoreScenes, layout: Layout, parts: tuple) -> None:
        self.close()
        self._scenes = scenes
        self._layout = layout
        self._parts = tuple(parts)

    @property
    def editing(self) -> bool:
        return self._field is not None

    def close(self) -> None:
        """Tear the editor down without committing."""
        field, self._field = self._field, None
        self._target = None
        if field is not None:
            field.hide()
            field.deleteLater()

    # -- the Texts… dialog (the list view of the same commands) -------------

    def open_texts_dialog(self) -> None:
        if self._layout is None:
            return
        # band = the free space above the top staff, re-derived from the
        # CURRENT engraved layout (runtime data for the header refit —
        # the doc stores intent only)
        tempo_elements = tuple(el for el in self._layout.elements
                               if el.text_class == "tempo")
        TextsDialog(self._state, band=self._band(),
                    tempo_elements=tempo_elements,
                    parent=self._view.window()).exec()

    # -- the gesture -------------------------------------------------------

    def edit_at(self, scene_pos: QPointF,
                scene: QGraphicsScene | None = None) -> bool:
        """Open an editor over the editable text at this point, if any.
        Returns whether one opened (the tests' handle on 'nothing here')."""
        self.close()
        if self._scenes is None:
            return False
        found = self._text_item_at(scene_pos, scene)
        if found is None:
            return False
        item, eid = found
        target = route_for(item.identity, eid, self._text_class(eid),
                           self._condensed())
        if target is None:
            return False
        initial = self._current_content(target, eid)
        if initial is None:
            return False
        self._open(target, item, initial)
        return True

    def _text_item_at(self, scene_pos: QPointF,
                      scene: QGraphicsScene | None
                      ) -> tuple[ElementItem, ElementId] | None:
        """The topmost item whose real ink is under the point.

        Deliberately NOT the selection policy: that one ranks musical
        objects and filters stage texts out entirely. This asks only
        'what text did the pointer land on', so it takes the frontmost
        item whose own ink contains the point — no tolerance rect, since
        a text is a solid glyph run rather than a hairline, and an
        editor opening on a neighbour would be worse than not opening."""
        if scene is None:
            scene = self._scenes.scenes[0] if self._scenes.scenes else None
        if scene is None:
            return None
        for hit in scene.items(scene_pos):
            item = _element_parent(hit)
            if item is None:
                continue
            eid = getattr(item, "element_key", None)
            if eid is not None:
                return item, eid
        return None

    def _text_class(self, eid: ElementId) -> str | None:
        if self._layout is None:
            return None
        for el in self._layout.elements:
            if el.identity.element_id == eid:
                return el.text_class
        return None

    def _element(self, eid: ElementId):
        if self._layout is None:
            return None
        return next((el for el in self._layout.elements
                     if el.identity.element_id == eid), None)

    def _stage_text(self, eid: ElementId):
        return next((t for t in self._state.doc.stage.texts
                     if t.element_id == str(eid)), None)

    def _band(self) -> float:
        return page_content_top(self._layout)

    def _condensed(self) -> dict[PartId, int]:
        """Each condense group's kept part → the group's index. A merged
        staff's label names the group, so it edits the group (M7)."""
        return {group.parts[0]: i
                for i, group in enumerate(self._state.doc.condense_groups)}

    def _current_content(self, target, eid: ElementId) -> str | None:
        """What the field starts with — always what is ON SCREEN now."""
        if target.route is TextRoute.STAGE_TEXT:
            text = self._stage_text(eid)
            return None if text is None else text.content
        element = self._element(eid)
        if element is None or not element.glyph.texts:
            return None
        # the engraved ink's own text, via the same reader the overlay
        # seed uses (music glyphs mapped to text equivalents)
        return seed_overlay_text(element).content

    # -- the editor widget -------------------------------------------------

    def _open(self, target, item: ElementItem, initial: str) -> None:
        rect = self._view.mapFromScene(
            item.sceneBoundingRect()).boundingRect()
        rect.setWidth(max(rect.width(), _MIN_EDITOR_WIDTH))
        field = _InlineField(self._commit, self.close, self._view.viewport())
        field.setText(initial)
        field.setGeometry(rect)
        field.selectAll()
        field.show()
        field.setFocus(Qt.FocusReason.MouseFocusReason)
        self._field = field
        self._target = target
        self._initial = initial

    def _commit(self) -> None:
        field, target = self._field, self._target
        # clear FIRST: hiding the field fires editingFinished again on
        # some platforms, and a re-entrant commit would double the edit
        self._field = None
        self._target = None
        if field is None or target is None:
            return
        content = field.text()
        field.hide()
        field.deleteLater()
        if content == self._initial:
            return                       # no change, no command, no undo entry
        self._execute(target, content)

    def _execute(self, target, content: str) -> None:
        if target.route is TextRoute.PART_LABEL:
            override = self._state.doc.text_overrides.get(target.part)
            name = override.name if override is not None else None
            abbrev = override.abbreviation if override is not None else None
            if target.field == "name":
                name = content
            else:
                abbrev = content
            self._state.execute(SetPartText(
                target.part, name, abbrev,
                tuple(p.part_id for p in self._parts)))
            return

        if target.route is TextRoute.CONDENSE_LABEL:
            groups = self._state.doc.condense_groups
            if target.group is None or target.group >= len(groups):
                return                   # the doc moved under the editor
            group = groups[target.group]
            edited = (replace(group, name=content) if target.field == "name"
                      else replace(group, abbreviation=content))
            # the SCORE's part order, not the condensed one this build
            # reports: the group still names the parts it absorbed, and the
            # command validates against what it is handed
            self._state.execute(EditCondenseGroup(
                target.group, edited,
                flat_part_order(tuple(p.part_id for p in self._parts),
                                [g.parts for g in groups])))
            return

        if target.route is TextRoute.STAGE_TEXT:
            text = self._stage_text(target.element_id)
            if text is None:
                return
            # the header block re-fits into the band; an overlay sits at
            # its engraved position and must never rescale with it
            band = self._band() if is_header_text(text) else None
            self._state.execute(EditStageText(
                text.element_id, replace(text, content=content), band))
            return

        element = self._element(target.element_id)
        if element is None:
            return
        # hide the engraved ink + add its replacement: ONE undo step
        self._state.execute(AddTempoOverlay(
            element.identity.element_id,
            replace(seed_overlay_text(element), content=content)))


def _element_parent(item) -> ElementItem | None:
    node = item
    while node is not None and not isinstance(node, ElementItem):
        node = node.parentItem()
    return node
