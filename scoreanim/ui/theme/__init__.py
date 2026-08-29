"""The app's one dark theme: the colour tokens, and how they are applied.

`palette` holds the names, `stylesheet` the QSS built from them, and
`theme.apply_theme(app)` puts the lot on the QApplication. Nothing else
in the UI sets a colour of its own — a view that paints (the waveform,
the lanes, the stage) imports the tokens.

`icons` is the same idea for line art: vendored Lucide SVGs, tinted
from the same tokens, so an icon matches the text beside it.
"""
from scoreanim.ui.theme import icons, palette
from scoreanim.ui.theme.stylesheet import stylesheet
from scoreanim.ui.theme.theme import apply_theme, build_palette

__all__ = ["palette", "icons", "apply_theme", "build_palette", "stylesheet"]
