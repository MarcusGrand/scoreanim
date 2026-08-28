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

**C3 — Selection tab comes to front on select.**
> When a stage selection is made, bring the Selection tab to front (and flip
> back to the previously active tab when the selection clears, if the user
> hasn't switched tabs themselves meanwhile). Add the empty state: "Nothing
> selected — click a note on the stage." Check: click a note → Selection tab
> fronts with the readout; Esc/deselect → previous tab returns; manual tab
> choice while something is selected is respected.

**C4 — timeline bar split.**
> The bottom bar keeps only document timing, grouped under a "Timing" label:
> Tempo, Offset, Swing. Lane, the grid dropdown and Flatten move into a small
> gear-icon menu at the right edge of the lane header. Check: all lane view
> options still work from the gear menu; the timing fields still live-preview
> and land one undo entry per edit.

### Phase D — transport and stage polish

**D1 — transport cluster.**
> Replace "Play + full-width slider" with a transport cluster: go-to-start
> and play/pause icon buttons, monospace timecode "0:42.8 / 1:40.8", then the
> Follow/Systems toggles from C2; the seek slider becomes a slim themed bar
> filling the remaining width. Space and all existing bindings unchanged.
> Check: seek by click and drag still works; go-to-start seeks to 0 and
> keeps playing state sensible; timecode digits don't wiggle during playback.

**D2 — stage overlay controls.**
> Add floating overlay controls in the stage's bottom-right: zoom out, zoom
> percent readout, zoom in, and Fit (the same fit QAction). Subtle
> semi-transparent chrome that appears when the pointer is over the stage.
> Wheel/pinch zoom updates the readout. Check: overlay never steals a click
> meant for the score (it sits outside the page area), Fit restores fit mode,
> percent tracks pinch zoom.

**D3 — hint bar.**
> Turn the status bar into a hint bar: with a selection it shows what is
> selected and the available gestures ("Note · Tpts · m. 19 — drag to move
> its onset line, F flips the stem"); with none it shows the loaded audio
> file and transient status messages as today. One small module owns the
> wording. Check: hints update on select/deselect; status messages (export
> progress, re-engrave failures) still show and then give the hint back.

### Phase E — front door and release readiness

**E1 — welcome pane.**
> Show a welcome pane in the stage area when nothing is loaded: app name,
> Open Score and Open Project buttons, the recent-files list from B1, and a
> drop hint. Accept drag-and-drop of .musicxml/.xml and project files on the
> whole window at all times. Check: launch empty → welcome pane; open or
> drop a file → pane gone, score loads; drop while a score is loaded asks
> before replacing.

**E2 — tooltip and empty-state pass.**
> A finish pass over every interactive control: each gets a tooltip (what it
> does, plus shortcut if it has one); every list/readout gets an empty state
> (layout zone lists, selection tab); every disabled control's tooltip says
> why it is disabled. Check: hover any control in every panel — no tooltip
> gaps; fresh launch shows helpful empty states, not blank space.

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
