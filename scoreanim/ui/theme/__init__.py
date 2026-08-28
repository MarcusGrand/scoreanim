"""The app's one dark theme: the colour tokens, and how they are applied.

`palette` holds the names, `stylesheet` the QSS built from them, and
`theme.apply_theme(app)` puts the lot on the QApplication. Nothing else
in the UI sets a colour of its own — a view that paints (the waveform,
the lanes, the stage) imports the tokens.
"""
from scoreanim.ui.theme import palette
from scoreanim.ui.theme.stylesheet import stylesheet
from scoreanim.ui.theme.theme import apply_theme, build_palette

__all__ = ["palette", "apply_theme", "build_palette", "stylesheet"]
