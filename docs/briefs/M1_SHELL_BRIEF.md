# M1 Shell planning brief — UI reorganization (2026-07-24)

Written by a planning session, 2026-07-24, against ROADMAP.md's M1
milestone (the scope authority — what M1 IS; this brief is how it gets
built). Goal, from the roadmap: professional chrome in the
Dorico/Cubase/Final Cut layout — stage central, **right-hand inspector
dock** with collapsible labeled panels, **lower zone** formalizing the
timeline area, menus reorganized around it. **No new capabilities**:
every existing action, command, and shortcut keeps working; this
milestone only re-homes them, and decomposes the `ui/main_window.py`
monolith (1167 lines — the named worst offender of the no-monoliths
rule) into focused modules.

**Boundaries (roadmap, restated as law for this build):** commands,
AppState semantics, `core/`, and `render/` are untouched. Widgets
observing the document keep the exact block-signals/diff idiom of
`_on_document_changed`. Every prefix-in-spinbox is replaced by a
labeled field. QSettings persists window/dock geometry — UI state,
never document state (rule 5 untouched).

**Rulings recorded this session (Marcus, 2026-07-24):**

- **Lower zone container = bottom QDockWidget** (not a splitter pane):
  matches the inspector, `toggleViewAction()` lands in the View menu
  for free, and one `saveState`/`restoreState` pair persists both
  docks. Dock features restricted (no close via titlebar float chrome —
  it should feel like a fixed zone with a View toggle).
- **The top toolbar stays, slimmed**: ◀ page-label ▶ and Fit. "Open
  Score…" drops off it (File menu covers it). The page/system readout
  stays window-owned, next to the stage it describes.
- **Time fields live on the transport strip** (Marcus, 2026-07-24,
  during the M1.3 build — supersedes §1c's inspector targets for
  three rows): everything time-related — Tempo, Offset, Swing — sits
  in the lower zone with the transport it configures, as labeled
  fields on the strip (prefixes retired there, not in M1.4). The
  strip owns their commit handlers and a `sync_from_document(doc)`
  resync the window calls. M1.4's *Playback & Sync* section
  accordingly holds only the Follow/Systems toggles; Floor opacity
  and Sweep proceed to *Appearance & Effects* unchanged.

## 1. Current state — the complete re-homing inventory

Read from `ui/main_window.py` end to end (2026-07-24, post-alpha
main). This is the "no capability lost" checklist: at exit, every row
must be reachable and functioning in its new home.

### 1a. Actions

| Current action | Shortcut | Wiring today | New home |
|---|---|---|---|
| Open Score… | Ctrl+O | `_open_dialog` | File (off the toolbar) |
| Open Project… | Ctrl+Shift+O | `_open_project_dialog` | File |
| Save Project | Ctrl+S | `save_project`; window-level action | File |
| Save Project As… | std SaveAs | `save_project_as` | File |
| Export Video… | Ctrl+E | `_open_export_dialog`; disabled until load; pauses playback first | File |
| Undo / Redo | Ctrl+Z / Shift+Ctrl+Z | `app_state.undo/redo`; dynamic "Undo <cmd>" text; window-level | Edit |
| Texts… | — | `_open_texts_dialog`; disabled until load | Edit |
| Fit | Ctrl+0 | `view.fit` | View + slim toolbar |
| ◀ / ▶ | PgUp / PgDn | `_step(∓1)` — mode-aware (pages / systems) | View + slim toolbar |
| page label "n/N" · "sys n/N" | — | QLabel fed by `show_page`/`show_system` | slim toolbar (window-owned) |
| Open Audio… | — | `_open_audio_dialog` | Playback menu |
| Import Tempo… | — | `_open_tempo_dialog` | Playback menu |
| Reload Tempo | F5 | `_reload_tempo`; window-level | Playback menu |
| ▶ Play / ⏸ Pause | Space | `playback.toggle_play`; window-level; text flips in `_on_playing` | transport strip + Playback menu (one QAction) |
| Follow (checkable) | — | `playback.set_follow` — transient controller state, NOT doc intent | inspector *Playback & Sync* + Playback menu (one QAction) |
| Systems (checkable) | — | `SetPresentationMode` command; blockSignals-resynced | inspector *Playback & Sync* |
| Sweep (checkable) | — | `SetRevealMode` command; blockSignals-resynced | inspector *Appearance & Effects* |
| ● Arm Taps (checkable) | Shift+T | `tap_recorder.set_armed`; window-level; auto-unchecked on pause via `_on_playing` | transport strip |
| Tap | T | `tap_recorder.tap`; window-level ONLY — no visible widget today | transport strip (visible button; shortcut unchanged) |

