"""One press, one owner.

The stage view has a single probe slot (`nudge_probe`) and one set of
drag signals. This router fans them out so the onset cursor and the
nudge share the stage without the view learning about either: probes
run in order, and the first to claim the press owns start, move and
finish for the whole gesture. A handler is anything with the nudge's
gesture surface — probe(scene_pos, scene), start(scene_pos, scene),
move(delta), finish(delta).
"""
from __future__ import annotations

from typing import Sequence


class DragRouter:
    def __init__(self, handlers: Sequence) -> None:
        self._handlers = tuple(handlers)
        self._owner = None

    def probe(self, scene_pos, scene=None) -> bool:
        for handler in self._handlers:
            if handler.probe(scene_pos, scene):
                self._owner = handler
                return True
        self._owner = None
        return False

    def start(self, scene_pos, scene=None) -> None:
        if self._owner is not None:
            self._owner.start(scene_pos, scene)

    def move(self, delta) -> None:
        if self._owner is not None:
            self._owner.move(delta)

    def finish(self, delta) -> None:
        owner, self._owner = self._owner, None
        if owner is not None:
            owner.finish(delta)
