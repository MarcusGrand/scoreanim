"""Inspector section bodies (M4.8): each panel is one section's widget,
owning its controls' commit handlers and blockSignals resync — the
inspector composes them and delegates `sync_from_document`."""
from scoreanim.ui.panels.effects_panel import EffectsPanel

__all__ = ["EffectsPanel"]
