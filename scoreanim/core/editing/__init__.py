"""Direct-edit policy (M3): pure, Qt-free decisions about what a
gesture on an element MEANS.

`text_route` answers "double-clicking this thing edits what, via which
existing command"; `nudge` answers "may this thing be dragged, and by
how much"; `deletion` answers "may this thing be deleted, and what has
been"; `stem_flip` answers "which stem does F flip, and which way is
it pointing now"; `envelope_drag` answers "what does dragging this
handle on an envelope's picture do". All are policy tables plus a little
arithmetic, headless-tested on synthetic inputs — the
`core/selection/policy.py` shape.
"""
from scoreanim.core.editing.deletion import (DELETABLE_KINDS, DeleteAction,
                                             deleted_families, deleted_ids,
                                             is_deletable)
from scoreanim.core.editing.envelope_drag import (Box, Handle, drag,
                                                  drag_attack, drag_release,
                                                  drag_sustain, drag_swell,
                                                  frac_of, handle_at,
                                                  handle_points, level_of,
                                                  x_of, y_of)
from scoreanim.core.editing.nudge import (COARSE_NUDGE, NUDGEABLE_KINDS,
                                          NUDGE_STEP, is_nudgeable,
                                          nudged_delta)
from scoreanim.core.editing.segments import (family_of, is_segment,
                                             source_of)
from scoreanim.core.editing.stem_flip import (FLIPPABLE_KINDS, FlipAction,
                                              is_flippable, stem_of)
from scoreanim.core.editing.text_route import (TextRoute, TextTarget,
                                               flat_part_order, route_for)

__all__ = ["Box", "COARSE_NUDGE", "DELETABLE_KINDS", "DeleteAction",
           "FLIPPABLE_KINDS", "FlipAction", "Handle",
           "NUDGEABLE_KINDS", "NUDGE_STEP", "TextRoute",
           "TextTarget", "deleted_families", "deleted_ids", "drag",
           "drag_attack", "drag_release", "drag_sustain", "drag_swell",
           "family_of", "frac_of", "handle_at", "handle_points",
           "is_deletable", "is_flippable", "is_nudgeable", "is_segment",
           "flat_part_order", "level_of", "nudged_delta", "route_for",
           "source_of", "stem_of", "x_of", "y_of"]
