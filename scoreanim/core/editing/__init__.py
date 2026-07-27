"""Direct-edit policy (M3): pure, Qt-free decisions about what a
gesture on an element MEANS.

`text_route` answers "double-clicking this thing edits what, via which
existing command"; `nudge` answers "may this thing be dragged, and by
how much". Both are policy tables plus a little arithmetic, headless-
tested on synthetic inputs — the `core/selection/policy.py` shape.
"""
from scoreanim.core.editing.nudge import (COARSE_NUDGE, NUDGEABLE_KINDS,
                                          NUDGE_STEP, is_nudgeable,
                                          nudged_delta)
from scoreanim.core.editing.segments import (family_of, is_segment,
                                             source_of)
from scoreanim.core.editing.text_route import (TextRoute, TextTarget,
                                               route_for)

__all__ = ["COARSE_NUDGE", "NUDGEABLE_KINDS", "NUDGE_STEP", "TextRoute",
           "TextTarget", "family_of", "is_nudgeable", "is_segment",
           "nudged_delta", "route_for", "source_of"]
