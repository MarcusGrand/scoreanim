# ScoreAnim UI redesign — review and plan

Written 2026-08-28, from the current code (`scoreanim/ui/`) and a screenshot of
the app with `nidelven.scoreanim` loaded. Goal set by Marcus: a full facelift,
free to restructure, aimed at an app other people will eventually use.

---

## 1. What the UI is today

- **Center:** the stage (score page on a dark letterbox).
- **Left dock "Layout":** break buttons, break overrides list, deleted list.
- **Right dock "Inspector":** collapsible sections — Playback & Sync
  (Follow, Systems), Appearance & Effects (effect pickers + knobs + volume
  response), Page (light/dark), Video canvas, Selection.
- **Bottom dock:** transport strip (Play, seek slider, time), waveform lane,
  tempo/ticks lane, then a bar with Tempo · Offset · Swing · Lane · grid ·
  Flatten.
- **Chrome:** five menus, a text-only toolbar (Open Score · Open Audio ·
  Import Tempo · page pager · Fit), a status bar showing the audio file.

The structure underneath is healthy: shared QActions, one document pass,
small modules. That is exactly what makes a facelift cheap — looks and
grouping can change without touching how anything works.

---

## 2. The problems, biggest first

**P1 — The app has two identities.** Light native macOS chrome (gray panels,
white buttons, blue checkboxes) wrapped around dark content (stage, waveform,
ticks). Every serious media app — Premiere, After Effects, DaVinci, Logic,
Live — commits to one dark theme so the content is the brightest thing on
screen. Right now the brightest thing is the Inspector.

**P2 — The Inspector mixes three different kinds of thing.** Document-wide
defaults (effects, volume response), stage/export setup (page colors, video
canvas), transient view state (Follow/Systems), and the current selection all
share one stack of sections. The Adobe convention: the right panel answers
*"what am I looking at / what is selected"*; app-wide settings live elsewhere.
A user who selects a note has to scroll past global effect knobs to find it.

**P3 — Related things live apart, and some things are hidden.**
- *Open Score…* is on the toolbar but **not in the File menu** (only Open
  Project is). Open Audio and Import Tempo sit in the *Playback* menu.
  Everything that brings a file in belongs in File, together.
- *Export Video…* — the whole point of the app — is a File-menu item.
  It deserves a visible button.
- Follow and Systems are playback/view behavior, but they live at the top of
  the Inspector, far from the transport they modify.
- Tempo/Offset/Swing (document timing) share one bar with Lane/grid/Flatten
  (pure view options).
- No recent-files list anywhere.

**P4 — Words where controls should be.** "Toggle System Break Here",
"Move to Previous System", "▶ Play" as text. No icons anywhere. Text-only
toolbars read as a prototype; icons + short labels + tooltips read as a
product.

**P5 — Small finish issues that add up.** Fields clip at the panel edge
("Entire note valu…", the half-visible "Loud" row); section headers look like
gray buttons; the seek slider is a stock blue macOS slider spanning the whole
window; disabled buttons don't explain themselves; powerful invisible
features (right-click staves menu, drag-to-nudge, onset cursor, F to flip a
stem) have no discoverable surface.

**P6 — No front door.** The app opens as an empty gray window. A released
app needs a welcome state: recent projects, big "Open score", drag-and-drop.

---

## 3. The target design

One dark theme, three work zones, and a right panel that always answers
"what is selected".

```
┌────────────────────────────────────────────────────────────────────┐
│ ⬒ Open ▾   ♫ Audio   ⌚ Tempo      ◂ sys 10/18 ▸        [Export ▸] │  toolbar
├──────────┬───────────────────────────────────┬─────────────────────┤
│ LAYOUT   │                                   │ ANIMATE ⋮ STAGE ⋮ ▣ │
│ Breaks   │            stage                  │  (tabbed panel)     │
│ Overrides│                                   │                     │
│ Deleted  │                        ⊕ 100% ⊡  │                     │
├──────────┴───────────────────────────────────┴─────────────────────┤
│ ⏮ ⏯   0:42.8 / 1:40.8   ⟲ Follow  ⧉ Systems              ⚙ lanes │  transport
│ ───────────────── waveform ──────────────────────────────────────  │
│ ───────────────── ticks / tempo ─────────────────────────────────  │
│ Timing:  Tempo 120,0   Offset 1,46 s   Swing 0,67                  │
└────────────────────────────────────────────────────────────────────┘
```

