"""The colour tokens for the app's one dark theme.

Plain strings, no Qt: this module is the single place a colour is
written down. Everything that paints — the QPalette, the app-wide QSS,
the waveform, the two lanes, the stage letterbox — reads a name from
here. If a colour is needed and no name fits, add a name here rather
than a hex literal at the call site.

The nine names under "the theme" are the ones the design sets. The rest
are working colours picked from the same family, so a lane never drifts
away from the panels around it.
"""
from __future__ import annotations

# -- the theme ------------------------------------------------------------

WINDOW = "#1e1f22"      # the app's ground: main window, letterbox
PANEL = "#26272b"       # a raised surface: docks, toolbar, buttons
INSET = "#17181b"       # a sunken surface: lanes, text fields, lists
BORDER = "#3a3b40"      # the line between two surfaces
TEXT = "#d6d7db"        # normal text and icons
DIM = "#8e909c"         # secondary text, hints, axis labels
ACCENT = "#ffcc66"      # the glow colour — used sparingly, for "active"
PLAYHEAD = "#ffb454"    # the playhead line in every time view
WAVEFORM = "#5b87b8"    # the audio peaks

# -- working colours, same family -----------------------------------------

HOVER = "#303138"       # a surface under the pointer
PRESSED = "#33343c"     # a surface being clicked
ACCENT_HOVER = "#ffd782"    # the accent-filled button under the pointer
ACCENT_PRESSED = "#e6b855"  # that button being clicked
DISABLED = "#5a5c66"    # text of a control that cannot be used
HIGHLIGHT = "#3f4652"   # selected row in a list or menu (quiet on
                        # purpose: the accent is reserved for "active")

# The floating stage controls (D2) are the only chrome that sits ON the
# score, so they are see-through: the same surfaces as everywhere else
# with an alpha in front (#AARRGGBB — Qt reads it, and so does QSS).
OVERLAY = "#d626272b"          # the floating panel's ground: PANEL at 84%
OVERLAY_BORDER = "#d63a3b40"   # its edge: BORDER, same alpha
OVERLAY_HOVER = "#f0303138"    # a button in it under the pointer

GRID = "#2e3037"        # lane grid lines and the waveform's midline
WAVEFORM_SOFT = "#7fa8d4"   # the RMS body inside the peaks
BAR_LINE = "#5b6472"    # a barline in the ticks lane
SUB_LINE = "#3d424c"    # a subdivision line
SUB_LINE_STRONG = "#4b5563"  # a subdivision that lands on a whole beat
HANDLE = "#7fb8e8"      # the grid line under the pointer, or dragging
HANDLE_SELECTED = "#6fa8d0"  # the line the Tempo field is aimed at
LOCK = "#f2761f"        # a locked grid line: warmer than the playhead
                        # it sits next to
TEMPO_LINE = "#c46a6a"  # the tempo curve
TEMPO_DOT = "#e08585"   # a tempo event on that curve