### 1b. Parts menu → **Score** menu (renamed, content preserved)

Dynamic, rebuilt per load in `_build_parts_menu`. Static head: **Score
Setup…**, **Staff Groups…**, **Part Names…**, **Hide Empty Staves**
(checkable → `SetHideEmptyStaves`, resynced via `_hide_staves_action`).
Then one submenu per part: 7 color swatches (icon pixmaps) + **Custom…**
(QColorDialog; cancel restores check state via `_sync_styles`) + **No
Color** → `SetPartColor`; an effect radio group enumerated from
`PRESETS` → `SetPartEffect`. Check-state registries
`_part_color_actions` / `_part_effect_actions`, synced in
`_check_part_menu` with the blockSignals idiom. All of it survives
as-is under the new **Score** menu name until M3/M4 re-home per-part
color/effect (roadmap: "keeping the per-part color/effect submenus").

### 1c. Prefix-in-spinbox widgets — all four retire into labeled fields

| Spinbox | Prefix today | Commit path (unchanged) | Inspector row |
|---|---|---|---|
| `_bpm_spin` | `"bpm "` | `_commit_bpm` → `MoveTempoEvent` on the first tempo event | *Playback & Sync* → **Tempo** (bpm) |
| `_offset_spin` | `"offset "` (+ `" s"` suffix) | `_commit_offset` → `SetOffset` | *Playback & Sync* → **Offset** (keeps the `" s"` suffix — units-as-suffix stays; only prefixes retire) |
| `_swing_spin` | `"swing "` | `_commit_swing` → `SetGlobalSwing(value, end_beat)` | *Playback & Sync* → **Swing** |
| `_floor_spin` | `"floor "` | `_commit_floor` → `SetFloorOpacity` | *Appearance & Effects* → **Floor opacity** |

