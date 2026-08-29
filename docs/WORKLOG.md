# ScoreAnim — Worklog

**NOW:** the UI facelift is **merged to `main`, tagged
`v0.2-beta.7`, pushed, and passed under Marcus's own eye in the running
app** (2026-08-29) — phases A, B, C and D of `docs/UI_REDESIGN.md` less
**D2** (stage overlay zoom controls), which is **built on
`ui-d2-stage-overlay` and waiting for Marcus's in-app check**; phase E
(welcome pane, tooltip pass, identity) is next after it. The
phases: A1 one dark theme, A2 icons, A3 the panel finish pass, B1 the File menu and recents, B2
the toolbar with Export, B3 the Help menu, C1 the three inspector tabs,
C2 Systems on the transport strip, C3 the Selection tab fronting on
select, C4 the timeline bar split, D1 the transport cluster (and the
seek slider's removal, with arrow-key seeking in its place), D3 the
hint bar. **Schema is untouched at v12** — the facelift is presentation
only, so a project saved on `v0.2-beta.6` opens here unchanged.
On 2026-08-16, on Marcus's call after his in-app
check, three branches merged in order: `beta/f-hide-parts` (the
Staves menu, per-system hides, the region-fill hide fix),
`f-tuplet-ink-reclaim` (stolen tuplet ink under id reuse) and
`f-tied-as-one` ("Tied notes as one"). The last merge's conflicts
were resolved to the byte-identical tree tested on the scratch
integration branch (full suite 2163 green there).
**Schema is v12** (hidden-parts, system-hides and tied-as-one all
ride it sparsely), so a project saved from here will not open on
`v0.2-beta.6` or any older build.

**Every score re-engraves differently from 2026-08-03 on** — the stem
pass is unconditional, and it moved 11 of the 12 goldens. That is the
point of it, but it means a project saved before 2026-08-03 will not
render identically to how it looked.

Light and dark mode, the glow (with its envelope editor) and the stem
pass are all on `main` but **unproven under a human's eye** — every
check so far is headless or offscreen. The things to look at are a
transposing part, where 34 % of the wrong stems lived, and the feel of
dragging the envelope's handles.

Two calibration questions left open on purpose, both measured (see the
2026-08-02 lines): the pulse amounts' **0–20 % range is too generous** —
two systems overlap on testscore page 2 at 0.10 and nothing detects a
collision — and the onset pop's **default `notes_for_full` of 6
saturates 72 %** of that fixture's beats, so most bumps come out the same
size. Marcus's call on both; he has said he wants to tweak them.

Open question from grid-align, still open: whether Tempo mode still
earns its place now that the Tempo field aims at the selected line.

`render/items.py` is at **402** — over the ceiling as of 2026-08-06,
though its own class docstring argues it is one job (it is the single
compositing point for how an element looks), so the split wants a real
seam rather than a line count. `render/animate.py` is at **408** as of
2026-08-10 (the tied-as-one reveal-tracks hook) — same shape, one
class whose drivers are already split out; flagged, not paid.
Three of the standing split debts were paid on the canvas branch
(2026-08-06): `export_dialog.py` 425 → 386 (`ui/export_run.py`),
`serialize.py` 503 → 441 (`serialize_style.py` — still over, but what
remains is mostly the version-history comment block, which belongs
with the envelope), `main_window.py` 412 → 326 (`ui/score_install.py`).
`ui/stage_view.py` is at **443** after the canvas framing and its
stability fit — the real seam in it is the selection-gesture handlers,
and it is now the most overdue split. `render/items.py` still wants
its seam.

One dated line per session, newest first. Every session reads this file
at start and appends its line at close. Keep entries to one or two
lines — history lives in git and `docs/history/`.

---

- 2026-08-29 — `ui-redesign` (UI_REDESIGN.md phase C2, as amended):
  **Systems on the transport, and Follow is not an option**. Marcus's
  ruling mid-step: playing music always shows the music, so the Follow
  toggle, its Playback-menu item and `PlaybackController.set_follow` are
  all gone — the controller emits page/system unconditionally, and
  pressing play now snaps the stage back to the cursor (paging around
  while paused is browsing, and play ends it). Systems did move to the
  strip as an icon toggle after the time readout: it runs
  `SetPresentationMode` and is resynced from the document, so undo and
  project load push the mode back onto the button without re-running the
  command. The inspector holds neither now and no longer takes the
  playback controller at all. One Lucide icon vendored (`rows-3`).
  Suite green (2228).

- 2026-08-29 — `ui-redesign` (UI_REDESIGN.md phase C1): **the right dock
  is three tabs**. Animate (the effects panel), Stage (Page over Video
  canvas) and Selection, instead of one column of five sections. A tab
  holding one panel gets no section header — the tab label is the
  heading — so only Stage still stacks collapsible sections, and
  `sections` holds those two. Each tab scrolls and locks its own minimum
  width, so nothing clips in any of them. The active tab is persisted by
  KEY, never by index; `window_state` now takes the inspector itself
  rather than its sections. Playback & Sync is gone: Follow keeps its
  Playback-menu item (the same shared QAction), and the Systems toggle
  has NO home until C2 puts it on the transport. Suite green (2221).

- 2026-08-29 — `ui-redesign` (UI_REDESIGN.md phase B3): **Help menu**.
  A sixth menu, last on the bar: Keyboard Shortcuts… and About
  ScoreAnim. The shortcut sheet is HARVESTED from the menus when it
  opens, never a hand-kept table — so a key added anywhere shows up in
  it, and the Score menu's break keys are in it once a score is loaded.
  An action with no key is skipped; an action that renames itself (Undo,
  the three break actions) carries a fixed `set_sheet_name` for the
  sheet. The mouse gestures are the one hand-kept list (`GESTURES`).
  `harvest` takes the menu objects the chrome holds — calling
  `QAction.menu()` on them deletes the C++ menu, which emptied the menu
  bar the first time round. About prints no app version (there is no
  version constant to read): project format v12, Python and Qt. Suite
  green (2219).

- 2026-08-29 — `ui-redesign` (UI_REDESIGN.md phase B2): **toolbar with
  Export**. The bar now reads left to right as a session: the three
  openers, the page pager, a spring, then Export on the right edge —
  the one filled, accent-coloured button in the app. It is a
  `QToolButton` (a widget, so the QSS has a name to aim at) driving the
  File menu's `export_action`, so it is dead until a score loads and
  Ctrl+E is unchanged. Fit left the toolbar; it stays in View until the
  stage takes it over in D2. Two accent tokens added
  (`ACCENT_HOVER`, `ACCENT_PRESSED`). The window's own minimum width
  (753 px with a score loaded) is wider than the bar's contents, so the
  toolbar never overflows into an extension menu. Suite green (2211).

- 2026-08-29 — `ui-redesign` (UI_REDESIGN.md phase B1): **File menu and
  recents**. Every way of getting a file in is in File now — Open
  Score, Open Project, Open Recent, Open Audio, Import Tempo — with
  Open Audio and Import Tempo moved out of Playback, which keeps Play,
  Follow and Reload Tempo. The three openers are still on the toolbar,
  as the same QAction objects, so a button and its menu item cannot
  disagree. New `ui/recents.py`: a QSettings-backed store (last 8
  scores and projects, newest first, no duplicates) plus the submenu,
  which refills itself every time it opens. Every successful open adds
  its path; a picked entry goes to the score or the project opener by
  its suffix, and one whose file has gone says so and drops off the
  list. New `tests/test_recents.py` (14) covers the ordering rule, the
  store, the submenu and the open-close-reopen round trip. UNMERGED.

- 2026-08-29 — `ui-redesign`: **section seams**. With several
  inspector sections open they ran together, so the header band now
  carries the boundary: a shade darker than its body (`WINDOW` under
  `PANEL`, the same pairing as a dock title bar) with ONE 1px `BORDER`
  line, along its top. A line under the band as well drew a box around
  the heading — Marcus called it, and it is why the line is a divider
  between sections and not a frame. The section at the top of a stack
  draws none at all (`topmost`, worked out from its place in its
  parent's layout), so it does not double the dock title bar's line.
  One rule in the theme QSS, so every `CollapsibleSection` gets it and
  no panel paints a divider of its own; a nested one (glow's Envelope)
  keeps its line and still reads as a sub-block because the panel's
  padding insets it. Pinned by painted tests that read the pixels.
  UNMERGED.

- 2026-08-29 — `ui-redesign` (UI_REDESIGN.md phase A3): **panel finish
  pass**. Section headers are flat full-width bands now — a chevron
  (new `icons.plain_icon`, which never takes the accent), a bold label
  pinned left, a hover highlight edge to edge, no button frame. New
  `ui/panel_style.py` holds the four spacing numbers every dock form
  reads (8 px padding, 12 px between groups) and pins each form's label
  column to one width. The clipping was two bugs: a `QScrollArea` with
  `widgetResizable` squeezes its content past the content's own minimum
  (`lock_min_width` hands it back), and a panel that hides rows has to
  measure itself while it is whole. The right dock is 346 px at its
  narrowest and nothing in it clips, pinned by `tests/test_panel_style.py`.
  UNMERGED.

- 2026-08-29 — `ui-redesign` (UI_REDESIGN.md phase A2): **icons**. 13
  Lucide SVGs vendored under `ui/theme/icons/` (their LICENSE too — it
  is ISC, with MIT on the Feather-derived ones, not plain MIT), and
  `ui/theme/icons.py` tints them by swapping `currentColor` for a
  token: text off, accent on, dim disabled, rendered at each size the
  app asks for at 1x and 2x. Icons on the three openers (icon+label),
  prev/next/Fit, undo/redo, the three break buttons and Play — the
  strip's "▶ Play" text is now an icon-only button whose icon flips to
  pause. Also fixed a theme bug the icons exposed: a DISABLED toolbar
  button was the only one drawing a frame. UNMERGED.

- 2026-08-29 — `ui-redesign` (UI_REDESIGN.md phase A1): **one dark
  theme**. New `ui/theme/` package — `palette.py` names every chrome
  colour, `theme.py` builds the Fusion style + QPalette + one app-wide
  QSS string, applied in `app.py` before the window exists. The
  waveform, both lanes and the stage letterbox now read tokens instead
  of their own hex; section headers and the layout zone's headings are
  styled by object name, so no module sets a colour on itself any more.
  UNMERGED.

- 2026-08-16 — Merged to `main` on Marcus's call after his in-app
  check, in order: `beta/f-hide-parts`, `f-tuplet-ink-reclaim`,
  `f-tied-as-one`. The tied merge's conflicts (both features widened
  the same loader/installer signatures and command exports) resolved
  to the byte-identical tree of the tested scratch integration branch
  (`git diff` empty; full suite 2163 green on that tree). Pushed.
- 2026-08-10 (tuplet reclaim) — **Stolen tuplet ink goes home**
  (`f-tuplet-ink-reclaim`, off `beta/f-hide-parts`, UNMERGED): Marcus's
  bug — on the new `testdata/triplet_error.musicxml` (fixture #13, own
  golden, his call), Alto 1's m28 tuplet "3" lit with a Trombone 1 note
  and Trumpet 1's bracket was unclickable. Root cause measured: under
  hide-empty-staves' optimize round-trip Verovio re-mints xml:ids,
  leaves the `tupletNum`/`tupletBracket` groups EMPTY and draws their
  ink as direct children of id-colliding groups in ANOTHER part (the
  FINDING-5 family, beyond the spanner-curve reclaim; the bracket fell
  into staff lines = unselectable, with ZERO warnings). New
  `decoration_reclaim.py` at the decompose seam: for an empty
  id-bearing group of a `kinds._DECORATION_INK` class whose id
  collides in-page, the colliding groups' direct children matching the
  class's ink signature (tuplet digits by SMuFL range E880-E88F,
  brackets by polyline) are buffered at the walk and folded back — one
  `reclaimed-decoration-ink` warning each; collision with NO ink found
  warns/raises (`empty-decoration`). Hidden now matches flat (onset
  108.0, selectable, onset-movable); the phantom P4 accidental never
  exists. Repro needs THIS branch — on `main` the fixture's slash
  staff dies under optimize and the provider retries flat. Split
  first: `svg_text.py` out of decompose (455 → 382). Full suite green
  (2148), 12 old goldens byte-identical. Unproven under a human's eye —
  the thing to do is click the "3" and the bracket in m28 and drag
  their onsets.
- 2026-08-10 (system hide) — **A staff can hide for ONE system**
  (`beta/f-hide-parts`, UNMERGED): Marcus's correction — per-part was
  not enough, he wants "hide the drums HERE, keep them next system".
  Verovio 6.2.1 still ignores `staffDef@visible` (re-spiked), so the
  mechanism is the region fill run backwards: `doc.system_staff_hides`
  (rides v12, keyed by the system's starting measure ordinal — the
  break maps' convention, inert+warned when stale) strips the part's
  non-sounding measures to whole-bar forwards at the Verovio seam and
  optimize hides the staff there. Sounding notes are NEVER stripped
  (kept + warned), the rule-10 guard exempts deliberate hides, and the
  slash synthesis skips a staff that is not there. The context menu
  grew "Staves in This System" — the band under the right-click, one
  checkable entry per part, grayed when the mechanism cannot work
  (notes there / hiding off / system 1 without the first-system
  option), never grayed when already hidden so a stale override stays
  clearable. Full suite green; goldens untouched (no override = no
  strip). Unproven under a human's eye — the thing to feel is
  right-clicking a drum slash system and watching only that system
  thin.
- 2026-08-09 (hide) — **Right-click Staves menu + hiding survives
  breaks** (`beta/f-hide-parts`, off `main` after `beta/f-move-onset`
  merged on Marcus's call, UNMERGED): two halves. (1) Per-part manual
  hiding: `doc.hidden_parts` (rides v12), `SetPartHidden` (refuses the
  last visible part), the part removed at the prep seam (condense
  mechanics; `PreparedScore.all_parts` keeps the full roster so the
  menu can re-show), threaded through all three provider prepares; the
  stage view grew ONE `context_menu_requested` signal and the menu
  lives in new `ui/stage_menu.py` (built fresh per popup — no resync).
  (2) The "staves don't always hide" bug was the rule-10 fallback going
  score-wide when a break isolated a slash measure; fixed by invisible
  notes in region measures at the Verovio seam ONLY
  (`region_fill.py` — invisible RESTS don't work, the clef's
  middle-line NOTE does, spike-measured; decomposer skips the fill
  ids; canonical bytes/music21/note_records untouched). Hiding WORKS
  on testscore now, so five old flat-calibrated pins were repinned.
  ONE golden moved 3 lines (video_test_hidden — a real dashed bracket
  at Drums m23 draws for the first time; Marcus blessed the diff).
  Full suite green. Unproven under a human's eye — the things to feel
  are the right-click menu on a real score and hiding holding through
  break edits. Watch out for one thing: a PySide6 `addMenu(str)`
  submenu is Python-owned and dies with its wrapper — build submenus
  as `QMenu(title, parent)`.
- 2026-08-10 (tied) — **"Tied notes as one"** (`f-tied-as-one`, off
  `main`, UNMERGED): Marcus's option — a tied chain appears whole at
  its chain start, and note-value effects (and the volume window) run
  the full tied length. `doc.tied_notes_as_one` rides v12 sparsely
  (written only when True), `SetTiedNotesAsOne` beside SetTriggerBeat,
  checkbox under Sweep in the Effects panel. Mechanism: the glow's
  chain walk extracted to `core/animation/tie_chains.py`;
  `build_trigger_schedule(tied_as_one)` retargets continuation heads —
  the OPTION-SCOPED reversal of the 2026-07-22 grow-with-playhead
  ruling, off is that ruling untouched (pinned) —
  `resolve_durations(tied_as_one)` gives every chain link the chain
  span so all links run one effect window, and the reveal anchors fold
  to chain start. Toggling live re-derives schedule + reveal tracks
  (no Verovio); `set_schedule` grew an optional reveal_tracks. Watch
  out for one thing: the glow scope must keep BASE durations — chain
  spans measured off tied durations double-count. Full suite green
  (2099), goldens untouched. Unproven under a human's eye — the thing
  to feel is a long held note with a swell on (video_test has 24x
  chains) and the toggle mid-playback. `render/animate.py` at 408 —
  over the ceiling, flagged not paid (the items.py precedent).
- 2026-08-09 (hotfix) — **Drum staves lose their key signatures**
  (`beta/f-move-onset`): Dorico exports the score's key on percussion
  parts too; a new prep pass (`_suppress_percussion_key_signatures`)
  zeroes any `<key>` in force while every staff shows the percussion
  clef. 7 goldens re-captured (diff is exactly the drum keysigs, plus
  the leftward shift on bar_repeat_min); censuses −3/−15.

- 2026-08-09 (retime, round 4) — **The ruler escapes the system mask,
  ticks top-align** (`beta/f-move-onset`, UNMERGED): system mode
  clipped the ruler because a scene item paints UNDER the view's mask;
  the ruler is view-painted now — `drawForeground` gained ONE overlay
  hook after every mask path, `render/onset_ruler.py` became a paint
  function, the controller invalidates the viewport on tick changes.
  Ticks hang from one shared top line, bars deepest (pinned in
  pixels). Full suite green (2079). **`ui/stage_view.py` is at 481**
  — the standing most-overdue split (gesture handlers), this hook
  added ~10; flagged, not paid — input-code surgery wants its own
  session.
- 2026-08-08 (retime, round 3) — **Grid snap, tick ruler, and the
  hand cursor** (`beta/f-move-onset`, UNMERGED): Marcus's corrections.
  The cursor snaps to the union of events and an eighth-note grid
  (`core/animation/onset_grid.py` — tick x interpolated between event
  stops, stretched to the system's right edge; `snap_targets` keeps a
  16th-note EVENT snappable while the ruler shows only eighths), a
  Dorico-style ruler hangs bars/beats/eighths above the selected
  system (`render/onset_ruler.py`, hit-transparent), and the line got
  the idiomatic pair: pointing-hand hover over its grab band, thicker
  while held. BEAT ticks are quarter-based for now — meter-aware beats
  need the meter, which MeasureInfo does not carry; a 6/8 bar shows
  quarter ticks. Full suite green (2078). Unproven under a human's
  eye — the things to feel are the ruler's heights/grey on both page
  modes and whether eighth-ticks crowd a dense system.
- 2026-08-08 (retime, round 2) — **The onset is a line you can grab**
  (`beta/f-move-onset`, UNMERGED): Marcus confirmed the stepping works
  and asked for the on-page cursor. A selection-orange vertical line
  spans the selected element's system band at `x_at(stops, beat)` (new
  pure helper — off-stop times draw between their neighbour stops);
  dragging snaps stop to stop (`nearest_stop_to_x`) and release
  commits ONE SetTriggerBeat. First true overlay item in the score
  scene (`render/onset_cursor.py`); gesture is view-level through a
  new `DragRouter` (cursor probe first, nudge second — the stage view
  keeps its one probe slot untouched, and a claimed press never
  becomes a selection click). Full suite green (2071). Unproven under
  a human's eye — the things to feel are the grab tolerance (10 page
  units), the live stop-to-stop snap, and whether the line reads as
  draggable at all. Known gap: the line does not ride a system-pulse
  scale (top-level item, not in the group) — invisible unless pulsing
  while editing.
- 2026-08-08 (retime) — **You can move WHEN an element fires**
  (`beta/f-move-onset`, UNMERGED): `trigger_overrides` on the document
  (absolute beats, rides v12, stem_directions shape), consumed by
  `build_trigger_schedule` after its four rules — an overridden
  element is never FRESH (the displaced-sig rule), anchor kinds can
  never be moved, so the reveal tracks provably cannot change. A
  change rebuilds the schedule LIVE from the loader's newly retained
  join mapping (**~36 ms on complex3's 19k elements**, no Verovio, no
  scene rebuild) through the new `AnimationApplier.set_schedule`, and
  the retained `AnimationInputs` follow so export keeps the moved
  time (pinned from the export side). Selection panel grew a Fires
  row + Earlier/Later/Reset walking the onset stops of the element's
  own system (`core/animation/onset_stops.py`, x carried for the next
  step's drag indicator). Full suite green (2062). Watch out for one
  thing: `set_schedule` must restore the CTOR's construction state
  (empty seconds AND no tempo map) before re-resolving effects, or
  the glow resolve indexes an empty seconds list — the window test
  caught it. Unproven under a human's eye; the on-page drag indicator
  is the NEXT step.
- 2026-08-08 (later) — Merged `beta/f-glow-orthogonal` and
  `beta/f-video-canvas` into `main` on Marcus's instruction (schema
  v12 now on `main`). Full suite green before and after. Pushed.
- 2026-08-08 — Remote sync: pushed `main` (64 commits, `d0af1b5..15ad4b6`),
  the `v0.2-beta.6` tag and the two unmerged branches
  (`beta/f-glow-orthogonal`, `beta/f-video-canvas`) to GitHub. Corrected
  the NOW block: `fix/bracket-hidden-staves` was already merged. No code
  changes; the merge decision on both beta branches stays with Marcus.
- 2026-08-07 — **Staff line thickness knob** (`beta/f-video-canvas`,
  UNMERGED): the fourth engraving knob, and the groove is now fully
  worn: `EngravingParams.staff_line_width` (a factor of Verovio's
  `staffLineWidth` 0.15 default, saturating at its hard 0.1–0.3 →
  70–200 %), sparse v12 key, `SetStaffLineWidth`, a "Staff lines" row
  in the Video canvas block on the same debounced live field — real
  time, default 100 % = today's look, byte-identical (goldens green).
  Measured (`spikes/staff_line_width.py`): rendered line ink linear in
  the factor (0.90/1.30/2.00/2.70 units at 0.7/1.0/1.5/2.0), heads,
  stems, page and pagination untouched. **Barlines ride the same knob**
  (Marcus's rule, same day: never tuned separately, always a fixed
  ratio with the staff lines) — `barLineWidth` and
  `thickBarlineThickness` at the engraver's own default ratios, neither
  clamping inside 70–200 %; a double bar's two lines measured 2.69 →
  5.38 units each at factor 2, pinned beside the staff-line pin. Watch
  out for two things: the layout BBOX tracks the drawn path, not the
  stroke, so only a pixel render shows thickness — the pin measures
  antialiased coverage over thin runs, skipping beams — and most
  BARLINE elements carry a ZERO-width bbox, so bbox statistics see
  only the multi-line complexes. Unproven under a human's eye.
- 2026-08-06 (round 3) — **The box is solid, Scale is live, lyrics get
  a knob** (`beta/f-video-canvas`, UNMERGED): Marcus's second review.
  (1) "The canvas still moves" was the LIT AREA, not the edge: in
  system mode the visible region was band∩frame, so the box reshaped
  with every system. The frame now fills WHOLE — preview color, or
  the page's own background (forwarded from light/dark mode) — and a
  neighbor system's in-frame ink masks with that same fill; letterbox
  exists only outside the frame. One still rectangle whose content
  changes, pinned by a pixel test. (2) **Scale previews in real time**:
  `LiveField` gained `delay_ms` — a debounced preview, once per typing
  pause, which is what makes a ~0.6 s re-engrave livable. The preview
  re-engraves into the running playback BEFORE the commit; the commit
  is still one undo entry and costs no second engrave (pinned on a
  real window). The one-day-old `reengrave_fields` exemption is gone
  again — a re-engraving field is just a delayed live field now, and
  the LiveField doctrine text says so. (3) **Lyrics size**
  (`EngravingParams.lyric_size`, rides v12 sparse): a factor of
  Verovio's `lyricSize`, because lyrics crowd first when the score
  grows. Measured (`spikes/lyric_size.py`, complex2's 588 syllables):
  lyric heights linear in the factor, noteheads and page untouched,
  saturation outside ~45–175 % (the command range). Same debounced
  panel field, row "Lyrics" under Scale. Watch out for one thing: the
  end-to-end lyrics pin engraves complex2 twice and costs ~65 s —
  complex2 is the ONE fixture whose lyrics reach the layout
  (grieg_short's four never draw). Full suite green (2017), goldens
  untouched. Unproven under a human's eye — the things to feel are
  the solid box through a playthrough, the ~0.4 s + engrave latency
  on a Scale spin, and whether 70 % lyrics read on a real chart.
- 2026-08-06 (later) — **Scale sizes the score, and the canvas holds
  still** (`beta/f-video-canvas`, UNMERGED): Marcus's three corrections
  to the morning's feature. (1) **The canvas moved during playback** —
  measured: 4 px between systems (fitInView clamped against the
  frame∪page union's uneven scroll slack), and 1 px left after fixing
  that (position-dependent integer scrollbar rounding). The canvas has
  its own fit now (`_fit_canvas`): direct zoom with no fitInView
  margin, one constant overscan scroll rect per page, and the frame
  snapped a quarter device pixel off the integer grid so every
  rounding lands the same side. Probed and pinned: identical viewport
  corners across all pages, systems and modes. The snap costs a
  sub-device-pixel sliver at the page's exact corner (unclickable —
  a real click lands on a whole pixel; the test insets by one). (2) A
  system band still centers vertically in the canvas — that was
  already true; the movement was the fit, not the centering. (3)
  **Scale was born a crop and is now a rastral size**: Marcus wants
  bigger NOTES, not a magnified window. `EngravingParams.scale`
  (rides v12), consumed at the Verovio seam as `scale` percent with
  the `scaleToPageSize` it already sets — measured first
  (`spikes/score_scale.py`): page constant, ink linear, testscore
  overflows at 130 % and the rule-7 never-clip repagination absorbs
  it (scale-to-fit's percent now derives from the user's base, so it
  keeps the last word). Crowding within a system is the user's to
  solve with system breaks, per Marcus. `VideoCanvas` is width+height
  only; the frame always shows the whole page; a pre-release
  stage.canvas.scale on disk is IGNORED on read (crop and size are
  different meanings — noted in the schema log). Because Scale
  re-engraves, the panel commits it on the finished edit — the
  live-field rule gained its ONE exemption (`reengrave_fields`,
  enforced by the same scan), and `needs_reengrave` now diffs
  `doc.engraving`. Full suite green (2011), goldens untouched (1.0
  sets nothing). Unproven under a human's eye — the things to feel
  are the canvas holding still through a whole playthrough and
  whether 130 % reads as "bigger notes" on a real score.
- 2026-08-06 — **The video is framed in the app now**
  (`beta/f-video-canvas`, off `beta/f-glow-orthogonal`, UNMERGED):
  Marcus asked for an export aspect he can SEE (1080×1920 etc.), a
  score scale inside it, and a way to judge the overlay on black.
  **Schema v12** (his approval, same session): `VideoCanvas(width,
  height, scale)` on `StageConfig`, None meaning the page-aspect frame
  every project has had — no read gate, sparse key, a v11 reader
  refuses a v12 file. This REVERSES half of Phase 10R: the free-form
  canvas that phase removed is back as document intent, and 10R's
  constancy survives narrower — one user shape for both modes, every
  frame. ONE pure function is the whole seam
  (`core/engraving/canvas.py::canvas_view_rect`, the inverse of
  `centered_fit`): the stage fits its view to that rect
  (`ui/stage_frame.py`, letterbox mask + 1 px edge; clicks stop at the
  crop) and export renders exactly it, so the composite matches by
  construction — pinned from both sides (viewport pixels offscreen; a
  notehead's ink at the predicted pixel in a real 1080×1920 PNG
  export, both modes, corners transparent). Scale > 100 % crops at the
  frame edge — user FRAMING, not engraving clipping; RULES rule 7 got
  the one-line clarification (in this diff for Marcus's eyes; CLAUDE.md
  untouched). Inspector grew a "Video canvas" block (presets, W/H,
  Scale — all LiveFields) plus **"Preview on video"**: black default +
  picker, painted view-side behind the ink with the paper hidden —
  QSettings, never the document, never a frame (R1 stands, pinned).
  The export dialog shows a document canvas READ-ONLY (the size has one
  home); no-canvas docs keep the height spinbox verbatim, and the whole
  pre-canvas export suite passes unmodified. BACKLOG 11 partially
  resolved (size left R3; fps/format/alpha/range/path stay session).
  **Three split-first commits** paid standing debts: `ui/export_run.py`
  out of the dialog, `core/project/serialize_style.py` out of
  serialize, `ui/score_install.py` out of the window (412 → 326).
  Full suite green (2019). Unproven under a human's eye — the things
  to feel are the frame edge at odd zooms, typing in the W/H fields,
  and whether the crop at high Scale reads as intended framing.
- 2026-08-06 — **The glow going solid in Premiere was an ALPHA reading,
  not an animation bug** (`beta/f-glow-orthogonal`, UNMERGED): measured
  the export end to end first — the exported
  frames' glow state is byte-for-byte the live applier's at every frame,
  and it tracks the envelope, radius, density and colour exactly (a
  scratch spike walked both paths side by side). The difference appears
  only once Premiere has a clip UNDERNEATH: it composites our
  straight-alpha frames as if they were premultiplied, so the halo's
  own colour goes on at full strength with alpha used as a mask. A real
  halo pixel: alpha 70/255 carrying gold (251,197,91) — correct over
  black is (69,54,25), read as premultiplied it is the full
  (251,197,91), **3.6x brighter**, and every soft edge in the frame goes
  hard. It is not glow-specific; ghost ink and fades take the same hit.
  Marcus A/B'd two clips in Premiere and premultiplied is the one that
  matches, so **`AlphaMode` is now an export setting with premultiplied
  the DEFAULT** (`render/encode.py`, one dropdown in the export dialog,
  session memory per R3) — Premiere has no straight/premultiplied
  switch the way After Effects does, so the cure is on our side.
  Straight stays available for the tools that read it. Watch out for
  one thing: the matte has to be **relabelled** as plain RGBA (same
  bytes, a name Qt will not undo), because `pixelColor` un-premultiplies
  whatever the format says AND Qt's PNG writer converts premultiplied
  data back to straight on save — a premultiplied label would have
  shipped straight PNGs and a test that read `pixelColor` would have
  said everything was fine. Verified through the real encoder: a
  premultiplied clip's colour channel decodes to the app's own
  over-black composite within 2/255 (max channel difference 2, mean
  0.002 over the whole frame). Full suite green, no schema bump, no
  golden movement. Unproven in Premiere on the final build — the thing
  to check is a real overlay. If it ever reads wrong BOTH ways the next
  suspect is the sequence compositing in linear colour (the linear
  reading of that same halo pixel is 141,109,47, 2x the correct one).
  **`ui/export_dialog.py` is at 425** — it was already at 404 before
  this, and it is a split due: the settings form and the chunked run
  are two jobs in one file.
- 2026-08-06 — **Only notes glow, and a tied note is one note**
  (`beta/f-glow-orthogonal`, UNMERGED): the glow ran on the animation
  denylist, so a meter, a key signature, a rest and a dynamic all lit up
  with the notes. It runs on its own **allowlist** now
  (`GLOWING_KINDS`, new pure `core/animation/glow_scope.py`): noteheads,
  the slash and bar-repeat signs that stand in for one, the accidental
  in front of one, the syllable under one, the tie between two, and
  **everything drawn as part of a note** — stem, flag, beam, tremolo
  strokes, dots, articulations, ornaments, tuplet brackets, ledger
  dashes. (Marcus first said head-and-accidental only, then corrected it
  the same session; the correction cost **one frozenset and two test
  expectations**, which is what the allowlist is for.) **A slur is dark
  where a tie glows**, the one place those two spanners part company.
  Dots ride in on `ElementKind.OTHER`, so the ornaments and the tuplet
  brackets come with them — all note ink, but they cannot be separated
  until OTHER is split into real kinds in the adapter. That is a THIRD
  scope list beside `STATIC_KINDS` and `TINTED_KINDS`, and deliberately
  not merged with either: the denylist is right for "does this animate",
  where a new kind should join for free, and wrong for the glow, where a
  new kind should be dark until somebody decides it is a note. Cost is
  **level with `main`** now that most ink glows again (497 sprites
  against 452, 0.66 ms a frame on the first pass against 0.70); the
  narrow first cut measured 76 and 0.21, so the price of the wider rule
  is known if it ever matters.
  **A tied chain glows as the one note it is**: every head plus the tie
  ink lights together at the chain start and dies together when the last
  of it stops. Marcus's second call: that is a GLOW rule only —
  **appearance is untouched**, so a continuation head still fills in as
  the playhead reaches its own barline and schedule.py rule 1 stands
  (with it the complex3 phantom fix). The chain's first head owns the
  halo, everything else copies it, and the halo is stretched to the
  chain by a SECOND evaluation with a chain timescale, so a pop or a
  swell on the same note still runs on the notehead the user can see.
  That second evaluation also widens the trigger's window, or every
  follower would freeze mid-glow when the leader's own note ended.
  Chains are pitch-matched inside one (part, staff, voice) — a chord
  holding one note while the others move ties only that one. Attached
  ink joins through the nearest head, the pop-pivot idiom, so
  `scale_groups._nearest_head` is public. Measured
  (`spikes/tie_glow.py`, `spikes/glow_scope.py`): 58 chains on
  testscore, 234 on video_test, each running 2.3–3.9x its first
  notehead's own duration; every tie on five fixtures finds its note
  through the existing rule-3 key, `:seg` halves included.
  **The reveal clip now cuts the sprite too.** It was moot while nothing
  clipped ever glowed; a tie is clip-revealed, so without it a held
  note's light stood a bar ahead of the ink. Watch out for one thing
  when comparing the two: a clip is clamped to each item's OWN bounds
  and the halo's box is the ink's plus the blur margin, so the two
  report different local edges for one scene x. **`animate.py` was split
  first**, its own commit (395 → 369): the schedule's rows against a
  scene are now `render/trigger_index.py`. No schema bump, no golden
  movement, full suite green. **`items.py` is at 402 and `animate.py`
  back at 399** — both over the ceiling, and `items.py` is the next
  split, though its class docstring argues it is genuinely one job.
  Checked end to end in the real window offscreen: over a whole
  playthrough exactly the ten kinds on the list ever light, nothing
  outside it does, and undo puts every halo out. Rendered a frame
  mid-chain on a dark page and looked at it — head, stem, tie, head read
  as one held object, with the 4/4 right beside it dark. Unproven under
  a human's eye; the thing to feel is whether a whole held note lighting
  at once is too much light on a busy page.
- 2026-08-05 — **Each glow knob changes one thing**
  (`beta/f-glow-orthogonal`, UNMERGED): the block had two knobs on one
  axis and one knob doing two jobs. **Strength is retired** — it reached
  the envelope as `spec_envelope`'s amount, which multiplies the sustain
  and the swell's level and nothing else, so it was Sustain a second
  time. An old project's value folds into those two levels **on read**
  and the key goes (`fold_strength`, three lines in `_style_rules_in`
  beside the v1 `part_colors` fold). The fold WRITES, unlike the
  `shape`/`peak` fold next to it, and that is the whole design: at
  consumption it would multiply again the moment the user edited
  Sustain, because the panel would write an explicit level under a
  `strength` still on disk. Checked end to end: a file carrying
  `strength 0.6` opens as sustain/swell_level 0.6, glows at the same
  0.600 the old two-knob path did, and the panel says 60 % with no
  Strength row. **Radius is size only** — a blur spreads the same light
  thinner as it widens, so the halo used to dim as it grew (74 → 28 of
  255 from radius 18 to 60). Each sprite is now scaled after the blur so
  its brightest point matches what the SAME ink reaches at radius 24
  (`_normalize`, `render/glow_build.py`): per shape, so a thin stem
  still glows fainter than a fat notehead, and **the gain at 24 is
  exactly 1.0**, so no second blur runs and every saved project renders
  as it did. The scaling is `_thicken`'s shape with
  CompositionMode_Plus, which ADDS — a true linear scale, and the only
  way past Qt's opacity ceiling of 1 for the radii that need brightening.
  It runs BEFORE the density pass, which is what keeps those two knobs
  independent too. Measured on testscore: peak alpha flat at
  163/163/164/164/164 across radius 12–60 where reach goes 4 → 22 units.
  **`glow_sprite.py` was split first**, its own commit (378 → 191): how
  a pixmap is drawn is now `render/glow_build.py`. Watch out for one
  thing: **`spikes/glow.py` had been printing zeroes since 2026-08-04**
  — it measured at the trigger, where the default envelope is dark now —
  **and reading the halo as the ink since 2026-08-02**, because an
  item's bounds include its sprite child. Both repaired, both worth
  remembering: a spike can rot silently. No schema bump, no golden
  movement, full suite green. Unproven under a human's eye — the thing
  to feel is whether radius 36+ is usable now that it stays bright.
- 2026-08-04 — **You can draw the glow's shape now**
  (`beta/f-glow-effect`, UNMERGED): an "Envelope" header in the Glow
  block opens the classic synthesizer picture — time across the note,
  level up the side — and the four handles drag the same six values the
  boxes hold. **The curve is SAMPLED from the envelope that plays**
  (`spec_envelope`, one point per pixel), so the eased segments on
  screen are the ones the score runs rather than a drawing of them. A
  drag is the live field's contract with a mouse: every move previews,
  the release is one undo entry, and the canvas refuses a resync
  mid-gesture — a picture cannot be focused, so nothing else would stop
  the preview redrawing under the hand. **Handles stop at their
  neighbours live** (`core/editing/envelope_drag.py`, pure): the clamp
  is the consumer's own, so an invalid envelope is unreachable rather
  than corrected after the fact, pinned by a fuzz over the whole canvas
  on five starting shapes. The swell point moves two params at once, so
  `SetEffectParam` grew an `also` — the fat-apply idiom, not a compound
  command — and says "change effect options" when it carries more than
  one key. No schema bump, no golden movement. Marcus's two calls: the
  fill is the palette's highlight, not the glow colour (the widget will
  host other effects), and the block opens CLOSED. **Two split-first
  commits**: `knob_types.py` out of `effect_knobs.py` (388 → 276), and
  the generic `EnvelopeSpec`/`clamp_spec`/`spec_envelope` out of
  `glow.py` into `core/animation/envelope_shape.py` so nothing in the
  editor says "glow"; the envelope's own gesture then went to
  `ui/panels/envelope_row.py` when the wiring took `effect_knobs.py`
  back to 383 (now 305). Checked end to end in the real window
  offscreen: dragging the attack to 50 % takes the light at 5 % of the
  note from 0.875 to 0.271, the box follows the handle, and undo puts
  the document, the box and the picture back. Rendered eight shapes and
  looked at them — the labels of a full release and a zero attack meet
  at the same x, so they go to opposite ends rather than over each
  other. Unproven under a human's eye.
- 2026-08-04 — **The glow's shape is user data now**
  (`beta/f-glow-effect`, UNMERGED): the pop/swell switch is gone and the
  halo runs a synthesizer envelope — attack, sustain, an optional swell
  hump on the hold, release — every one of them a FRACTION of the span,
  so the shape keeps its proportions whether the span is the note's own
  value (the default) or a typed duration. The swell Peak precedent, and
  it costs nothing at the windows seam: the last keyframe still sits at
  1.0 × the authored duration, so `Effect.duration` and the timescale
  arithmetic never moved. **The envelope ends at exactly 0 when the span
  does, by construction**, which is what keeps a glow to the sounding
  notes. Easings are Marcus's call: attack EASE_OUT (curls gently into
  the hold), release EASE_OUT (leaves at once, lands soft, the way a
  note rings out), the hump EASE_IN up / EASE_OUT down. That pair is
  also what makes **both old shapes reproduce byte-for-byte** — old pop
  IS attack 0 + a full-span release, old swell IS the hump with nothing
  held — so `shape`/`peak` are read as per-key DEFAULTS for the six new
  ones (the v1 `part_colors` fold's rule, an explicit new key always
  wins) and never written again. The ordering is enforced where the
  params are consumed, because `Envelope` refuses keyframes that do not
  strictly increase: attack + release that overflow scale down together
  keeping their balance, and the hump is clamped strictly inside the
  hold or dropped when there is no room — 13 degenerate combinations
  pinned to degrade instead of raising. The panel needed its own store
  (`GlowParamStore`) so an old project's boxes describe the shape it is
  actually glowing in rather than the new defaults — the `forced_by`
  argument, on a second setting. **No schema bump** (`style.effect_params`
  round-trips raw), no golden movement. Watch out for one thing: the new
  default is NOT lit at the onset, so three test files that assumed
  "full light at t=0" now pin the instant-on shape explicitly
  (`attack: 0, release: 1`). Checked end to end in the real window
  offscreen: the light rises over the attack, holds at 1.000, dips to
  0.500 where a swell at 50 % says, and reads exactly 0.000 at the span
  end. The `Choice` knob type has no user left now that the Shape
  dropdown is gone — kept, not deleted. Unproven under a human's eye.
  *(The envelope EDITOR canvas is the next step.)*
- 2026-08-03 — **Stems point the right way, and F flips one**
  (`beta/f-stem-directions`, UNMERGED, off `main`): the wrong-way stems
  are not random. **Dorico exports the WRITTEN score's directions and we
  engrave concert pitch** (rule 9) — transposing moves notes across the
  middle line and the `<stem>` does not follow. Measured over 7 fixtures
  (`spikes/stem_dirs.py`): **6.5–34.3 %** of unbeamed single-voice stems
  were drawn on the wrong side, and the error is about **seven times
  denser in transposing parts** (34.5 %) than in concert-pitch ones
  (5.1 %). `_normalize_stem_directions` drops `<stem>` wherever a staff
  carries ONE voice in a measure and lets Verovio decide from the pitch
  it actually draws — every fixture goes to **100 %**, and Verovio gets
  beam groups and middle-line notes right on its own. A staff with two or
  more voices keeps exactly what the file encodes (Marcus's call, so
  divisi is never overruled). It runs **before `_apply_condense`**, which
  fixes condensing for free: each source player is single-voice, so after
  the merge Verovio applies its own v1-up/v2-down — measured, the two
  voices stop being offset **27 units sideways** and 7 duplicate ledger
  dashes go. **`F` on the stage** flips the selected note, cycling up ↔
  down only. Two things made it less obvious than a nudge: the user
  selects a NOTE but the document keys a STEM (joined through the
  schedule's existing note group, so a chord's heads all name one stem
  and the command needs no fan-out), and **nothing records which way a
  stem points** — it is read off the drawn ink, so `F` flips away from
  whatever is on the page. Bare `F` is stage-scoped, pinned
  EMPIRICALLY rather than by a scope assertion: "flute" still types into
  a QLineEdit anywhere in the window, including inside the stage view.
  **No schema bump** — fourth feature to ride the untagged v11 — and the
  automatic half stores nothing at all, so every already-saved project
  re-engraves with corrected stems. **11 of 12 goldens re-captured with
  Marcus's eyes on the diff**; `pickup_min` is the one fixture with no
  `<stem>` at all, so it stays the clean control for the five
  comparator-sensitivity tests. `note_records`, `measure_timeline` and
  `pages` moved nowhere, which was the bisect. Watch out for one thing:
  **`scaled-to-fit` shifted 1 %** on complex3 and tall_system_min
  (70→71, 90→89), because stem directions change a system's height — and
  that moved 100 % of those two fixtures' rows. A small visual change is
  not a small golden diff. **`musicxml_rewrite.py` was split first**, its
  own commit with no feature code (509 → 269): the break passes are now
  `core/score/musicxml_breaks.py`. Unproven under a human's eye — the
  thing to look at is a transposing part, which is where the 34 % lives.
- 2026-08-02 — **The glow goes all the way to solid**
  (`beta/f-glow-effect`, UNMERGED): a **Density** knob, 0–100 %, for
  Marcus's "there should be options so at the very extreme the glow is
  basically a solid color". The halo could only ever be soft — a blur
  fades from the ink outwards, so even at full Strength the light is
  thin, and Strength itself is the halo's own opacity with nothing past
  1. Density lays the same blurred sprite down over ITSELF n times, so
  the alpha at a point goes 1 - (1 - a)ⁿ. Ordinary painting, not
  adding: every pass is the same colour, so the alpha climbs and the
  hue stands still (adding would wash the warm gold out towards white
  — pinned by a test). The third STYLING number, not an animated one:
  it rides `read_glow`/`GlowStyle` beside colour and radius, joins the
  sprite cache key, and costs nothing per frame — the applier still
  writes one opacity. **No schema bump** (`style.effect_params`), and 0
  is one pass, which `_thicken` hands back untouched, so every document
  already saved renders exactly as it did. The knob is a per cent over
  a curve, 1 to 32 passes: an even spread would waste its top half.
  **Measured on testscore** (`spikes/glow_density.py`): at 24 radius
  the halo's alpha 4 units out from a notehead goes 21 → 98 → 238 of
  255 across 0/50/100 %, and it fills the halo IN rather than spreading
  it — the reach stops at 12 units and CANNOT go past the blur, so
  radius is still the knob for how far and the two together are how you
  get a big solid halo (rendered four pages and looked). 32 passes is
  the top because past it the change is all in the tail. Cost is
  build-time only: lighting every element of every page at once, 456
  sprites, 780 ms at 0 % against 993 at 100 %, and a replay still
  builds nothing. Checked end to end in the real window offscreen:
  100 % in the box takes the halo from 21 to 238, undo puts the box and
  the halo back. Unproven under a human's eye.
- 2026-08-02 — **The glow is fast now** (`beta/f-glow-effect`,
  UNMERGED): the live drop-shadow effect re-blurred every halo on every
  repaint, at device resolution — playback lagged on stop, scrub and
  zoom. Replaced by pre-rendered sprites (`render/glow_sprite.py`,
  `glow_effect.py` deleted): a glowing element gets a pixmap child
  BEHIND its ink, the silhouette in the glow colour blurred ONCE at
  first light, and a frame writes only the sprite's opacity. Cached by
  shape: the whole of testscore is 900 glowing elements sharing 300
  pixmaps, the first pass costs 495 ms in total (1.2 ms a frame,
  builds included) and a replay builds nothing — pinned by tests, as
  are z-order, transform inheritance, restyle-rebuild and the stale
  extinguish. Page at 1400 px with 74 halos lit: 8 ms against 4 dark,
  where the live effect measured 133 against 92. Qt's blur effect
  spreads half again as far as the drop shadow's at the same radius
  (measured, alpha profiles), so a 0.6 factor (`_BLUR_MATCH`) keeps
  the calibrated radius-24 look; reach holds at 9–10 units for radius
  20 at every zoom. Dropped with the old effect: the 30 % reach
  pull-in as a glow dies (the fade is brightness-only now). Gained: a
  mid-pop halo scales with its ink, and the one graphics-effect slot
  per item is free again. Unproven under a human's eye — stop, scrub
  and zoom mid-glow are the things to feel.
- 2026-08-02 — **A sounding note glows**
  (`beta/f-glow-effect`, UNMERGED): a warm halo around the ink that
  lights at the onset and dies exactly when the note's value ends — so
  only the notes actually playing glow. The **first new animatable
  PROPERTY since the slide offsets**, and it cost exactly what the
  architecture says it should: one `PropertyId`, one row in the compose
  table, one applier entry, one preset. Glows take the BRIGHTER of two
  (max, neutral 0) rather than stacking, and GLOW joins
  `MODULATED_PROPERTIES`, so the volume response brightens a loud note's
  halo the way it widens its pop; opacity stays out of both. "pop+glow"
  and "swell+glow" needed no code and are checked in the running app.
  No schema bump — the params ride `style.effect_params`, which
  round-trips raw; `SetEffectParam` widened to accept a STRING (the
  colour and the shape are words), which is what its own "type only"
  contract already promised. **The Qt trap, measured before writing
  anything**: a zero-offset drop shadow IS the Photoshop outer glow, but
  Qt blurs at DEVICE resolution, so a raw `blurRadius` of 20 reached
  16.0/10.0/5.0/2.5 scene units at view scales 0.5/1/2/4 — the glow
  would shrink as you zoom and the stage and an export would disagree.
  `GlowEffect` converts from the painter's own transform inside
  `draw()`; measured again on the real page, the halo is 8.0 units at
  every zoom. The effect is built on the first nonzero strength and
  disabled at 0, which Qt skips entirely, so ink that never glows costs
  nothing — 88 of 1691 items ever grew one on testscore, 64 lit at
  once. **Default radius 24** (`spikes/glow.py`): a wider radius spreads
  the same light thinner, so 18/24/36 reach 7/8/8 units at brightnesses
  74/66/49 of 255 — rendered all three on a dark page and 18 reads as a
  rim ON the ink, 36 as fog. Cost: 0.27 ms a frame to evaluate, and a
  whole page at 1400 px goes 92 → 133 ms with 74 halos on it. Peak has
  no knob on purpose (swell shape only). **Two splits first, each its
  own commit**: `render/items.py` 396 → 357 (SVG paint helpers to
  `render/svg_paint.py`) and `effects_panel.py` 379 → 277 (the knob
  table to `ui/panels/effect_blocks.py`). A document that never touches
  glow renders byte-identically to `main` — 21 pages over testscore,
  video_test and complex1, sha256. Unproven under a human's eye.
- 2026-08-02 — **Light mode or dark mode**
  (`beta/f-page-colors`, merged `6d89f1b`): the score is either black on
  white or white on a dark blue-grey (`#1d1f24` — not black, which is
  harsh under a white staff, and it is the tone the app's own lane and
  waveform chrome already use). Built first as two free colour pickers;
  **Marcus cut it back to one choice** the same session, which is also
  the better model — the document stores the MODE and the two colours
  are derived from it (rule 5), so a later change to what dark looks
  like reaches every project that chose it. Per-colour fine-tuning is
  deferred, and the sparse entry has room for it. Appearance, not
  animation — one pass over the items when the style changes, like the
  floor opacity, and nothing per frame. One sparse `style.colors` entry
  beside `volume` and `pulse`, **no schema bump** (v11 is untagged; the
  reasoning is written into the schema log so it is not re-litigated).
  Validated at CONSUMPTION and, unlike `read_volume`/`read_pulse`,
  genuinely fail-soft — an unknown mode reads as light rather than
  raising. Scope is **everything**, not `TINTED_KINDS`:
  that list is the scope of a part TINT, and a white-on-black page needs
  white staff lines or there is no staff. Ink is its own composition
  input on `ElementItem` beside the authored colour, which is what lets
  the two apply in either order and stops a recolour corrupting
  DocumentSync's authored-colour cache. **Export needed no wiring** — it
  already calls `apply_style_colors` — and the background deliberately
  still never reaches a frame (ruling R1 stands), so a black page
  exports as white notation over transparency, which is what an overlay
  wants. Marcus's call, and now pinned by a test. Two things the plan
  had wrong, both found by testing rather than reasoning: `set_stage_texts`
  rebuilds its items, so the scene now RETAINS the ink (without it,
  editing the title on a black page turned it black-on-black and no
  cache upstream could see it), and `add_stage_text` tracked on "colour
  is None" where its sibling uses `fill_tracks_color`. Selection needed
  no change — the tint composites over the EFFECTIVE colour and white
  sits further from the orange than black does; there is a test saying
  so rather than a claim. Pixel identity is pinned with two non-vacuity
  guards. **`render/items.py` was split first** as its own commit (438 →
  365, landing at 396 with the feature): `RevealPathItem` moved to
  `render/reveal_item.py`, which closes the split this file has been
  naming since 2026-08-01. Checked end to end in the real window
  offscreen, both ways and back: dark gives paper `#1d1f24` with every
  kind from noteheads to staff lines to the title at `#ffffff`, the
  selection still orange on it, light restoring exactly `#ffffff`/
  `#000000`, and undo putting the document back to storing `{}`. Page 1
  rendered in both modes and looked at. Opened BACKLOG 28
  (per-colour fine-tuning, deferred) and 29 (deliberately-coloured ink
  does not follow the page — one light-grey credit today, so nothing is
  broken yet). Unproven under a human's eye.
- 2026-08-02 — **Every system jumps when its notes land**
  (`beta/f-system-pulse`, UNMERGED): the system pulse's second mode, an
  onset pop, and it needs **no recording at all** — the schedule is the
  whole input. At every beat the system the notes appear in bumps up and
  eases back over 0.25 s, and the more noteheads land there the harder
  it jumps. Only HEADS count (a stem, dot or beam hangs off a head
  already counted), and each head counts in the system it is DRAWN in,
  not in the trigger's single min() hint — the reveal-grouping
  precedent, which matters at a system break. Overlapping bumps take the
  LARGEST live one, never the sum, so a fast run cannot inflate a
  system. The two modes' DEVIATIONS add (`1 + follow + pop`), so either
  alone is exactly what it was; both at 0 still touches no group. The
  skip is per GROUP now, keyed like the reveal edges, since the bumps
  differ per system. Same sparse `style.pulse` entry, three more keys,
  **no schema bump**. **Measured on testscore** (`spikes/onset_pop.py`):
  **the default notes_for_full of 6 is low** — a six-part score puts a
  median of SEVEN heads on a beat, so 63 of 88 bumps (72 %) already hit
  the ceiling and every jump is the same size; 8–16 is where the
  strengths spread out on this fixture. The frame-to-frame jump IS the
  amount every time (the rise is instant, by design). Gaps close about
  half as fast as the follow half's, because only the firing system
  grows — but 0.20 still overlaps, and the two amounts can reach 1.4
  together. **`render/animate.py` was split first**, as its own commit
  (421 → 363): the volume response's bookkeeping moved to
  `render/gain_index.py`, the third half of the applier after reveal and
  pulse. Checked end to end in the real window offscreen: 10 % in the
  box, system 1 moving over 200 distinct sizes between 1.0 and 1.0996
  while scrubbing, the resting systems at exactly 1.0, undo putting the
  box and every system back. Unproven under a human's eye.
- 2026-08-02 — **The whole page breathes with the recording**
  (`beta/f-system-pulse`, UNMERGED): the branch is
  `beta/system-groups` with `beta/f-follow-volume` merged in, which is
  what the feature needed — the group items on one side, the live
  loudness reading on the other. Every system now takes ONE size at
  time t, `1 + Amount × how loud the recording is there`, each turning
  around the centre of its own ink, so the page swells and shrinks as
  one object. Deliberately not a property track: it is per FRAME, not
  per element, so the evaluator, the compose table and the schema are
  all untouched, and it reads the RAW loudness rather than the volume
  response's gain — two features, one reading, a knob each. Its own
  driver (`render/pulse_driver.py`, the reveal driver's shape), fed
  from the recompute that already runs on both seams that can move it,
  so live preview and export needed no wiring at all. Amount 0 means no
  group is ever touched — the tests spy on `set_system_scale` itself,
  so "never touched" means the call and not the change. **Measured on
  testscore.wav** (`spikes/system_pulse.py`): at 5 % the biggest jump
  between two frames is 2.4 % of the page, which breathes rather than
  shakes — but two systems on page 2 close from 73.9 units to 8.7, and
  at 10 % they OVERLAP by 57. **The 0–20 % range is too generous and
  nothing detects a collision**; 5 % is about where a busy page runs
  out of room, so the ceiling probably wants lowering. Checked end to
  end in the real window offscreen: 5 % in the box, five systems at
  1.05 with a recording loaded, exactly 1.0 without one, and undo puts
  the box and every system back. Unproven under a human's eye.
  No schema bump — the key rides the unreleased v11 beside
  `style.volume` (Marcus's call). *(`render/animate.py` was split on
  2026-08-02, above; `render/items.py` at 432 is still the next one.)*
- 2026-08-01 — **Every system is one object now**
  (`beta/system-groups`, UNMERGED, off `main`): a structural change with
  no visible half. Each element whose system is known hangs off a
  `SystemGroupItem` for its (page, system) (new `render/system_group.py`,
  90 lines); stage texts and page furniture stay top-level. The group
  paints nothing, is hit-transparent by the same empty `shape()` the
  per-element parents already use, and carries NO transform until
  something scales it — so every child keeps the scene coordinates it
  had. The seam for the next step, with no caller: `set_system_scale`
  turns the system around the centre of its own ink, frozen once at
  build (a nudge must not drag that point), 1.0 exactly identity, and it
  re-derives descendant reveal clips, because a scale springs the M3.2
  cached-inverse trap from the other side. The one real risk was paint
  order — synthesis appends slashes and stray ties after the systems
  they belong to, so grouping moves that tail earlier relative to other
  systems on the page. Measured: **21 pages over testscore, video_test
  and complex1 render bit-identically** before and after
  (`tools/render_page_png.py`, sha256). Goldens never moved (they pin
  the core Layout, not the Qt scene), full suite green. Checked in the
  real window offscreen: click-select still lands on the notehead and
  tints it, a nudge still previews and commits 20/−10. Unproven under a
  human's eye. **`render/items.py` is at 430 lines** — it was over the
  ceiling before this and it is still the next split.
- 2026-08-01 — **A swell follows the recording**
  (`beta/f-follow-volume`, UNMERGED, off `beta/f-swell-effect`): a
  "Follow volume" box in the Swell block, off by default. With it on a
  note's size tracks how loud the recording is WHILE IT SOUNDS — a
  crescendo grows it, a diminuendo shrinks it — instead of playing one
  frozen average. The shape changes to suit: a plateau instead of a
  hump, 10 % up / 75 % hold / 15 % back (Marcus's call), where the hold
  is what the live volume plays on and the tail is the snap-back that
  lands the note at exactly its engraved size as the next one arrives.
  Follow forces the note-value stretch on — a fixed 0.8 s window cannot
  track a whole note — and the panel shows that box checked and grayed
  rather than lying about it (new `Check.forced_by`, five lines in the
  shared knob module); Peak grays too, since the top is a stretch now,
  not a point. Three layers, each one small: a third reading in
  `intensity.py` (`intensity_at`, off the ~90 ms level of the pyramid
  the cache already built, interpolated between bins — no new sums), one
  more `Effect` flag beside `settle_to_note_value`, and one choice in
  the applier between the live gain and the average. The flag comes out
  of `derive_windows`, which already walks every effect of every item,
  so the lookup is once per trigger per frame and the peak reference is
  cached on the seams that move it. **`render/animate.py` went 409 →
  367 first**, as its own commit: reveal was never trigger-driven, so
  the index, the warning, the curves and the edge cache moved to
  `render/reveal_driver.py`; it lands back at 398. No schema change, no
  golden movement. Measured on testscore.wav
  (`spikes/follow_volume.py`): across a dotted half the reading runs
  0.40–0.71 and the biggest jump between two frames is 0.13, so it
  breathes without flickering. Checked end to end in the real window
  with the recording loaded — the note holds between 1.36× and 1.46×
  and lands on exactly 1.0. Unproven under a human's eye.
- 2026-08-01 — **A note swells over its own length**
  (`beta/f-swell-effect`, UNMERGED, off `beta/f-pop-per-note`): a fifth
  effect, and the first one about a note's LENGTH instead of its
  arrival. The note is already on the page at its engraved size, grows
  to 1.4× and eases back down to exactly where it started, timed to its
  notated value — a whole note swells across its bar, an eighth is a
  quick breath. Pure preset data (rule 6): one registry entry plus four
  knobs, and nothing in the evaluator, the applier, the compose table or
  the schema. Up on EASE_IN and down on EASE_OUT — gentle away from
  rest, softly back to it — which puts a brief point at the top; both
  ends land exactly on 1.0, so no note is ever left oversized.
  `settle_to_note_value` defaults ON here, the only preset it does, and
  the existing per-element timescale stretches the whole authored shape
  at once, so the top keeps its place inside the note however long the
  note is (Peak, shown as a per cent of the way through). The two
  interactions asked about needed no code and are now pinned: pop+swell
  multiplies into a dip-then-swell, and the volume response modulates a
  swell like any other scale departure. Checked end to end through the
  applier on testscore — a dotted half tops out at +0.75 s where an
  eighth was home at +0.25 s. No schema change, no golden movement;
  unproven under a human's eye in the running app.
- 2026-08-01 — **Every notehead pops in its own place**
  (`beta/f-pop-per-note`, UNMERGED, off `beta/f-volume-duration`): a
  chord's heads used to share one pivot — the centre of the whole stack
  — so the outer ones slid sideways as they grew. Each head now turns
  around its OWN centre, and the ink hanging off it follows the head it
  belongs to: a stem stands on the head at its foot, a flag and tremolo
  strokes ride the stem, an accidental or dot takes the nearest head.
  133 of testscore's 252 note groups are chords, so this is most of the
  fixture. Two Marcus calls with it: **beams never scale** (they appear
  with their note at engraved size — a beam belongs to several notes, so
  any pivot is a compromise), and a **stem stops at its beam**. The stem
  ceiling is a new pure module (`core/animation/stem_caps.py`), a
  geometric stem↔beam join like the ledger dashes', carried on the item
  as `scale_cap` and clamped in one `min()` in the applier. Measured:
  the beam's far edge sits ~3% of a stem's length past its tip, so a
  beamed stem thickens where a flagged one pops with its head; 101 of
  252 stems are capped and none overshoots. The ceiling took two goes —
  a first cut read the beam's BOX and stems grew straight through
  tilted beams (28 of testscore's 38 beams are tilted), so it now reads
  the beam's drawn outline at the stem's own x, across the stem's whole
  width, through a new pure `svg_geom.path_outline`. The same pass found
  a second one on video_test: a beam one staff up was close enough to
  claim an unbeamed stem, so a beam is now this stem's only where the
  tip is drawn INSIDE its ink. Checked over 8 fixtures, flat and with
  staves hidden: 3244 capped stems, zero overshoot, zero beamed stem
  without a ceiling. Applies to EVERY scale
  effect, not just pop, so under drop the heads enter at 3× while the
  beam sits still — deliberate, and it reverses the beam half of the
  2026-07-31 ruling. Rendered rest vs peak and looked at it
  (`spikes/pop_pivot.py`); unproven under a human's eye in the running
  app. No schema change, no golden movement. **`render/items.py` is at
  432 lines** — it was already over the ceiling before this, and it is
  the next split.
- 2026-08-01 — **The gain follows each note's own length**
  (`beta/f-volume-duration`, UNMERGED, off `beta/f-volume-response`): the
  volume response reads a note's whole notated duration instead of the
  moment it starts, and the gain is per ELEMENT, not per trigger — two
  notes on the same beat with different lengths now pop by different
  amounts. Averaging is on ENERGY (mean of rms squared, then the square
  root), one running total per call so each window costs a subtraction.
  Ink with no notated length — dynamics, texts, rests — falls back to
  the old attack reading through a zero-length window, so nothing loses
  its gain. No schema change, no new settings, `peak_reference`
  untouched. Split first as its own commit: the window arithmetic moved
  to a pure `core/animation/windows.py` (`derive_windows` for the settle
  stretches, `audio_windows` for these), which is what kept animate.py at
  409 rather than 450 — still AT the ceiling, and the reveal-index wiring
  in `__init__` is the next seam if it has to come down. `trigger_gains`
  is gone; `window_gains` is the one None contract. Measured on
  testscore.wav (`spikes/volume_response.py`, now prints both readings):
  the average reads **0.80× the attack** over the 1159 elements with a
  length, the spread widens at the quiet end (0.040–1.00 → 0.011–1.00),
  and the busiest frame's largest pop goes 1.24 → 1.15 where it used to
  go 1.24 → 1.34. So it is gentler AND leans quiet — recalibration is
  Marcus's call after he looks at it.
- 2026-08-01 — **Animation strength follows the recording**
  (`beta/f-volume-response`, UNMERGED): a loud beat pops harder, a quiet
  one more subtly. One derived scalar per trigger — the loudest rms bin
  in a window that leans forward onto the attack (−25/+75 ms), over the
  95th percentile of the bins that carry any sound. A percentile, not
  the maximum, or one stray transient flattens every real note; only
  sounding bins, or a silent tail makes quiet music read as loud
  (`core/animation/intensity.py`). The gain scales the FINISHED state
  about the compose table's neutral — SCALE and the two offsets only.
  Opacity is never modulated and never will be: a quiet note still has
  to become fully visible. Gain 1.0 returns the state by an early
  return, not by arithmetic, so amount 0 is bit-identical to before.
  Three settings (Amount, Quiet, Loud) in a sparse `style.volume`,
  **schema v11** — no read gate, a missing key is the response off.
  Live and export share one seam (`AnimationApplier.set_audio`), pinned
  by a test that walks both. The live path reads the peaks on
  `finished`, not `progress`: a half-decoded file's reference is wrong
  and moves every tick. Panel first: `PresetKnobs` became `KnobGroup`
  with a pluggable store, so the Volume response block rides the same
  live fields instead of a second copy. Measured on testscore.wav:
  intensity spreads 0.04–1.00 over 89 triggers, and the busiest frame's
  largest pop goes 1.23 → 1.34 (`spikes/volume_response.py`). Checked
  end to end in the real window offscreen; unproven under a human's eye
  so far. **`render/animate.py` is at 415 lines** — over the ceiling,
  and due a split before anything else lands in it.
- 2026-08-01 — **Effects combine** (same branch): a note can drop AND
  fade, picked with a second "Combine with" dropdown. The stored intent
  stays ONE name — the parts joined by "+" — so no schema bump, and an
  old build opening "drop+shimmer" still drops. Envelopes are never
  merged (two eased curves cannot be merged exactly at their
  keyframes): each part keeps its own tracks, shift and timescale, runs
  through the same kernel, and the RESULTS combine property by property
  in a new pure table (`core/animation/compose.py`). Opacity takes the
  MIN, not a product — every opacity envelope starts at the document
  floor, so multiplying would put a combined ghost below the floor
  Marcus set; scale multiplies, offsets add, all commutative. The
  applier now holds a tuple of effects per element and a timescale for
  each. The property appliers moved to `render/properties.py` first, as
  its own commit (animate.py was at 370). Rendered drop+fade and
  slide+fade to PNG and looked at them; unproven in the running app so
  far.
- 2026-07-31 — **A slide effect** (same branch): notes travel in to their
  place from a direction you pick — Direction in degrees (0 from above,
  clockwise), Distance, Duration and Bounce. Unlike drop it needed two
  NEW animatable properties, `OFFSET_X`/`OFFSET_Y` in scene units, so it
  is three layers, not one: the properties, the applier, the preset. The
  trap was the position: the document's nudge already owned it, so
  `ElementItem` now stores the nudge and the animated offset apart and
  derives `setPos(doc + animated)` — a nudged note slides to its nudged
  place and neither writer clobbers the other (ARCHITECTURE §M3.2). The
  angle becomes two track values inside `build_presets`, once per
  document change, so the evaluator never hears the word "direction".
  Default distance 120 page units — just clear of the note's own staff
  and inside the gap to the next one (rendered and looked at; at 200 the
  note arrives sitting on the staff above). Known compromise, and it
  shows: a beam slides on its first note's trigger, so a later note in
  the group comes in with its stem while its beam is already resting —
  the stem hangs unattached for a moment. Worse here than under drop,
  because a scale keeps the ink roughly where it belongs.
- 2026-07-31 — **A scale moves the whole note** (same branch): a drop or
  a pop used to grow the head and leave the stem behind. Head, stem,
  flag, beam, accidental, dots and articulations now turn around one
  point — the centre of the note's own heads — so the note arrives as
  one object. Ledger lines are the exception: ruled at staff size, they
  keep it, and only fade. The grouping is the key `durations.py` already
  uses (part, staff, voice, quantized onset), so nothing new is stored
  and the adapter is untouched; a beam's onset is its first note's,
  which is what makes the beam fall in with the note it starts on while
  the rest of its group drop onto it. Policy in a new pure module
  (`core/animation/scale_groups.py`), render only applies it: no pivot,
  no scale.
- 2026-07-31 — **A drop effect** (`beta/f-drop-effect`, UNMERGED): notes
  land on the page like a stamp — each one enters at three times its
  size and part-way solid, then shrinks and goes fully solid over
  0.35 s, with a small bounce as it lands. No new property and no
  applier change: it is the existing scale and opacity, so the effect is
  preset data plus one curve, `EASE_OUT_BOUNCE` (the standard piecewise
  bounce, which ends exactly on its target — that is what leaves every
  played note at its engraved size). Knobs: start size, duration,
  bounce. The panel was split first, as its own commit: a preset's knobs
  are now a table entry built by `ui/panels/effect_knobs.py`, and
  `effects_panel.py` went 379 → 232 lines. Stems and beams still appear
  without the stamp — the same compromise pop makes, since scale only
  reaches anchored ink.
- 2026-07-31 — **A fade effect** (`beta/f-fade-effect`, UNMERGED): ink
  rises from the ghost floor to full over a duration, easing out.
  `Easing` gained EASE_OUT and EASE_IN, and `value_at` now looks the
  curve up in a table instead of testing for LINEAR, so the next curve
  is one entry. The effect itself is one registry entry plus its knobs —
  no evaluator, applier or schema change, which the applier tests on the
  real fixture check. Two Marcus calls on the panel: every effect's
  length is now **Duration** with "Entire note value" beside it on the
  same row (the alternative to typing one), and an effect's options only
  show while something resolves to that effect — each preset's block is
  a named heading plus its rows, hidden as a unit. Reset clears pop and
  fade together in one undo step. The panel is at 379 lines: split the
  knob blocks out before adding a third effect.
- 2026-07-31 — **Every number field previews as you type** — the new
  default (`ui/live_field.py`), not the Tempo field's special case:
  Offset, Swing, Amplitude, Settle, Peak offset and Floor opacity all
  show the result on every keystroke and still commit as one undo entry.
  A test scans each host's `live_fields`, so a spinbox added without the
  helper fails the suite. Two things it turned up: a resync must never
  gray out a live field (disabling drops focus, and focus-out commits),
  and Cmd-S was writing the preview instead of the committed document —
  fixed. PATTERNS rewritten; unproven in the app so far.
- 2026-07-30 — **The Tempo field previews as you type**: the ticks move
  on every digit instead of waiting for the click outside, so you can
  see whether a tempo fits the recording while you are still setting it.
  It runs the drag's own preview/commit pair, so the typing session is
  still one undo entry. Two gotchas, now in PATTERNS: the no-op guard has
  to read the new `AppState.committed` (`doc` hands the field back its
  own preview, and it would never commit), and the resync has to skip
  the `setValue` mid-edit or it rewrites the number under the cursor.
- 2026-07-30 — **Ticks is the default lane**, and the Tempo field now
  aims at the selected line: click a line, type a tempo, and it sets the
  tempo from there to the end and releases the locks after it
  (`SetTempoFrom`). That is the tempo line's whole job, so Marcus may
  retire Tempo mode — kept for now. Cosmetics: the padlock is centred on
  a locked BARLINE with the line breaking around it, and locked
  subdivisions get the orange and the weight but no badge.
- 2026-07-30 — **Grid alignment round 2**: double-click a line to LOCK
  it (thick, orange, padlock); locks are the only drag anchors and they
  persist (schema v10, `locked_beats`, beats only — the second is
  derived). A drag now evens the span from the previous lock out to one
  tempo and locks the line it placed, so aligning left to right holds;
  Pin/Ripple became Flatten / Keep shape. Also fixed the view jumping
  out mid-drag — three causes, the real one being that with no audio the
  axis re-fits to the score's own changing length on every preview
  frame. Opened BACKLOG 25-26.
- 2026-07-30 — **Grid alignment** (`beta/grid-align`, UNMERGED): the lane
  gets a Ticks mode where the grid lines are drag handles, at Bars / 1/4 /
  1/8 / 1/8T / 1/16, with Pin or Ripple (Alt flips it). Solved back into
  tempo events — no new document field, no schema bump. Anchors are the
  nearest barline or tempo point, NOT the neighbouring ticks (those choke
  a 1/16 drag). New pure `core/timing/grid.py` + `retime.py`, one command
  `AlignBeat`, `swing_unwarp`, and the lane split into host + modes first.
  Opened BACKLOG 21–24.
- 2026-07-30 — Docs slimmed for lightweight working. The milestone
  ceremony and the two-track process are retired: one track now, no plan
  gate, ask first only for a schema bump, a golden re-capture, or a rule
  change. CLAUDE.md cut 355 → 244 lines (rules keep their short form;
  the long form moved to the new `docs/RULES.md`). ROADMAP, PHASES and
  the briefs moved to `docs/history/` and are out of the read path. The
  session protocol is now WORKLOG only, everything else on demand.
- 2026-07-30 — `beta/f-trackpad-gestures`: stage navigation is now the
  ordinary desktop set — pinch zooms, two-finger scroll moves the view,
  Cmd/Ctrl+wheel zooms, no drag-panning (so, a plain arrow cursor).
  Repeals the M2 "pan is unchanged" ruling in ARCHITECTURE §7. Qt's
  scrollbars are off because they reserve space (measured); a fading
  hint is painted instead. Opened BACKLOG 19. Merged into `main`.
- 2026-07-30 — **Part labels**: the adapter now joins a part label to its
  staff (document order over labelled staves, self-checked against the
  label text), so double-clicking a staff label renames the part —
  BACKLOG 14 closed. A condensed label edits its condense group instead.
  Found and measured a case the spike had missed: a multi-staff part
  hangs its label on the `<staffGrp>` and Verovio draws those FIRST
  (`spikes/label_group.py`). Goldens moved in three fields on label rows
  only. Opened BACKLOG 20. Merged `7ffc3bb`, tagged `v0.2-beta.6`.
- 2026-07-29 — Staff-label direct edit requested → flag-and-stop (it
  moved goldens). Spiked it instead: the MEI-id hypothesis is dead
  (0/129), order-over-labelled-staves is exact (129/129). BACKLOG 14
  updated with the measurement.
- 2026-07-29 — `beta/f-delete-elements`: delete = hide, for engraving
  cleanup only. Del/Backspace on the stage + Edit menu, texts/slurs/
  hairpins/dynamics only, restorable from the layout zone's new
  "Deleted" readout. Rides `LayoutOverride.hidden`; no schema bump, no
  re-engrave. Break commands split out of `layout.py` first. Also fixed
  a tint gap it surfaced (black-filled texts never took the selection
  colour). Merged `38ed04a`, no tag.
- 2026-07-29 — Docs: two-track process encoded, PATTERNS.md and this
  file created, CLAUDE.md slimmed (rules untouched). *(The two-track
  process was retired on 2026-07-30.)*
- 2026-07-29 — `fix/bracket-hidden-staves`: a bracket over hidden staves
  no longer kills the re-engrave; re-engrave failures are now visible in
  the UI instead of silent no-ops. Opened BACKLOG 18 (condense vs staff
  groups cross-validation). UNMERGED.
- 2026-07-28 — **Page breaks CLOSED**: page-break authoring (`plan`
  composition with never-clip, combined `_apply_breaks` pass, schema v9)
  + the left layout zone. Merged `bf3a824`, tagged `v0.2-beta.5`.
  BACKLOG 16, 17 closed.
- 2026-07-28 — **System breaks CLOSED**: system-break authoring, Move to
  Previous System (fat `SetSystemBreak`), schema v8. Merged `d912040`,
  tagged `v0.2-beta.4`.
- 2026-07-27 — **Direct edit CLOSED** (`v0.2-beta.3`): in-place text
  edit, drag-to-nudge, per-element style. Part-label rename unbuilt
  (BACKLOG 14). Selection re-closed after the tint rework.
- 2026-07-25 — **Effects** and **Selection CLOSED**, merged together
  (`v0.2-beta.2`).
- 2026-07-24 — **Shell CLOSED** (`v0.2-beta.1`). Alpha frozen at
  `v0.1-alpha`.
- 2026-08-29 — C3: the Inspector follows the selection. Picking something on the stage brings the Selection tab to the front and remembers the tab you were on; clearing puts it back, unless you chose a tab yourself while the selection was up, in which case yours stands and no flip back happens. The rule is a pure state machine in `ui/tab_focus.py` (9 headless tests) and the dock only reports the two events to it — a tab switch it makes itself is flagged so it cannot read back as the user's choice. The empty state now says "Nothing selected — click a note on the stage." Full suite 2242 green. Awaiting Marcus's in-app check with A1–A3, B1–B3, C1, C2.
- 2026-08-29 — C4: the bottom bar splits by what a control changes. The lane's three view options (which lane, which grid step, Flatten) moved up to a gear at the right edge of the transport strip — that row is the lanes' header — as `ui/lane_menu.py`, a popup menu that sets `AppState.grid` and so is still nothing the document hears about. The bar under the lanes now holds document timing alone, under a "Timing" heading: Tempo, Offset, Swing, still three live fields, still one undo entry per typing session. Flatten dropped its inverted "Keep shape" wording and is a plain checkable item. Lucide `settings` vendored. Group labels in the menu are disabled items, not `QMenu.addSection` — the app stylesheet paints a section as a bare line and ate the words. 9 new headless tests; full suite 2249 green. Awaiting Marcus's in-app check with A1–A3, B1–B3, C1–C3.
- 2026-08-29 — **`ui-redesign` merged to `main`** on Marcus's call: phases A1–A3, B1–B3 and C1–C4 of `docs/UI_REDESIGN.md`, 14 commits, a `--no-ff` merge onto a `main` that had not moved, so the merged tree is byte-identical to the branch tip that tested green. Full suite 2249 green on `main` after the merge. Phase D (transport cluster, stage overlay controls, hint bar) is next; `main` is unpushed and untagged.
- 2026-08-29 — D1: the transport becomes a cluster. The strip now reads go to start · play · timecode · Systems · the seek bar · the lane gear, instead of one stock slider spanning the window. Go to start is a seek to 0 and nothing else, so playing stays playing; it is the strip's own action, with no menu item and no key, so every existing binding is untouched. The timecode needed two fixes to stop wiggling: `QFontDatabase.systemFont(FixedFont)` names a family called "monospace" that no machine has, so Qt fell back to the proportional UI font — a Monospace style hint lands it on the real face (Menlo here) — and the label keeps a minimum width so the first two-digit minute cannot shove the cluster sideways. The slider is dressed by name (`QSlider#SeekBar`) in the stylesheet: a 4-px groove, the playhead colour behind the handle, a small pill for the handle. Lucide `skip-back` vendored. 4 new headless tests; full suite 2252 green. Awaiting Marcus's in-app check with A1–A3, B1–B3, C1–C4.
- 2026-08-29 — D1 revised: the seek bar comes off the strip. The lanes were already the seek surface (click seeks, drag scrubs), so the slider was a second playhead moving at a different speed — two clocks disagreeing. The strip is now the cluster, Systems, empty space, and the gear; `QSlider#SeekBar` left the stylesheet with it. The keyboard seeking a QSlider hands you for free is rebuilt as `ui/seek_keys.py`: Left/Right = 1 s, Shift+Left/Right = 5 s on `PlaybackController.seek_by` (clamped to the timeline, play state untouched), and Home went onto the strip's existing Go to Start action rather than a second action on the same key. All five are window-level and all five are in the Playback menu, which is the only place the shortcut sheet looks. The collision the task did not mention: the arrows have nudged the selection since M3.2, and a window shortcut normally beats the focused widget. Both exceptions ride Qt's ShortcutOverride rather than a focus test — a text field or spin box claims Left/Right/Home for its caret by itself (verified, not assumed), and `StageView.event` claims the arrows while something nudgeable is selected. 7 new headless tests, 6 slider tests retired; full suite 2257 green. Awaiting Marcus's in-app check with A1–A3, B1–B3, C1–C4.
- 2026-08-29 — D3: the status bar becomes a hint bar. With something selected it says what it is and what can be done to it ("Dynamic · Sop. Alto Ten. 1 · m. 1 — drag to move it, drag its onset line to re-time it, Delete hides it"); with nothing selected it names the loaded recording. The wording is one pure module, `core/editing/hints.py`, sitting with the other status-tip modules: a plain name for every ElementKind, one phrase per gesture, three phrases at most on the line. `ui/hint_bar.py` only gathers, and gathers each answer from the controller that owns that gesture — the delete and flip policies' `current()`, the break policy's resolve, the onset cursor's "is my line drawn", the nudge kind test, the text editor's route — so the bar cannot promise a key the app would ignore. That is why a note reads "F flips the stem" and nothing about an onset line: a notehead is a reveal anchor and has none. Two Qt facts made it work: a temporary message hides the bar's normal widgets and puts them back when it EXPIRES, so every status message now goes through `HintBar.message` with a timeout (an untimed one would bury the hint forever, and a test pins that nobody adds a bare `showMessage` back); and the label elides its own text, so the window's minimum width does not depend on which note you clicked. 24 new tests (15 headless wording, 9 wiring); full suite 2281 green. Awaiting Marcus's in-app check with A1–A3, B1–B3, C1–C4, D1.
- 2026-08-29 — **The UI facelift merged, tagged and pushed** on Marcus's call: `ui-d1-transport` merged `--no-ff` onto a `main` that had not moved, so the merged tree is byte-identical to the branch tip that tested green (full suite 2281 re-run on `main` before the tag). That is phases A, B, C and D of `docs/UI_REDESIGN.md` less D2. Tagged `v0.2-beta.7`; `main` and the tag are pushed, so the 16-commit backlog on `origin` is cleared too. Next: D2 (stage overlay zoom controls), then phase E.
- 2026-08-29 — Marcus ran the facelift in the app: **every point passes** — A1–A3, B1–B3, C1–C4, D1 and D3. So `v0.2-beta.7` is a tag with a human check behind it, not just a green suite. Still unproven under an eye, and untouched by this run: the score page's light/dark mode, the glow with its envelope editor, and the stem pass (see the paragraph above).
- 2026-08-29 — D2: floating zoom controls on the stage. The stage's bottom-right corner now carries zoom out · the percentage · zoom in · Fit, see-through and only there while the pointer is on the stage. **100 % means fitted**, because there is no other honest anchor — a page is 2095 x 2967 in tenths of a millimetre, so "actual size" would be a number about nothing, while Fit is a size one click gets back. The fit scale is worked out on every reading (`ui/stage_zoom.py`, pure) and never remembered, or a window resize under a zoomed-in view would leave the readout lying; a test pins the pure formula against a real `fitInView`, which is what keeps Qt's undocumented 2 px margin honest. The controls (`ui/zoom_overlay.py`) are a child of the view's viewport, take no keyboard focus (Esc, the arrows and Space stay where they were), and are hidden rather than transparent when the pointer leaves, so nothing of theirs is in the way of a click on the score. A button zoom anchors on the middle of the stage, not the pointer — the pointer is on a button in the corner at that moment. Fit is the View menu's own QAction. `transport.py`'s private monospace-font helper moved to `ui/theme/fonts.py`, since the readout wants the same face for the same reason. Lucide `zoom-in`/`zoom-out` vendored, three OVERLAY colour tokens added. 21 new tests; full suite 2302 green. Awaiting Marcus's in-app check.
