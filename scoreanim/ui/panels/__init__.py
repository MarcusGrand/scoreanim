"""Inspector section bodies (M4.8): each panel is one section's widget,
owning its controls' commit handlers and blockSignals resync — the
inspector composes them and delegates `sync_from_document`.

SelectionPanel (M2.5) is the exception that proves the rule: it is
driven by transient selection state, so it subscribes to
`AppState.selection_changed` itself and has no document resync.

BreakOverridesList (M6.7) and DeletedElementsList are section bodies of
the LAYOUT ZONE rather than the inspector — same contract, different
dock: the zone composes them and delegates `sync_from_document`."""
from scoreanim.ui.panels.break_overrides import BreakOverridesList
from scoreanim.ui.panels.deleted_elements import DeletedElementsList
from scoreanim.ui.panels.effects_panel import EffectsPanel
from scoreanim.ui.panels.page_colors import PageColorsPanel
from scoreanim.ui.panels.video_canvas import VideoCanvasPanel
from scoreanim.ui.panels.selection_panel import SelectionPanel
from scoreanim.ui.panels.selection_style import SelectionStyleControls

__all__ = ["BreakOverridesList", "DeletedElementsList", "EffectsPanel",
           "PageColorsPanel", "SelectionPanel", "SelectionStyleControls",
           "VideoCanvasPanel"]
