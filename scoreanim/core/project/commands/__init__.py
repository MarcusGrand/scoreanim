"""Undoable commands over the project document (CLAUDE.md rule 8).

A command is a pure transform ``apply(doc) -> doc`` on the immutable
ProjectDoc — it never mutates, and it raises CommandError on invalid
input. The UndoStack stores (command, doc_before, doc_after) triples;
undo/redo swap document values and never re-run ``apply``. Snapshots
are cheap: the doc is small intent-only frozen data with structural
sharing.

Drag gestures do NOT create a command per mouse-move: the UI previews
(apply against the committed doc, discard) and commits exactly one
command on release — see ui/app_state.py.

Split along the command-domain seams at the M4 exit audit (the single
module had grown past 950 lines — the no-monoliths rule): base.py the
contract, timing.py tempo/taps/swing, style.py rules and effect
params, stage.py presentation/texts/overlays, layout.py the
engraving-input commands, breaks.py the two break maps (split out of
layout.py when it passed 400 lines), undo.py the stack. This façade
re-exports every public name, so import sites are unchanged.
"""
from scoreanim.core.project.commands.base import Command, CommandError
from scoreanim.core.project.commands.breaks import SetPageBreak, SetSystemBreak
from scoreanim.core.project.commands.layout import (AddCondenseGroup,
                                                    AddStaffGroup,
                                                    ApplyScoreSetup,
                                                    EditCondenseGroup,
                                                    EditStaffGroup,
                                                    RemoveCondenseGroup,
                                                    RemoveStaffGroup,
                                                    SetElementsHidden,
                                                    SetLayoutOverride,
                                                    SetPartText)
from scoreanim.core.project.commands.stems import SetStemDirection
from scoreanim.core.project.commands.stage import (AddTempoOverlay,
                                                   EditStageText,
                                                   RemoveTempoOverlay,
                                                   SetHideEmptyStaves,
                                                   SetHideFirstSystem,
                                                   SetLyricsSize,
                                                   SetPresentationMode,
                                                   SetScoreScale,
                                                   SetStaffLineWidth,
                                                   SetVideoCanvas)
from scoreanim.core.project.commands.style import (ResetEffectSettings,
                                                   SetDefaultEffect,
                                                   SetEffectParam,
                                                   SetElementStyle,
                                                   SetFloorOpacity,
                                                   SetPartColor,
                                                   SetColorMode,
                                                   SetPartEffect,
                                                   SetPulseParam,
                                                   SetRevealMode,
                                                   SetVolumeParam)
from scoreanim.core.project.commands.timing import (AddSwingRegion,
                                                    AddTempoEvent,
                                                    AlignBeat,
                                                    ApplyTaps,
                                                    ImportTempoSetup,
                                                    MoveTempoEvent,
                                                    RemoveSwingRegion,
                                                    RemoveTapSession,
                                                    RemoveTempoEvent,
                                                    SetBeatLock,
                                                    SetGlobalSwing,
                                                    SetTempoFrom,
                                                    SetOffset,
                                                    SetSwingRegion)
from scoreanim.core.project.commands.undo import UndoStack

__all__ = [
    "AddCondenseGroup", "AddStaffGroup", "AddSwingRegion", "AddTempoEvent",
    "AddTempoOverlay", "AlignBeat", "ApplyScoreSetup", "ApplyTaps",
    "Command", "CommandError",
    "EditCondenseGroup", "EditStaffGroup", "EditStageText",
    "ImportTempoSetup", "MoveTempoEvent",
    "RemoveCondenseGroup", "RemoveStaffGroup", "RemoveSwingRegion",
    "RemoveTapSession", "RemoveTempoEvent", "RemoveTempoOverlay",
    "ResetEffectSettings",
    "SetBeatLock", "SetDefaultEffect", "SetEffectParam", "SetElementStyle",
    "SetElementsHidden",
    "SetFloorOpacity", "SetGlobalSwing", "SetHideEmptyStaves",
    "SetHideFirstSystem", "SetLyricsSize", "SetOffset", "SetPartColor", "SetPartEffect",
    "SetLayoutOverride", "SetPageBreak",
    "SetColorMode", "SetPartText", "SetPresentationMode", "SetPulseParam",
    "SetRevealMode", "SetScoreScale", "SetStaffLineWidth",
    "SetStemDirection", "SetSwingRegion", "SetTempoFrom",
    "SetSystemBreak", "SetVideoCanvas", "SetVolumeParam",
    "UndoStack",
]