### 3.1 Visual design

- **Dark theme everywhere.** Token set (working values, tune by eye):
  window `#1e1f22`, panel `#26272b`, inset/lanes `#17181b`, border
  `#3a3b40`, text `#d6d7db`, dim text `#8e909c`, accent `#ffcc66` (the glow
  color — it is already the app's signature), playhead `#ffb454`, waveform
  `#5b87b8`. Accent is used sparingly: the active toggle, the playhead, the
  Export button.
- **One icon set.** Lucide (MIT-licensed SVGs), tinted to the text color at
  load, accent when active. Play/pause/skip, folder, music note, metronome,
  export, eye, undo-arrow for restore, etc.
- **Typography.** System font; timecode and measure numbers in the system
  monospace so digits don't wiggle.
- **Spacing.** An 8-px grid: 8 px panel padding, 4 px between label and
  field, 12 px between groups. Fixed label column in forms so nothing clips.
- **Section headers** become flat headers: caps-ish small label + chevron,
  full-width hover, no button frame.

### 3.2 The right panel: three tabs instead of one stack

Adobe's model, simplified to what ScoreAnim actually has:

- **Animate** — how the score animates by default: Effect + Combine with,
  the active preset's knobs, envelope, volume response, floor opacity, sweep,
  tied-as-one. (Today's *Appearance & Effects*, unchanged inside.)
- **Stage** — what the frame looks like: page light/dark, video canvas
  preset/size/scale, preview background. (Today's *Page* + *Video canvas*.)
- **Selection** — what is selected and what you can do to it: readout,
  color/effect scope controls, "Fires" re-timing row. **Auto-switches to
  front when you select something on the stage** (Premiere's Effect Controls
  behavior), and shows a quiet "Nothing selected — click a note" empty state
  otherwise.

Follow and Systems leave the panel entirely and join the transport (3.4).

### 3.3 Toolbar and menus

- Toolbar, left to right: **Open** (icon + label, with a small dropdown for
  Score / Project / recent files), **Audio**, **Tempo**, separator, page
  pager `◂ sys 10/18 ▸`, spring spacer, and a highlighted **Export** button
  on the right — the one accent-colored control in the chrome.
- File menu: Open Score…, Open Audio…, Import Tempo…, Open Project…,
  Open Recent ▸, then Save / Save As / Export Video…. (Playback menu keeps
  playback only: Play, Follow, Reload Tempo.)
- New **Help** menu: Keyboard Shortcuts… (generated from the live QActions,
  so it can never go stale) and About.
- Fit leaves the toolbar for a stage overlay (3.5).

### 3.4 Transport

A real transport cluster instead of a full-width slider:

- **⏮ go-to-start, ⏯ play/pause** as icon buttons, then the timecode in
  monospace, then **Follow** and **Systems** as labeled icon toggles — they
  are playback behavior, and this puts them next to what they change.
- The seek bar stays, but slimmer and themed; later it can merge into the
  waveform itself (click-to-seek on the lane already exists via the axis).
- Lane view options (Lane / Ticks / Bars / Flatten) move out of the bottom
  bar into a small **⚙ menu at the lane's right edge** — they configure the
  view, not the document. The bottom bar keeps only document timing, under
  one label: **Timing: Tempo · Offset · Swing**.

### 3.5 Stage

- Floating overlay controls, bottom-right of the stage, like every canvas
  app: **zoom −/+, percent readout, Fit**. Semi-transparent, appear on
  hover/interaction.
- The page pager can stay in the toolbar (it is navigation, not view), still
  synced with Follow.
- Status bar becomes a **hint bar**: shows the selection ("Note, Tpts,
  m. 19 — drag to nudge, F flips the stem") and short contextual hints.
  This is the cheapest discoverability tool the app can have.

### 3.6 Layout dock

- Break buttons get icons and short labels ("System break here", "Page break
  here", "Pull to previous system") — the tooltip carries the long
  explanation. Disabled buttons get a tooltip saying *why* ("Select a
  measure first").
- Overrides and Deleted become styled list rows: icon, text, and a restore
  button that appears on hover. Proper empty states ("No break overrides —
  toggle one with a measure selected").

### 3.7 The front door

A welcome pane in the (otherwise empty) stage area on launch: app name,
**Open score**, **Open project**, recent projects as a list, and
"…or drop a MusicXML / project file here". Disappears the moment something
loads. Drag-and-drop onto the window should work at all times.

### 3.8 Where every control moves (summary map)

| Control today | New home |
|---|---|
| Inspector → Follow, Systems | Transport strip (icon toggles) |
| Inspector → Appearance & Effects | Right panel, **Animate** tab |
| Inspector → Page, Video canvas | Right panel, **Stage** tab |
| Inspector → Selection | Right panel, **Selection** tab (auto-front) |
| Toolbar → Fit | Stage overlay (with zoom −/+/%) |
| Toolbar → the three openers | Toolbar, icon+label, + File menu + welcome pane |
| File menu (missing Open Score) | File menu gains all openers + recents |
| Playback menu → Open Audio, Import Tempo | File menu |
| Timeline bar → Lane, grid, Flatten | ⚙ menu on the lane |
| Timeline bar → Tempo, Offset, Swing | Stays, grouped as "Timing" |
| Export (File menu only) | Also an accent Export button, toolbar right |
| Status bar (audio filename) | Hint bar (selection + hints); filename moves to a small chip next to the Audio button |

Nothing is removed; every QAction keeps working from its old shortcut and
menu, so muscle memory survives.

---

## 4. Implementation plan

Ordered so each phase is visibly worth it on its own, and sized so every step
is one small Claude Code prompt. Theme first: it touches no behavior, changes
everything on screen, and every later step then builds in the new look.

Two decisions are baked into the prompts (flagging them so they're conscious):
tabs (not stacked sections) for the right panel, and Follow/Systems moving to
the transport. If either feels wrong in use, each is a one-step revert.

### Phase A — one dark theme

**A1 — theme package.**
> Give the app one dark theme. Create a small `ui/theme/` package:
> `palette.py` holding named color tokens (window #1e1f22, panel #26272b,
> inset #17181b, border #3a3b40, text #d6d7db, dim #8e909c, accent #ffcc66,
> playhead #ffb454, waveform #5b87b8) and `theme.py` that applies the Fusion
> style, a QPalette built from those tokens, and one app-wide QSS string for
> what the palette can't reach (dock title bars, toolbar, section headers,
> spinboxes). Apply it at the app entry point before the window exists. No
> per-widget styling in other modules — everything reads the tokens. The
> waveform and lane views should switch their hard-coded colors to the
> tokens too. Check: launch, load a score — every surface dark, all text
> readable, the two lanes and the stage letterbox use the same family of
> darks.

**A2 — icons.**
> Add an icon system. Vendor a small set of Lucide SVG icons (MIT) under
> `ui/theme/icons/`, with a loader in `ui/theme/icons.py` that returns
> QIcons tinted to the theme's text color (accent when on/checked). Give
> icons to: the three openers, prev/next page, Fit, Play/Pause (replace the
> "▶ Play" text with an icon-only button whose tooltip says Play/Pause +
> Space), undo/redo, and the layout zone's three break buttons. Keep labels
> on the openers (icon + text), icon-only elsewhere with tooltips. Check:
> toolbar and transport show crisp icons in both a Retina and non-Retina
> window; play button flips icon while playing.

**A3 — panel finish pass.**
> Restyle the inspector's collapsible sections and the three docks: section
> headers become flat full-width headers (small bold label + chevron, hover
> highlight, no button frame); every form gets a fixed label column and
> enough minimum width that nothing clips (today "Entire note value" and the
> volume "Loud" row clip); consistent 8 px padding, 12 px between groups.
> Check: no clipped text anywhere in the right dock at its default width;
> sections expand/collapse as before and remember their state.

### Phase B — commands where people look for them

**B1 — File menu and recents.**
> Every way of getting a file in belongs in the File menu: add Open Score…
> (it is toolbar-only today), move Open Audio… and Import Tempo… from the
> Playback menu into File, and add an Open Recent submenu (last 8 scores and
> projects, stored in QSettings, updated on every successful open). Playback
> keeps Play, Follow, Reload Tempo. Same QAction objects everywhere — no
> duplicates. Check: all three openers work from File; recents list
> populates, survives a restart, and opens the file it names.

**B2 — toolbar with Export.**
> Rework the toolbar: left group Open Score / Open Audio / Import Tempo
> (icon+label), separator, the page pager, then a spring spacer, then an
> Export button styled with the accent color, right-aligned — the same
> export QAction the File menu holds, enabled once a score loads. Remove Fit
> from the toolbar (it moves to the stage in D2). Check: Export button
> disabled on launch, enabled after load, opens the export dialog; layout
> holds at narrow window widths.

**B3 — Help menu.**
> Add a Help menu with Keyboard Shortcuts… and About ScoreAnim. The
> shortcuts dialog is generated at open time from the window's QActions
> (action text + shortcut, grouped by menu), plus a hand-kept list of the
> mouse gestures (drag to nudge, right-click staves, double-click text,
> F flips a stem, Delete hides). Check: dialog lists Space, Ctrl+E, F5 etc.
> correctly and never shows an action with no shortcut and no gesture note.

### Phase C — the right panel becomes three tabs

**C1 — tab container.**
> Restructure the Inspector dock into a QTabWidget with three tabs: Animate
> (the EffectsPanel body), Stage (PageColorsPanel + VideoCanvasPanel stacked),
> Selection (SelectionPanel). The Playback & Sync section disappears from the
> dock; its Follow/Systems controls are re-homed in C2 — keep `follow_action`
> alive on the window meanwhile so the Playback menu keeps working. Sections
> inside a tab keep their collapsible behavior and persisted state; persist
> the active tab too. All sync_from_document paths unchanged. Check: all
> controls work as before from their new tabs; expanded state and active tab
> survive a restart.

**C2 — Follow/Systems to the transport.**
> Move Follow and Systems onto the transport strip as icon toggles (Follow =
> the same shared QAction the Playback menu uses; Systems keeps its
> command/resync shape), placed after the time readout with tooltips. Check:
> menu item and transport toggle stay in lockstep; toggling Systems still
> re-frames the stage; nothing about them remains in the right dock.

*Amended 2026-08-29, Marcus: Follow is not an option at all. Playing music
always shows the music, so the toggle and the Playback-menu item are both
gone, `ui/playback.py` reports the position unconditionally, and pressing
play snaps the stage back to the cursor. Only Systems reached the strip.*

**C3 — Selection tab comes to front on select.**
> When a stage selection is made, bring the Selection tab to front (and flip
> back to the previously active tab when the selection clears, if the user
> hasn't switched tabs themselves meanwhile). Add the empty state: "Nothing
> selected — click a note on the stage." Check: click a note → Selection tab
> fronts with the readout; Esc/deselect → previous tab returns; manual tab
> choice while something is selected is respected.

*Built 2026-08-29 (`ecb20f3`) — the note was written up in the worklog
and missed here. The rule is a pure state machine, `ui/tab_focus.py`,
over one episode: the stretch from "nothing selected" to "nothing
selected again". Fronting happens once per episode, so clicking a
second note does not yank a tab you just chose, and **your own choice
always wins** — switching tabs while something is selected clears the
tab to return to, so clearing the selection leaves it where you put it.
The dock only reports the two events to it, and a tab switch the dock
makes ITSELF is flagged, or it would read back as the user's choice.
Empty state as written. 9 headless tests.*

**C4 — timeline bar split.**
> The bottom bar keeps only document timing, grouped under a "Timing" label:
> Tempo, Offset, Swing. Lane, the grid dropdown and Flatten move into a small
> gear-icon menu at the right edge of the lane header. Check: all lane view
> options still work from the gear menu; the timing fields still live-preview
> and land one undo entry per edit.

*Built 2026-08-29. The lane header is the transport strip — it is the row
directly above the lanes — so the gear sits at its right edge, after Systems,
exactly as the §3 sketch draws it. The three view options live in
`ui/lane_menu.py`; the group labels inside the menu are disabled items, not
`QMenu.addSection`, because the app's stylesheet paints a section as a plain
line and ate the words.*

### Phase D — transport and stage polish

**D1 — transport cluster.**
> Replace "Play + full-width slider" with a transport cluster: go-to-start
> and play/pause icon buttons, monospace timecode "0:42.8 / 1:40.8", then the
> Systems toggle from C2 (Follow is gone — see the C2 amendment); the seek
> slider becomes a slim themed bar
> filling the remaining width. Space and all existing bindings unchanged.
> Check: seek by click and drag still works; go-to-start seeks to 0 and
> keeps playing state sensible; timecode digits don't wiggle during playback.

*Built 2026-08-29. Order on the strip: go to start, play, timecode,
Systems, then the seek bar taking the spare width, then C4's gear at
the right edge. Go-to-start only seeks — it never starts or stops
anything, so playing stays playing. The timecode needed two fixes, not
one: `QFontDatabase.systemFont(FixedFont)` comes back naming a family
called "monospace" that no machine has, so Qt fell back to the
proportional UI font and the digits still wiggled — a Monospace style
hint is what lands it on a real fixed-width face. The label also keeps
a minimum width, so the first two-digit minute does not shove the
cluster sideways. The slider is dressed by name (`QSlider#SeekBar`) in
the stylesheet.*

*Revised 2026-08-29, same day, on Marcus's call: **the seek bar is
gone.** The waveform and ticks lanes already seek on click and scrub on
drag, so the strip's slider was a second playhead moving at a different
speed from the lanes' cursor — two clocks disagreeing. The strip is now
just the cluster (go to start · play · timecode), Systems, empty space,
and the gear. `QSlider#SeekBar` came out of the stylesheet with it. The
keyboard seeking a QSlider gives away for free is rebuilt as
`ui/seek_keys.py`: Left/Right = 1 s, Shift+Left/Right = 5 s, on
`PlaybackController.seek_by` (clamped to the timeline, play state
untouched), and Home went onto the strip's existing Go to Start action.
All five are window-level, so they fire wherever the focus is, and all
five are in the Playback menu, which is where the shortcut sheet finds
them. Two things still get an arrow ahead of them, both through Qt's
ShortcutOverride path rather than a focus test here: a text field or
spin box claims Left/Right/Home for its own caret by itself, and the
stage claims the arrows while something nudgeable is selected.*

**D2 — stage overlay controls.**
> Add floating overlay controls in the stage's bottom-right: zoom out, zoom
> percent readout, zoom in, and Fit (the same fit QAction). Subtle
> semi-transparent chrome that appears when the pointer is over the stage.
> Wheel/pinch zoom updates the readout. Check: overlay never steals a click
> meant for the score (it sits outside the page area), Fit restores fit mode,
> percent tracks pinch zoom.

*Built 2026-08-29. **100 % means fitted** — the size the Fit button
gives you. There is no other honest anchor: a page is about 2095 x 2967
in the engraving's own units (tenths of a millimetre), so an
"actual size" percentage would be a number about nothing, while Fit is
a size the user can always get back to in one click. The fit scale is
therefore worked out on every reading (`ui/stage_zoom.py`, pure) rather
than remembered from the last fit, because resizing the window changes
what fitted means — a view left at twice fit size is not twice fit size
once the window grows. The pure part also pins Qt's undocumented 2 px
fitInView margin against a real fit, so a Qt release that changes it
fails a test instead of drifting the readout.

The controls (`ui/zoom_overlay.py`) are a child of the view's viewport
and the only chrome in the app that sits ON the score, so they are
see-through (three OVERLAY tokens) and only there while the pointer is
over the stage. Hidden means hidden, never transparent-but-present, so
nothing of theirs is in the way of a click when they are not showing.
They take no keyboard focus, so clicking one leaves Esc, the arrows and
Space where they were, and a button zoom anchors on the middle of the
stage rather than the pointer — the pointer is on a button in the
corner at that moment, so the pinch's under-the-cursor anchor would
throw the score away from it. Fit is the View menu's own QAction.

One honest limit: while the controls ARE showing they cover their own
corner, like every floating control does. Two things keep that cheap —
the page is letterboxed in a wide window, so the corner is usually
beside the page rather than on it, and the controls fade in before the
click, not under it. Marcus's call if it ever gets in the way.*

*Two fixes on Marcus's first look, same day. **The controls scrolled
away with the score**: they were a child of the view's VIEWPORT, and
`QGraphicsView` scrolls by calling `viewport()->scroll(dx, dy)`, which
moves that widget's children along with the pixels. They are a child of
the view now, placed against `viewport().geometry()`, so they hold
still wherever they are visible. **And the scroll indicators are real
scrollbars now.** They were feedback only, on the reasoning that they
were gone before you could reach for one — which was the wrong way
round: a thing that looks like a scrollbar has to behave like one. So
they come up when the pointer reaches within 32 px of the edge they
live on, they hold while it is there (the fade refuses to start on a
bar under the pointer or in the hand), and a press within 14 px of that
edge scrolls: on the bar it drags, on the track it jumps the bar to the
pointer and drags on from there. The view offers every press, move and
release to `TransientScrollbars` first, so a grab is never a click on
the score, and a bar that has faded out takes no press at all — the
same rule the zoom controls follow. Both bands stay inside the zoom
controls' own margin, so the two never argue over a click.*

*Third pass, same day, on Marcus's call: **a bar says whether it can be
grabbed.** Resting it is thin (6 px) and dark. Once the pointer is
close enough to take it, it widens to 11 px and goes more solid — and
that width is a promise, so the band `press` accepts is worked out FROM
the wide bar (`_GRAB = margin + wide + 2`) rather than picked
separately; the two cannot drift apart and start lying to each other,
and a test walks the distances from the edge to check that wide and
grabbable agree at every one. It grows INWARD, so the outer edge holds
still and a bar does not fatten out from under the hand that made it.
In the hand it goes light instead of dark — the theme's DIM grey, which
reads on the page and on the letterbox both, with a dark outline for
the same reason the dark bar has a pale one. The zoom controls moved
from 12 px to 20 px off the corner to clear the wide bar and its band:
at 12 they covered a stretch of the horizontal bar and made it
un-grabbable.*

**D3 — hint bar.**
> Turn the status bar into a hint bar: with a selection it shows what is
> selected and the available gestures ("Note · Tpts · m. 19 — drag to move
> its onset line, F flips the stem"); with none it shows the loaded audio
> file and transient status messages as today. One small module owns the
> wording. Check: hints update on select/deselect; status messages (export
> progress, re-engrave failures) still show and then give the hint back.

*Built 2026-08-29. The wording is `core/editing/hints.py`, pure and
next to the other status-tip modules (deletion, stem flip, breaks): one
table of plain kind names, one phrase per gesture, at most three of
them on the line. `ui/hint_bar.py` gathers the answers, each from the
controller that owns that gesture, so the bar cannot offer a key the
app would ignore — which is why a NOTE reads "Note · Tpts · m. 19 — F
flips the stem" and not the brief's onset-line example: a notehead is a
reveal anchor, so it has no onset line to drag. The measure is the
PRINTED number. Two mechanisms behind it: the hint is a normal widget
on the status bar, which Qt hides under a temporary message and shows
again when the message expires — so every status message now goes
through `HintBar.message`, which supplies the timeout an untimed
`showMessage` never had — and the label elides its own text, so the
window's minimum width does not depend on which note you clicked.*

### Phase E — front door and release readiness

**E1 — welcome pane.**
> Show a welcome pane in the stage area when nothing is loaded: app name,
> Open Score and Open Project buttons, the recent-files list from B1, and a
> drop hint. Accept drag-and-drop of .musicxml/.xml and project files on the
> whole window at all times. Check: launch empty → welcome pane; open or
> drop a file → pane gone, score loads; drop while a score is loaded asks
> before replacing.

*Built 2026-08-29. The pane (`ui/welcome_pane.py`) is a child of the
stage VIEW, sized to `viewport().geometry()` — the same parenting D2
had to be fixed into, since a child of the viewport scrolls away with
the picture. It shows exactly while `doc.score is None`, decided in the
window's document-changed pass beside every other sync, so nothing has
to be told about an open. The recent list is a second view of the store
the File menu reads (B1), the newest six of the eight; with an empty
store the heading and the box go and one line says "Nothing opened
yet."

One thing worth knowing about the layout: a Qt layout pushes its own
minimum size onto the widget it is in, so the card's 360 px would have
become a floor under the whole window's width. The outer layout is
`SetNoConstraint` — the stage sizes the pane, never the other way
round, and a stage too small for the card simply clips it.

Drops are the window's own `dragEnterEvent`/`dropEvent`
(`ui/file_drop.py` holds the policy). Two things had to be true for a
drag to arrive at all. `StageView` has drops turned OFF, because
QGraphicsView turns them on in its own constructor, and a drag that
stops at a widget which ignores it is never offered to the parent —
without that, the whole middle of the window would have been a dead
zone. And accepting the ENTER is enough: Qt carries that answer to the
moves that follow. What counts as openable is one pure rule
(`core/project/file_kinds.py`), which Open Recent now dispatches
through too, so the drag, the list and the dialogs cannot start
disagreeing about what a `.xml` is.

A drop onto a score that is already open asks first, and says so louder
when there are unsaved changes: opening is not undoable (ruling
2026-07-11), so a mis-aimed drag would otherwise throw the session
away. 18 new tests. Two Qt facts they had to be built around: a
programmatic `sendEvent` of a drag never reaches the widget — the
application discards drag events with no real drag behind them, so the
tests call the handlers the way Qt does — and a drag event does not own
its `QMimeData`, so a temporary one is freed while the event still
points at it (a segfault, found writing them).*

**E2 — tooltip and empty-state pass.**
> A finish pass over every interactive control: each gets a tooltip (what it
> does, plus shortcut if it has one); every list/readout gets an empty state
> (layout zone lists, selection tab); every disabled control's tooltip says
> why it is disabled. Check: hover any control in every panel — no tooltip
> gaps; fresh launch shows helpful empty states, not blank space.

*Built 2026-08-29. One module owns the mechanism (`ui/tips.py`):
`describe` writes a control's sentence and parks it on the widget,
`describe_action` adds the shortcut read off the QAction itself, and
`gate` replaces `setEnabled` wherever the reason for graying is not
already on screen — the tooltip becomes that reason and goes back to
the sentence when the control comes alive. `tips.label` came out of the
five panels each writing the same three lines to make a form label say
what its field says.

The gaps this closed were mostly the disabled ones. Export and Texts,
Undo and Redo, the pager, Reset, Restore all, Width and Height without
a frame, the re-time steppers, a part scope on score-level ink, a
colour on ink that is always the page's own — all of them grayed
silently before. So did the four different reasons the stage's Staves
menu refuses to hide a staff, which are now one pure function
(`StageMenu.hide_reason`). The Animate tab's grayed knobs generate
their own reason from the knob table (`knob_types.knob_name` plus three
phrases), so a new dependency gets one without anybody writing it —
effects stay data (rule 6).

Two behavior notes. Nothing was newly disabled: the pass adds reasons
to controls that already grayed themselves, and Offset and Swing keep
working with no audio and no score, as they did. And the break, delete
and flip actions now sync once at construction, so they carry their
reason from the first frame rather than from the first selection
change — which is what the layout zone's icon-only buttons show.

Empty states: the tempo lane was a blank rectangle on a fresh launch
next to a waveform that has said "No audio" since FIX 2, and now says
what it is missing. The two layout-zone lists say what would fill them
rather than only that they are empty.

`tests/test_tooltips.py` is the guard, and it is a sweep, not a
spot-check: it walks a real window and fails on an action with no
sentence, a control with no tooltip, or a control that grayed itself
out while still describing a gesture it will not run. 83 controls and
33 actions on an empty window, then again with a score loaded and a
note picked. It checks the dynamic property `describe` writes, not the
tooltip — Qt fills a bare action's tooltip in from its own label, so a
tooltip alone proves nothing. Two Qt facts it had to be built around: a
scroll area parents its content under a `qt_scrollarea_viewport`, so
skipping every widget with a `qt_`-named ANCESTOR would have quietly
excused two of the three docks; and a control disabled only because
its container is has its own enabled flag still set, which
`isEnabledTo(parent)` is how you tell apart — a block switched off as a
unit is covered by its panel's empty state and must not be asked to
repeat the reason on every widget in it.*

*Followed up 2026-08-30 on Marcus's look, on the box itself. It is
**light now** — a muted grey ground with near-black text, the one
surface in the app that runs the other way, because a tooltip is a note
laid ON the interface rather than part of it and it has to read over a
dark panel and over the white score page both. Three tokens (`TIP`,
`TIP_TEXT`, `TIP_BORDER`), the `QToolTip` rule, and the two palette
roles Qt would use without the sheet.

And it **always reads rightward from the pointer**: the box starts at
the cursor and runs right, and near the right edge it slides left only
far enough to fit, so the pointer ends up somewhere along it. Qt does
not do that — `QTipLabel::placeTip` moves the whole box to the OTHER
side of the cursor when it would overrun, so the same gesture puts the
text in two different places depending on where you were. So the
horizontal placement is ours: `tip_left` is the rule, pure and
headless, and an application-wide event filter applies it to Qt's own
tooltip window (`ui/tip_placement.py`). Only the x — Qt's vertical
behaviour is already right. Three events have to be watched, not one:
Qt places the box before showing it, places it AGAIN with no second
show when the pointer travels to another control while a box is up
(`reuseTip`), and applies the stylesheet's padding AFTER placing it, so
a correction made before that resize lands two pixels out — measured,
not guessed. 12 new tests, two of which drive Qt's real tooltip window,
including one that pins the flip Qt does without the filter so nobody
removes it thinking Qt would behave.*

**E3 — identity.**
> App icon (matches the accent-on-dark look), window title unchanged, About
> dialog with version, and a pass to make sure the app name/casing is
> consistent everywhere. Check: icon shows in the Dock and the app switcher.

---

## 5. What this deliberately does not do (yet)

- **Workspaces** (Adobe's switchable layouts). The app has one workflow;
  three docks + tabs cover it. Revisit only if the panel count grows.
- **Adobe-style scrubbable number fields** (drag a value label to change
  it). Nice, fits the LiveField model well — a good later addition to
  `live_field.py`, but not needed for the facelift.
- **Loop region / in-out points** on the timeline. A feature, not UI polish;
  belongs on the features plan.
- **Light theme.** One committed dark theme first; the token system makes a
  light variant cheap later if release feedback asks for it.