Shared wiring, preserved verbatim: `setKeyboardTracking(False)`,
commit-on-`editingFinished`, epsilon no-op guard, blockSignals resync
in `_on_document_changed`. Only the widgets move (roadmap: "Same
commit-on-editingFinished command wiring as today").

### 1d. Transport widgets → transport strip

- `_slider`: `sliderMoved` → seek; `valueChanged` → `_on_slider_value`
  (keyboard/page-step seeks, guarded by `isSliderDown`); blockSignals
  range/value update inside `_on_time`.
- `_time_label`: `" m:ss.d / m:ss.d "`, formatted by the local `fmt`.

### 1e. Signal connections the decomposition must preserve

From `__init__`: `tap_recorder.status → statusBar`,
`.session_finished → _on_tap_session`; `peaks.progress/.finished →
app_state.set_peaks`, `.failed → _on_peaks_failed`;
`playback.page_changed/.system_changed → _on_page_followed /
_on_system_followed` (routed by `_applied_mode`), `.status_message →
statusBar`, `.time_changed → _on_time`, `.playing_changed →
_on_playing`, `.duration_changed → app_state.axis.set_duration`;
`app_state.seek_requested → playback.seek`, `.document_changed →
_on_document_changed`, `.status → statusBar`. The status bar stays on
the window; extracted components signal through it, never own one.

### 1f. Non-widget machinery to relocate (the no-monolith math)

- Load pipeline (~330 lines): `open_score`, `open_project`,
  `_load_score`, `_reengrave`, `_engrave_and_wire`, plus the
  `_applied_groups/_applied_text_overrides/_applied_hide_empty/
  _applied_condense` engrave-diff caches, the `_last_overflow` →
  Score-Setup-on-open trigger, the `.tempo` sidecar auto-import, and
  the timing status line.
- Document sync (~150 lines): `_sync_styles` / `_sync_stage` /
  `_sync_hidden` with their applied caches (`_applied_colors`,
  `_applied_overrides`, `_applied_floor`, `_applied_stage_texts`,
  `_applied_hidden`).
- Pure helpers embedded in the window: `fmt` (time), 
  `_initial_tempo_event`, `_global_swing_ratio`; `_timing_config`
  (THE shared live/export timing construction — must stay one
  expression wherever it lands).
- Stays in the window (it IS window routing): `show_page`,
  `show_system`, `_step`, `_show_current`, `_sync_presentation_mode`,
  `_band_by_system`, `closeEvent`, save/save-as.

## 2. Target module map

The roadmap names `ui/inspector.py`, `ui/transport.py`, and "a thinner
window" — **flag: that split alone leaves an ~800-line window**, so the
no-monoliths rule (~400-line signal) expands it to:

| Module | Responsibility | ~lines |
|---|---|---|
| `ui/main_window.py` | composition root; page/system routing; open/save/close; `_on_document_changed` dispatch | ≤400 |
| `ui/inspector.py` | right QDockWidget; 3 collapsible sections; labeled fields; commit handlers; `sync_from_document(doc)` (blockSignals idiom) | ~250 |
| `ui/collapsible.py` | `CollapsibleSection` widget (header toggle + content; Qt has none built in) | ~60 |
| `ui/transport.py` | `TransportStrip` (play, slider, time, tap controls) + `LowerZone` bottom QDockWidget (strip above waveform/tempo lane; internal splitter keeps lane heights user-adjustable) | ~180 |
| `ui/menus.py` | static File/Edit/View/Score/Playback construction; the slim toolbar; window-level shortcut registration (undo, redo, save, play, reload-tempo, arm-taps, tap) | ~180 |
| `ui/parts_menu.py` | dynamic per-part color/effect submenu builder + check-state sync (`_build_parts_menu`, `_check_part_menu`, `_pick_part_color`) | ~160 |
| `ui/score_loader.py` | engrave→decompose→join→wire pipeline; returns a `LoadedScore` bundle (scenes, applier, animation inputs, parts, bands, warnings, overflow flag) | ~220 |
| `ui/document_sync.py` | styles/stage/hidden diff-sync + applied caches | ~170 |
| `ui/readouts.py` | pure helpers: time format, initial-tempo-event, global-swing-ratio — headless-tested | ~50 |

Interfaces stay narrow: components receive `app_state` (and the
playback controller where needed) and expose plain methods/signals; no
component reaches into another. Existing views (`stage_view`,
`waveform`, `tempo_lane`) are re-parented, not modified.

## 3. Tasks

Work on branch `beta/m1-shell` (the `v0.1-alpha` tag exists — verified
2026-07-24). Commit per task; the app must launch and the suite stay
green after every task, so each split is a working checkpoint.

- **M1.0 Housekeeping: packaging fix + branch.** The
  `[tool.setuptools] packages = ["scoreanim"]` fix is already in the
  working tree, uncommitted. Before committing, upgrade it to
  `[tool.setuptools.packages.find] include = ["scoreanim*"]` — the
  literal list fixes `pip install -e .` but a NON-editable
  `pip install .` would ship only the top-level package and silently
  omit `scoreanim.core`, `scoreanim.ui`, etc. (setuptools exact lists
  don't recurse); add the missing trailing newline. Then branch
  `beta/m1-shell`. **Verify:** in a fresh venv, `pip install -e .`
  then `python -c "import scoreanim.core.engraving.verovio"`; also
  `pip install .` into a second throwaway venv imports the same module
  (proves the find-directive form); `pytest` green.
- **M1.1 Pure readout helpers → `ui/readouts.py`.** Move `fmt` (time
  formatting), `_initial_tempo_event`, `_global_swing_ratio` into a
  Qt-free module; window imports them. **Verify:** new headless tests
  (negative/zero/hour-ish times; empty-events → None → DEFAULT_BPM
  display; no-regions → 0.5 swing; multi-region → first ratio);
  `pytest` green; app runs unchanged.
- **M1.2 `ui/collapsible.py`.** `CollapsibleSection(title)`: header
  QToolButton (arrow indicator) toggling a content widget; expanded
  state is per-section UI state (QSettings-persisted with the rest of
  M1.8). **Verify:** offscreen test (`QT_QPA_PLATFORM=offscreen`):
  construct, toggle, content visibility flips.
- **M1.3 Lower zone → `ui/transport.py`.** `TransportStrip` (Play,
  slider, time label, ● Arm Taps, visible Tap button) above
  waveform + tempo lane, inside a bottom QDockWidget; internal
  splitter between the lanes preserves height adjustability the old
  three-way splitter gave. Central widget becomes the stage alone;
  the bottom QToolBar is deleted; Open Audio/Import Tempo/Reload
  Tempo actions move to the (M1.5) Playback menu but keep working
  from their current handlers meanwhile. **Verify:** run the app —
  play, drag-seek, keyboard-step the slider, arm taps, tap; Space /
  T / Shift+T / F5 fire with focus anywhere (window-level
  registration intact); pausing still disarms taps; suite green.
- **M1.4 Inspector → `ui/inspector.py` + `ui/collapsible.py`.** Right
  QDockWidget, three sections per the roadmap: *Playback & Sync*
  (Tempo, Offset, Swing as QFormLayout labeled rows + Follow/Systems
  toggles), *Appearance & Effects* (Floor opacity + Sweep), *Selection*
  ("Nothing selected" placeholder for M2). Commit handlers and the
  `sync_from_document(doc)` resync move with the widgets, wiring
  unchanged (§1c). **Verify:** `grep -rn "setPrefix" scoreanim/`
  returns nothing; edit each field → the correct command name appears
  in the Edit-menu Undo text; undo restores the field's displayed
  value; a resync never re-executes a command (undo stack depth
  unchanged by document_changed passes).
- **M1.5 Menus + slim toolbar → `ui/menus.py`.** The roadmap's five
  menus: **File** (open score/project, save, save-as, export) ·
  **Edit** (undo, redo, Texts…) · **View** (Fit, ◀, ▶, Inspector
  toggle, Lower Zone toggle — the docks' `toggleViewAction()`s) ·
  **Score** (renamed Parts — §1b) · **Playback** (Play, Follow, Open
  Audio…, Import Tempo…, Reload Tempo). Slim toolbar: ◀ page-label ▶ ·
  Fit. Window-level shortcut registration preserved for every action
  in §1a marked window-level. **Verify:** click-through of every menu
  item + full shortcut sweep (Ctrl+O/Ctrl+Shift+O/Ctrl+S/Ctrl+E/
  Ctrl+Z/Shift+Ctrl+Z/Ctrl+0/PgUp/PgDn/F5/Space/T/Shift+T) with focus
  on the stage, the inspector, and the lower zone.
- **M1.6 Score-menu part submenus → `ui/parts_menu.py`.** Extract the
  dynamic builder + check sync + custom-color picker; rebuilt per load
  exactly as today. **Verify:** tint a part from the Score menu, undo;
  set an effect, undo; Custom… then cancel restores check state;
  checkmarks track undo/redo of part color and effect.
- **M1.7 Loader + document-sync split → `ui/score_loader.py`,
  `ui/document_sync.py`.** The §1f machinery: loader returns a
  `LoadedScore` bundle the window installs; `DocumentSync` owns the
  applied caches and the styles/stage/hidden diffs; the re-engrave
  trigger diff (groups/labels/hide/condense) and the ~0.6 s
  execute-not-preview constraint keep their current comments and
  behavior; overflow-at-open still raises the Score Setup dialog;
  sidecar auto-import unchanged. **Verify:** load complex2 (setup
  dialog appears), apply setup choices — one undo step; rename a part
  (score shifts, one undo step); toggle Hide Empty Staves on bigband1
  (one undo step, re-engrave preserves zoom/page); load testscore with
  its `.tempo` sidecar (auto-imports as a command);
  `wc -l scoreanim/ui/*.py` shows no file ≥ ~400.
- **M1.8 QSettings persistence.** `saveGeometry`/`saveState` on
  accepted close (not on cancel), restore in `__init__`; section
  expanded-states included. First-run default grows to fit the right
  dock (today's 1000×1200 is too narrow — pick ~1400×1000 and eyeball
  it). UI state only — nothing enters the document (rule 5).
  **Verify:** rearrange docks, collapse a section, quit, relaunch —
  layout and section states survive; delete the settings key →
  sensible default layout.
- **M1.9 Exit run-through + close-out.** The roadmap exit criteria,
  verbatim (§4), plus docs close-out (§6), merge to `main`, tag
  `v0.2-beta.1`. **Verify:** §4 checklist complete; full `pytest`
  (goldens + live oracle included) green on the merge commit.

## 4. Exit criteria (ROADMAP.md's, restated)

- Every alpha feature reachable and functioning in the new chrome —
  interactive run-through: load complex2, tint a part, tap, change
  swing/bpm/floor/offset from the inspector, undo through all of it,
  export. (Use §1's tables as the checklist: every row reachable.)
- Window layout survives restart.
- Full suite green: `pytest` including `tests/goldens/`, the live
  oracle, and `tests/test_no_qt_in_core.py`.
- No-monoliths audit: no `ui/` module ≥ ~400 lines.
- Merged to `main`, tagged `v0.2-beta.1`.

## 5. Contact-with-reality flags

Found while inventorying the real code against the M1 design; each is
a decision this brief records rather than a silent deviation.

1. **The roadmap's named split is too coarse.** `ui/inspector.py` +
   `ui/transport.py` alone leave an ~800-line window; §2 expands to
   nine modules under the no-monoliths rule. Consistent with the
   roadmap's own "M1 sets the pattern by decomposing main_window.py".
2. **pyproject fix, corrected form.** The requested literal
   `packages = ["scoreanim"]` (already in the working tree,
   uncommitted) repairs `pip install -e .` but would break a
   non-editable install — subpackages aren't recursed. M1.0 commits
   the `packages.find` form instead.
3. **Follow vs Systems/Sweep in one panel.** Follow is transient
   controller state (`playback.set_follow` — survives nothing);
   Systems and Sweep are document intent (commands, blockSignals-
   resynced, undoable). Same panel, two sync behaviors — correct, but
   the inspector must NOT resync Follow from the document (there is
   nothing to resync from). Follow's menu item and inspector toggle
   share one QAction so their checked states cannot diverge.
4. **Systems has no menu home in the roadmap** (View lists fit,
   prev/next, dock toggles; Playback lists follow but not systems).
   M1 leaves it inspector-only — flagged; a View-menu item is a
   one-liner later if wanted.
5. **Tap is currently invisible.** The "T" action is window-level with
   no widget. The strip gives it a visible button — a visibility
   change, not a new capability; recorded here so "no new features"
   stays honest.
6. **Units stay as suffixes.** The prefix-in-spinbox retirement removes
   prefixes; Offset keeps its `" s"` suffix (a unit, not a label).
7. **Lane resizing.** The old three-way splitter let the user resize
   waveform vs tempo lane vs stage. Stage-vs-zone sizing moves to the
   dock boundary; an internal splitter between the lanes preserves the
   rest. The stage's collapsible=False guarantee carries over (the
   dock can't swallow the central widget).
8. **First-run geometry changes** (1000×1200 → wider) — cosmetic, but
   it is a visible behavior change on first launch; recorded.

## 6. Suggested .md changes (during the build, per the usual close-out)

- CLAUDE.md: working-style bullet updated — main_window.py is no
  longer the worst offender; name the new module seams in the package
  layout tree (`ui/inspector.py`, `ui/transport.py`, …).
- ROADMAP.md: M1 marked closed with the two chrome rulings
  (bottom-dock lower zone; slim toolbar) recorded under it.
- ARCHITECTURE.md §7: one paragraph — window is a composition root
  over inspector/lower-zone/menus components; QSettings holds UI
  state only.
- BACKLOG.md: anything deferred (e.g. a Systems menu item, flag 4).

## 7. Prompts to paste into Claude Code

One session per prompt, /clear between.

### Prompt 1 — build

    Read CLAUDE.md, docs/ARCHITECTURE.md, docs/ROADMAP.md, and
    docs/briefs/M1_SHELL_BRIEF.md. M1 Shell is planned; build it task
    by task (M1.0 through M1.8) on branch beta/m1-shell: commit per
    task, app launching and pytest green after every task, the brief's
    §1 re-homing tables are the no-capability-lost checklist, no file
    in ui/ at or above ~400 lines when you finish. Boundaries: no
    changes to commands, AppState semantics, core/, or render/.
    Flag-and-stop where reality disagrees with the brief.

### Prompt 2 — exit + close-out

    M1 Shell is built on beta/m1-shell. Run the M1 exit: full pytest
    (goldens, live oracle, no-Qt-in-core); the §4 interactive
    run-through on complex2 (tint, tap, swing/bpm/floor/offset from
    the inspector, undo through all of it, export); restart-survival
    of the window layout; the ui/ module-size audit. Close out the
    docs per §6, then stop for my review before merging to main and
    tagging v0.2-beta.1.
