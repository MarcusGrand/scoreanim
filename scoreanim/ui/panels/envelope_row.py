"""One `Envelope` knob: its canvas, the header that opens it, and the
one command a drag on it commits.

Its own module because it is its own gesture. Every other knob is a
widget with a value; this one is a canvas with a shape, edited with the
mouse, spread over six document keys — so `KnobGroup` builds one of
these and delegates, instead of growing a fifth set of dictionaries.

The gesture is the live field's contract with a mouse instead of a
keyboard (PATTERNS, "a number field previews as you type"): every move
of the drag previews and the release commits one undo entry, both
through the same `_command`, so the two can never ask for different
edits. It reads the COMMITTED document, because `doc` hands the canvas
back its own preview and a guard reading that would never commit.

The canvas and the number boxes beside it are two views of one set of
values. `resync` is what keeps them equal, in both directions: a drag
previews, the preview comes back as a document change, and every view
of those values is written from the document again — except the one
being dragged, which owns itself until the mouse comes up.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from scoreanim.core.animation import EnvelopeSpec, clamp_spec
from scoreanim.core.project import Command, ProjectDoc
from scoreanim.ui.app_state import AppState
from scoreanim.ui.collapsible import CollapsibleSection
from scoreanim.ui.envelope_editor import EnvelopeEditor
from scoreanim.ui.panels.knob_types import Envelope, MultiKnobStore, Value


class EnvelopeRow:
    """The canvas for one envelope knob, and everything it commits."""

    def __init__(self, knob: Envelope, store: MultiKnobStore, state: AppState,
                 param: Callable[[ProjectDoc, str], Any],
                 on_change: Callable[[], None]) -> None:
        self._knob = knob
        self._store = store
        self._state = state
        # The group's own reader, so a value it defaults or forces reads
        # the same on the picture as it does in the boxes.
        self._param = param
        self._on_change = on_change
        self._live = False           # a drag of ours is previewing
        self.canvas = EnvelopeEditor(self.spec(state.doc))
        self.canvas.setToolTip(knob.tooltip)
        self.canvas.changed.connect(lambda spec: self._edit(spec,
                                                            commit=False))
        self.canvas.committed.connect(lambda spec: self._edit(spec,
                                                              commit=True))
        # Closed to start with: the block opens showing the numbers, and
        # the picture is there for whoever wants to draw the shape
        # instead (Marcus, 2026-08-04).
        self.section = CollapsibleSection(knob.title)
        self.section.set_content(self.canvas)
        self.section.set_expanded(False)

    # -- what it is showing ---------------------------------------------------

    def spec(self, doc: ProjectDoc) -> EnvelopeSpec:
        """The shape the six keys describe, as the effect will play it.
        Clamped, because the canvas draws what the score does — a shape
        stored out of order is put in order on the way to the ink too."""
        knob = self._knob
        return clamp_spec(EnvelopeSpec(
            attack=float(self._param(doc, knob.attack)),
            sustain=float(self._param(doc, knob.sustain)),
            swell_on=bool(self._param(doc, knob.swell_on)),
            swell_pos=float(self._param(doc, knob.swell_pos)),
            swell_level=float(self._param(doc, knob.swell_level)),
            release=float(self._param(doc, knob.release))))

    def resync(self, doc: ProjectDoc) -> None:
        """Show what the document says; a drag keeps its shape."""
        self.canvas.set_spec(self.spec(doc))

    def dragging(self) -> bool:
        """A handle is being held — the block must not be hidden."""
        return self.canvas.dragging()

    # -- one gesture, one undo entry -----------------------------------------

    def _edit(self, spec: EnvelopeSpec, commit: bool) -> None:
        """A move previews, the release commits. Nothing changed means
        the preview is dropped rather than turned into an entry, which
        is what makes a press that goes nowhere not an edit."""
        command = self._command(spec)
        if command is None:
            if self._live and self._state.doc is not self._state.committed:
                self._state.cancel_preview()
            self._live = False
        elif commit:
            self._live = False           # clear first: the commit lands
            self._state.commit(command)  # back here as a resync
        else:
            self._live = True
            self._state.preview(command)
        self._on_change()

    def _command(self, spec: EnvelopeSpec) -> Command | None:
        """The one command the whole shape becomes: every key the drag
        moved, written together so undo takes them together (rule 8)."""
        knob, doc = self._knob, self._state.committed
        wanted: Mapping[str, Value] = {
            knob.attack: spec.attack, knob.sustain: spec.sustain,
            knob.swell_on: spec.swell_on, knob.swell_pos: spec.swell_pos,
            knob.swell_level: spec.swell_level, knob.release: spec.release}
        moved = {key: value for key, value in wanted.items()
                 if not _same(value, self._param(doc, key))}
        return self._store.command_many(moved) if moved else None


def _same(value: Value, stored: Any) -> bool:
    """Is this what the document already holds? Numbers are compared
    with the number fields' own slack; a flag is a flag."""
    if isinstance(value, bool) or isinstance(stored, bool):
        return bool(value) is bool(stored)
    return abs(float(value or 0.0) - float(stored or 0.0)) < 1e-9
