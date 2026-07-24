# Spike & build notes

## Phase 12 — Orchestral robustness planning (2026-07-21)

Verified the PHASE12_BRIEF diagnosis against the real files during
planning; **the brief was corrected on two points.** Verovio 6.2.x.

- **Verovio draws NOTHING for `<measure-repeat>`** (census, read-only).
  Its MusicXML importer has no measure-repeat support: the repeat bars
  import as invisible `<space>` (Bongos staff 25, m2: two `<space
  dur=2>`), and there are ZERO `mRpt`/`beatRpt` glyphs in the MEI or the
  rendered SVG (`mRest`/`space`/`mSpace` only). The brief's "Verovio
  draws the mRpt symbol but produces no animated elements" is WRONG —
  it draws nothing. → 12.2 must FULLY SYNTHESIZE the % symbol (SMuFL
  `repeat1Bar` U+E500) in the slash-region shape, not map a drawn glyph.
- **3 regions / ~32 bars, not "6 regions."** The 6 `<measure-repeat>`
  tags are 3 `[start, stop)` spans: Bongos mm.2–12 & mm.14–24, Drum Set
  mm.98–107 — the same half-open convention `_slash_regions` uses.
  (`type="start">1` = single-bar repeat, spanning to the matching stop.)
- **Appoggiatura join is surgical.** `join.py::_match_voice` already
  sorts+zips both sides by document order (`ScoreNote.order` /
  `AdapterNoteRecord.order_in_voice`) within a pitch bucket; the ONLY
  onset dependence is `_note_key` embedding `round(onset*4096)` for
  non-graces. Verovio delays the appoggiatura's principal by the grace
  duration (+0.0957 q, complex1) while music21 keeps the notated beat →
  the quantized onsets differ → the principal misses. Dropping the onset
  term (12.1) is the whole fix; the grace tier already works this way.
  Chord-graces fall out for free (distinct pitch + order per member).
  Ruling: trigger stays the Verovio qstamp (performance time); the join
  fix only closes the match, no retiming.

- **Condensing is viable as designed** (`spikes/condense_prep.py`,
  kept). Naive prep-seam merge of Flute 1 (P1) + Flute 2 (P2) into one
  staff as two voices — append P2's voice flow behind a `<backup>` of
  the measure's voice cursor, relabel voice → +1, force `<staff>1`,
  combine the label to "Flute 1.2". Verified: merged part = 159
  measures, 642 real notes (= 321+321), m64 balances (v1=80, v2=80);
  renders cleanly (Verovio auto-assigns v1 stems up / v2 down; separate
  beams/rests; ties/trills/graces survive) with NO collisions on both
  unison (mm.84–92, collapses to one doubled line) and divergent
  (mm.60–63 staccato) passages. Only cost: doubled noteheads in unison
  (a2-collapse deferred to BACKLOG). Merging the two flutes took that
  staff 5 pages → 3. Build note: the spike also folds P2's `<direction>`
  (dynamics) in — harmless on unison, doubles on divergent bars; 12.3
  decides (primary-only vs accept). SVG→PNG for review via `qlmanage`
  (only rasterizer on the box; no cairosvg/rsvg/resvg).

## Phase 11 — Dorico robustness (`spikes/complex1_triage.py`, 2026-07-19)

Triage spike verified the PHASE11_BRIEF diagnosis against the real
`complex1`/`complex2` files and corrected four brief details; the plan
built on the corrected mechanisms. Findings, verovio 6.2.x:

- **bTrem is NOT a clean container.** The tremolo stroke glyph (SMuFL
  E222) is a DIRECT `<use>` child of the id-bearing `<g class="bTrem">`
  (which also wraps the id-bearing note). Treating bTrem as a
  transparent container loads but the stroke folds into the enclosing
  STAFF_LINES scaffold (complex1 P9 m7 gains a 6th primitive — the
  BACKLOG-6 shape). So bTrem must EMIT (ElementKind.TREMOLO); ruling (a)
  is a real choice, not free. The nested note keeps its own timemap
  onset; the tremolo inherits the note's onset (chord-member style).
- **fTrem occurs in NEITHER file** — all 85 complex2 tremolos render as
  bTrem. fTrem coverage is defensive (synthetic unit test only).
- **beamSpan** is id-bearing with direct `<polygon>` children (the beam
  quads); MEI `beamSpan` carries @startid/@endid but is NOT in the
  layer-beam table, so onset/extent come from those note ids. complex2
  has one, on raw-render page 5.
- **Verovio DOES rotate.** complex2 pages 8 & 16 (raw encoded-breaks
  render) carry `rotate(-90 cx cy)` on measure `<g>`s (vertical text) —
  the brief's "page 5" was a different pagination. All are exactly −90°,
  so corner-mapped `apply_rect` is exact. The "Verovio never rotates"
  svg_geom assumption is dropped.
- **The 22 unmatched joins are the grace-carrying PRINCIPALS, not the
  graces.** All 26 graces match via join.py's onset-excluded grace tier;
  the principals miss because Verovio's timemap delays each by the grace
  duration (+0.0957 q exactly, both sides grace=False) while music21
  keeps the notated beat. Same appoggiatura semantics as complex2's
  1882/9546 collapse — one order-based join rewrite (Phase 12.1) fixes
  both; Phase 11 only PINS the gap.
- Census under the real (emitting) fix: complex1 = **3491** elements
  (not the brief's shimmed 3490 — the bTrem element is new). complex2 =
  **42,615** (42,530 + 85 real tremolos), 20 pages, 20 system-overflow.

Build note: the offscreen `MainWindow` hangs in headless runs (no event
loop), so the scripted exit drives `ScoreScenes` + `FrameRenderer`
directly (the render_page_png idiom) — open/animate/export, 13/13.

## Phase 10R — review-fix spike (`spikes/phase10r_spike.py`, 2026-07-13)

Marcus's Phase 10 exit review required four fixes (hidden empty staves,
animate-everything, the m44 tie artifacts, page-frame systems mode +
never-clip). Library facts the fixes stand on, verovio 6.2.1:

- **Two-pass load is id- and timemap-transparent**: loadData(MusicXML)
  → getMEI() → set `optimize="true"` on the first `<scoreDef>` → fresh
  toolkit → loadData(MEI) preserves all 4959 xml:ids AND the exact
  timemap (215 entries, qstamps/on/restsOn/measureOn identical);
  `transposeToSoundingPitch` on pass 2 does NOT double-transpose
  (pnames identical — the MEI is already sounding pitch and Verovio
  re-transposing is a no-op). Cost: 0.12s → 0.24s on video_test.
- **`optimize` is the hide-empty-staves switch Verovio actually honors**
  (with `condense:"encoded"`); `staff-details print-object="no"` and
  `staffDef@visible="false"` are both IGNORED for rendering; plain
  `condense:"auto"` condenses only scores with 2+ top-level staffGrps.
  video_test hide-ON staves/system: 8,2,2,4,2,2,5,4,5,4,4,4,4,4,4
  (first system full — engraving convention). ALL Phase 10R page
  overflow disappears under hiding (max system bottom 21416/29670).
- **Condensed layouts draw systemDividers (8 on video hide-ON) unless
  `systemDivider:"none"`** — adopted as a fixed option (Dorico's
  default draws none); the Phase 10 SYSTEM_DIVIDER decomposer support
  stays as defense. testscore + 2 injected groups + hide-ON: 7/3/6/3/5
  staff rows, 0 dividers — optimize and injected groups compose.
- **The native grand-staff brace follows staff visibility**: 3 grpSyms
  on video hide-ON (only the piano-visible systems), including systems
  where just ONE piano staff survives — the brace draws over one staff;
  the geometric identity's `first is last and staff_count > 1` branch
  covers it (span "P5").
- **Slash regions vs hiding**: Verovio judges slash measures (MEI
  `<space>`) empty. testscore hide-ON HIDES the drum staff across slash
  measures mm5–8/13–16 → the adapter's fallback (redo without optimize
  + LoadWarning "hide-unavailable") exists for exactly this;
  video_test loses no slash staff (other content keeps staves 7/8
  visible in its slash systems).
- **`<print new-page="yes">` injection in PART 1 ONLY controls
  pagination** (stripped encoded new-page + 7 injected breaks → exactly
  8 pages). Verovio's own ids re-roll on the input change (4589/4959
  common) — as always, OUR musical ids are the stable ones.
- **Attach-onset census (video)**: fermata ×6 and trill ×1 carry
  `@startid`; dir ×3, tempo ×1, harm ×9, dynam ×24 carry `@tstamp`;
  nothing carries neither. The 15 other onset-less OTHER elements are
  the per-system systemic-barline elements (scaffold, correctly
  static); the 7 onset-less TEXTs are the page-1 part labels (ruled
  static furniture).

Phase 10R build finds (2026-07-13):

- **A fermata's `@startid` may reference a CHORD id**, which is not in
  the timemap — attach-onset resolution goes through
  `chord_members[first]` (3 of video's 6 fermatas).
- **Repagination drift**: the re-engraved layout placed one system
  2 page units lower than the measured first pass predicted (greedy
  plan said fit-by-11) — `plan_page_breaks` carries a 2% safety pad;
  never-clip beats an occasional extra page.
- **QGraphicsView clamps scrolling to the scene rect**: the page-sized
  system frame extends past the page for systems near its top/bottom,
  so `fitInView` silently re-centered on the page instead of the band —
  StageView widens the VIEW's sceneRect to frame∪page (the overhang
  renders as view background = letterbox, which is correct).
- **Verovio's tie matching differs under condensed layout**: the P4 m41
  open tie (dropped flat) DRAWS under optimize, producing a
  continuation segment with no resolvable source in system 13 — the
  tolerant pairing skips it with "unattributed-continuation"
  (hide-ON warning census: 5 dropped + 13 implausible + 1 mismatch +
  1 unattributed; flat: 6 dropped + 13 implausible + 1 repaginated).
- **Condensed layout REUSES SVG group ids across element types** (the
  page-jump bug, fixed 2026-07-13): an m1 stem's `<g>` and an m44
  note's `<g>` can carry the same xml:id (e.g. `c1ax32bj`), so a naive
  `onset_by_id[vid]` / spanner-table lookup on a note-owned fragment's
  OWN id returned the distant note's late onset (145.5 for an m1 stem).
  That poisoned the trigger schedule's page/system stamps (a bar-3
  trigger stamped page 4 / system 10), which follow-mode read as a jump
  to page 4 and back. 182 stray fragments on video hide-ON; 0 on flat
  (no condense → no reuse). Fix: onset lookups in `_identity_for` are
  GATED BY svg_class — only notes/rests consult `onset_by_id` by id,
  only spanner classes the spanner table, only "beam" the beam table;
  everything note-owned falls to `owner_onset`. A no-op on any load
  without id reuse (flat unchanged), robust to Verovio's id hygiene.
  The MEI xml:id SET is still round-trip-stable (spike A) — the reuse
  is in the rendered SVG, not the MEI, so the set check didn't catch
  it.

## Phase 9 — part-label overrides (`spikes/part_label.py`, 2026-07-12)

Task 9.3's opening spike. Verovio 6.2.1 against
`testdata/testscore.musicxml` (every part has BOTH plain and -display
label elements; P1/P2 abbreviations empty with print-object="no"),
production adapter options. Id-set comparisons run through the REAL
adapter (`load_detailed` on a mutated temp file), not a parallel path.

- **Verovio reads `<part-name-display>`/`<part-abbreviation-display>`
  and IGNORES the plain elements when a display twin exists**: renaming
  only `<part-name>` changed nothing; renaming only the display did.
  `_apply_text_overrides` therefore writes BOTH — display for Verovio,
  plain because `_parts` (PartInfo extraction) reads it.
- **`print-object="no"` suppresses even a non-empty abbreviation**:
  giving P1 an abbreviation renders labelAbbr on systems 2+ ONLY after
  clearing the attribute (from the plain AND display elements).
  Overrides with non-blank text clear it; None leaves it alone.
- **An empty-string name suppresses the label entirely** (P4 blanked →
  6 labels on page 1, no empty element) — "" is a usable "no label"
  intent, not an error.
- **Id stability (production adapter): a rename keeps the id set
  IDENTICAL** (labels are page-scoped ordinal `score:p{n}:text:{seq}`;
  renames change no element counts). Adding a FIRST P1 abbreviation
  **appends** ids (`score:p2:text:10`/`:11`, `score:p3:text:10`/`:11`)
  with zero shift of existing ids on this fixture — the new labelAbbr
  land after the existing texts in traversal order. The general caveat
  stands (an insertion earlier in traversal order would renumber later
  seqs), but label TEXTs are static scaffold, never animation targets;
  override staleness is accepted (ARCHITECTURE §4).
- **The score shifts to fit**: page-1 staff min-x 3045 → 5920 page
  units when P4's name grows to 30 chars — the label column re-derives
  from the longest name exactly as BACKLOG 5 predicted (rule 7's
  "re-engrave with changed inputs", observable).

## Phase 8 — part-group injection (`spikes/part_group.py`, 2026-07-12)

The proper re-do of the v2 scoping probe (task 8.1). Measured on verovio
6.2.1 against `testdata/testscore.musicxml`, production adapter options
(header none, xmlIdSeed 42, concert pitch, octave-only transposes
neutralized). Variants: baseline; P1–P2 bracket+joined (the sax group);
P1–P3 bracket+joined (the scoping-probe group); P1–P2 brace / line /
square. Artifacts: `spikes/out/partgroup-*-page-*.svg` (+ page-1 PNGs
for baseline and P1–P2-bracket, rasterized via headless Chrome — no
rsvg/cairosvg on this machine; QtSvg can't render Verovio SVG).

- **Injection works for all four symbols.** `<part-group type="start">`
  with `<group-symbol>`/`<group-barline>` before the first grouped
  `<score-part>` + `type="stop"` after the last → Verovio renders the
  group symbol AND joins barlines through the group (visible in
  `partgroup-P1-P2-bracket-page-1.png`: bracket on the two sax staves,
  connectors through the inter-staff gap). In MEI the injected group is
  a nested `staffGrp` with `bar.thru='true'`.
- **`grpSym` is the ONLY new SVG class token, for all four symbols**
  (census over all pages vs baseline). One per system per group (5 on
  the fixture: systems 1/2,3/4,5), always id-bearing, always a direct
  child of the system `<g>`. Ink: 2 `<use>` (end-cap glyphs) + 1
  `<rect>` (body) for bracket — `use`/`rect` are both handled drawable
  tags. Census noise worth recording: the id-less broken-tie
  continuation segments carry class strings like `tie id-XXX spanning`,
  and those embedded pseudo-ids CHANGED between baseline and grouped
  renders — **fixed `xmlIdSeed` gives same-input determinism only; any
  input change (the injection) re-rolls every Verovio id** (m1 barLine:
  `p1l81zsh` → `r10709ff`). Our ElementIds are minted from musical
  identity precisely so this doesn't matter; the 8.3 pin test asserts
  it.
- **grpSym does NOT cross-reference the MEI `staffGrp`** (neither
  staffGrp id appears anywhere in the SVG). Identity must come from our
  own injection knowledge: grpSyms within a system, ordered by y, map
  1:1 to the injected groups sorted by first-part index. Geometry
  confirms the mapping is trustworthy: page-1 bracket y-extent 827–3741
  vs grouped staves at 884–2234 / 2964–3924 — brackets its staves
  exactly, clear of staff 3 (4738+).
- **Connector segments land INSIDE the measure's existing id-bearing
  `<g class="barLine">` group — outcome A.** m1 baseline: 14 paths
  (7 staves × 2); P1–P3 grouped: 20 paths — new spans 1604–2964 (P1–P2
  gap) and 3684–4277 + 4729–4978 (P2–P3 gap **split around an
  obstacle**, reproducing the scoping observation). Zero id-less
  barLine groups anywhere. So the decomposer needs NO connector
  handling: the paths fold into the existing BARLINE elements, whose
  bboxes simply grow. The B1 silent-absorption / B2 orphan-raise
  scenarios do not occur.
- **No left-margin shift on this fixture**: staff-lines min-x is 3045
  for every variant (delta 0), and overall ink min-x is unchanged. The
  bracket (x 2865–2955 on system 1; 2121–2211 on later, abbreviated-
  label systems) fits inside the existing part-label margin. The
  accepted-staleness note for dx/dy overrides stands but is moot here —
  grouped and ungrouped geometry are identical except for the added
  ink.

## v2 scoping probes (2026-07-12 — session-inline; re-do the part-group probe as a proper spike at Phase 8 start)

Measured during the v2 scoping session (assessment only, nothing
built). The part-group probe ran from a session scratchpad, not
`spikes/` — ruling: re-do it properly here when Phase 8 opens (task
8.1). Facts, verovio 6.2.1 against `testdata/testscore.musicxml`:

- **Engrave + decompose is 0.23 s** (1686 elements, 3 pages) through
  `VerovioEngravingProvider.load`. Re-engraving on edit is
  computationally trivial; the real cost of any re-engrave feature is
  commands/schema/UI, not the engrave. (Consistent with the Phase 2
  finding of 0.22 s engrave+decompose; this run includes ledger-dash
  and spanner-segment attribution added since.)
- **Baseline barlines are per-staff segments, NOT joined**: each
  BARLINE element's full-system-height bbox is a union over gapped
  per-staff paths (page-1 y-spans 1942–2662, 4776–5496, … with nothing
  drawn between staves). Any earlier impression of joined barlines was
  a bbox artifact.
- **`<part-group>` injection works**: inserting a part-group
  (`group-symbol` bracket, `group-barline` yes) around P1–P3 in the
  part-list makes Verovio render a `grpSym` bracket AND join barlines
  through the group. Connector segments appear between the grouped
  staves and are **split around obstacles** (m1's P2–P3 connector
  breaks into two segments). Reimplementing that collision avoidance
  render-side is exactly the engraving logic we don't hand-roll —
  hence the Phase 8 ruling: brackets go through the engraving inputs.
- **`grpSym` is an unknown SVG class to the adapter, and unknown
  classes raise ValueError** in the decomposition walk — mapping it is
  a mandatory first step of Phase 8 or grouped scores refuse to load.
- **Every fixture element carries a system index** (zero `system=None`
  across all 1686 elements; systems per page 1 / 2,3 / 4,5) —
  system-at-a-time framing (Phase 7) is pure Layout consumption, no
  re-engrave. ElementIds are minted from musical identity
  (part/measure/staff/voice/kind/index), which a part-group does not
  touch — id stability across grouped re-engraves is expected by
  construction and gets pinned by test in Phase 8.

## Phase 5 — broken-spanner anatomy (`spikes/spanner_split.py`, 2026-07-11)

Question: how does Verovio represent spanners broken across systems, and
what identity do hairpins carry? Measured on verovio 6.2.1 against
`testdata/broken_hairpin_and_slur_test.musicxml` (user-provided Dorico
export: 2 parts — Tpts in B♭ (chromatic transpose) + Tbns — 10 measures,
3 systems on one page; hairpin broken across the m4→m5 system break, slur
broken across m8→m9, ties broken across m8→m9; companion `.wav`).

- **Broken spanner = one id-bearing `<g>` + one id-less `<g>` per
  continuation system.** Segment 1 is a normal `<g class="slur|tie|hairpin"
  id=...>` inside the START measure's subtree. Each continuation segment is
  an **id-less** `<g class="...">` emitted as a direct child of the
  continuation `<g class="system">` — outside any measure. One drawable per
  group; no duplicate ids anywhere; never one `<g>` with multiple segment
  paths.
- **The current adapter silently absorbs continuation segments into the
  system element** (kind OTHER, "systemic barline"): the id-less group's
  class is in `_KIND_BY_CLASS`, so no unknown-class error fires, and its
  drawable falls through to the enclosing system accumulator. The fixture
  loads without error (639 elements) but the continuation ink is static
  system ink — invisible to animation, tinting, and clip-reveal. Phase 5.1a
  must intercept id-less spanner-class groups in `_walk`.
- **Hairpin ink is `<polyline>`, not `<path>`** (closed first segment: one
  3-point polyline; open continuation: two polylines). Already handled by
  `_add_drawable`'s polyline branch.
- **Hairpins carry `@staff` + `@tstamp`/`@tstamp2` (`form`, `vgrp`) and NO
  `startid`/`endid`** — e.g. `staff='1' tstamp='1' tstamp2='1m+2.5'`.
  The adapter's spanner identity path (startid → part/staff/onset/extent)
  therefore yields part=None/onset=None/extent=None for hairpins today;
  `_parse_mei` must record spanner `@staff` and resolve tstamp extents.
  `tstamp2` grammar: `<n>m+<beat>` (n measures ahead, beat in meter units,
  1-based). Beat→quarters needs the active meter: MEI `meterSig
  count/unit` elements appear in document order (initial scoreDef +
  changes), so the meter per measure is trackable in the existing
  `_parse_mei` walk.
- **Open (unmatched) ties render as 0-path `<g>`s** here too (3 in this
  fixture — same importer quirk as the main fixture's 5).
- **Dynamics are `@tstamp + @staff` addressed too** (verified on both
  fixtures during the reveal re-plan, 2026-07-12): `<dynam staff='1'
  tstamp='2' place='below' vgrp=...>` — no `startid` from Dorico
  exports, though the adapter honors one if present. Same tstamp
  arithmetic as hairpins (meter-unit beats, 1-based); the fixture's m1
  dynamics at tstamp 2 resolve to 1.0 quarters — the tutti chord, not
  the measure start.

## Phase 4 — QAudioDecoder spike (`spikes/decode_audio.py`, 2026-07-11)

Question: is QAudioDecoder viable for waveform peak extraction (formats,
speed, coexistence with the playback QMediaPlayer)? Measured on the real
recording (`testdata/testscore.{wav,mp3}`, 34.56 s), PySide6 6.11.1 /
Qt ffmpeg backend / macOS:

- **Decode is effectively instant**: full-file decode in 0.03 s (wav) /
  0.04 s (mp3) wall — even a 5-minute file is sub-second. The
  event-driven design (per-buffer numpy binning on `bufferReady`) is
  comfortably event-loop friendly; no worker thread needed.
- **Formats delivered**: wav → `Int16`/2ch/48kHz in 4096-frame buffers
  (406 buffers); mp3 → `Float`/2ch/48kHz in 1152-frame buffers (1442).
  The extractor must handle at least Int16/Int32/UInt8/Float
  (QAudioFormat's full set) — scale each to [-1, 1].
- **Exact duration agreement**: both containers decode to the identical
  1 659 059 frames = 34.564 s, matching `QMediaPlayer.duration()`
  (34 563 ms). The mp3 encoder delay/padding is compensated by the
  backend (ffmpeg logs "skipped/discarded samples" and trims) — wav and
  mp3 waveforms align sample-exactly, so peak x-positions can be trusted
  against the playhead on either format.
- **`QAudioDecoder.duration()` is useless** (returns −1 throughout) —
  derive duration from accumulated frames / sample rate instead.
- **Concurrent decode works**: decoding a file the transport's
  QMediaPlayer currently has loaded behaves identically (LoadedMedia,
  same buffers, same speed).

Phase 4 build findings (library facts, 2026-07-11):

- **`QAudioBuffer.constData()` returns a memoryview** that dies with its
  buffer — `np.frombuffer` on it is fine within the handler, but any
  array kept past the handler must be an owned copy (`astype` copies;
  ui/peaks_worker.py relies on this).
- **`QAudioDecoder.stop()` re-emits `finished` synchronously**, so a
  finished-handler that calls stop() re-enters itself. The extractor
  nulls its decoder reference before stopping (peaks_worker.stop()).
- **Modal QMessageBox hangs offscreen scripts** — headless smoke tests
  must avoid paths that raise dialogs (or stub them).

## Phase 3 — audio playhead spike (`spikes/audio_playhead.py`, 2026-07-11)

Known risk 3: is Qt's audio playhead query precise enough to be the master
clock for onset animation? Criteria stated before measuring: effective
clock error ≤ 20 ms ideal (~1 frame @ 60 fps), ≤ 33 ms acceptable (below
ITU-R BT.1359 a/v-asynchrony detectability both directions). Measured on
PySide6 6.11.1 / Qt ffmpeg multimedia backend / macOS (Darwin 24), against
a synthesized 60 s click track (wav + libmp3lame mp3 twin).

- **`QMediaPlayer.position()` is cached and coarse**: it updates in
  lockstep with `positionChanged` at a fixed cadence — every **100 ms for
  wav, 50 ms for mp3** (cadence is evidently container/decoder dependent).
  Raw per-frame reads (tier 1) give a staircase with residuals up to
  120 ms — unusable. Zero backward jumps in steady playback.
- **Seeks are essentially instant and exact**, playing and paused:
  settle < 1 ms, landing error ~0.5 ms (both formats, 20 random seeks).
  Seek precision is NOT the problem; update cadence is.
- **Pause freezes position exactly** (0.00 ms drift over 1 s).
  **Resume jumps forward** ~20–60 ms relative to expected continuation
  (one-time transient while the pipeline restarts) — the AudioClock
  wrapper resets its anchor window on resume so this shows as one small
  re-anchor, not a sustained error.
- **Audio clock vs wall clock run at the same rate** to ~4e-5 (linear-fit
  slope 0.99997–1.00001) → extrapolating between anchors by wall-clock
  elapsed is safe, and offset averaging cannot drift.
- **Tier 2 (extrapolate from the single latest anchor)**: mp3 passes
  (p95 12 ms), wav is acceptable-but-not-ideal (p95 24 ms, max 27 ms) —
  anchor-timing jitter at 100 ms cadence is too big for the 20 ms bar.
- **Tier 2b (added during the spike): sliding-mean offset** — clock =
  `wall_now + mean(anchor_pos − anchor_wall)` over the last ~12 anchors
  (~1.2 s), monotone-clamped, frozen while paused, window reset on
  seek/resume. Simulated offline on the same traces: **wav p95 7.1 ms /
  max 21.8 ms; mp3 p95 1.2 ms / max 8.3 ms — PASS ideal on both.**
- **VERDICT: tier 2b.** AudioClock (ui/audio.py) implements sliding-mean
  anchored extrapolation. No accumulation (rule 2): the estimate is a pure
  function of (recent authoritative positions, wall time); every
  `positionChanged` updates the window, so error is bounded and cannot
  grow over a piece. Tier 3 (QAudioSink/processedUSecs) not needed.
- **Not measurable without a loopback rig**: absolute output latency
  (does `position()` lead the speakers by the sink buffer?) and any mp3
  decoder-delay constant offset (the encoded twin declares
  `start: 0.025057` — Qt appears to handle it, but a constant shift
  would be invisible to this spike by construction). Both are constants;
  the tempo file's `offset` absorbs them. Prefer wav for the reference
  recording to remove the mp3 question entirely.
- **Confirmed on the real recording** (`testdata/testscore.{wav,mp3}`,
  34.6 s, measured 2026-07-11 after fixing the spike's hardcoded 60 s
  seek bounds to use the player-reported duration): same cadences
  (wav 100 ms / mp3 50 ms), tier 2b PASS both — wav p95 6.3 ms /
  max 29.1 ms, mp3 p95 0.3 ms / max 9.0 ms; 20/20 seeks settle < 1 ms.
  Resume jump on the real wav is larger (~+100 ms one-time transient
  while the pipeline restarts); the AudioClock's anchor-window reset on
  resume absorbs it as one forward re-anchor — watch for a visible
  skip-at-resume in the sync session; if it bothers, tier 3 or a resume
  ramp would be the follow-up, not a tempo edit.

## Phase 2 build findings (2026-07-10)

Library facts discovered while building the Qt render layer; verified
against verovio 6.2.1 / PySide6 6.11.1:

- **`header: "none"` is safe for the join**: all Verovio element ids are
  byte-identical to a `header: "encoded"` load (verified) — timemap/MEI/
  SVG cross-referencing is unaffected. But Verovio **reclaims the header
  space**: the fixture's page-1 top staff rises from y≈165 to y≈138 page
  units. There is no option to reserve a Dorico-style title frame.
- **Dorico's credit `default-x/default-y` are unreliable for layout**:
  on the fixture they match neither Dorico's own PDF title block (the
  title would sit 22% down the page) nor the page center (593.75 tenths
  on a 1397.65-tenth page; Dorico centers credits on its music frame).
  `default_stage_config` therefore ignores them and derives positions
  from justify + font size, fitted into the band above the top staff.
- **Qt accepts Verovio's embedded Bravura WOFF2**: the pip package ships
  no OTF/TTF, but `data/Bravura.css` embeds base64 WOFF2, and
  `QFontDatabase.addApplicationFontFromData` registers it (FreeType) —
  the metronome-note text run renders for real, no tofu
  (`render/fonts.py`). Verovio's own upstream tofu (BACKLOG 3) remains.
- **QPainterPath must be switched to `WindingFill`**: SVG's default fill
  rule is nonzero; Qt's is odd-even, which inverts glyph counters
  (half-note heads render solid). One line in `render/qpath.py`.
- **QPen defaults mismatch SVG stroke defaults** three ways: Qt uses
  square caps (SVG: butt — square would lengthen every staff line and
  stem by half a width), bevel joins (SVG: miter), miter limit 2 (SVG:
  4). `render/items.py::svg_pen` bakes the SVG values.
- Qt performance is a non-issue at this score's scale: engrave+decompose
  0.22 s, scene build 0.29 s, ~2450 items across 3 scenes (densest page
  695 elements / ~1060 primitives).

## Phase 1 T0 — MEI bridge (`spikes/mei_bridge.py`, 2026-07-10)

Load options: concert pitch, encoded breaks, `xmlIdSeed: 42`.

- **Id agreement confirmed**: 500 note ids each in timemap / SVG /
  `tk.getMEI()`; timemap ⊆ MEI, SVG == MEI. Same seed → identical ids on
  reload. The MEI is a valid join bridge.
- **staffDef n=1..7 map 1:1 to the seven MusicXML parts, in order**, with
  labels equal to the part names.
- **MEI layer @n preserves MusicXML voice numbers** (drums layers 5/6,
  Tbns 1/2) — same numbers music21 reports as Voice ids, so voice
  matching is direct (order fallback kept as safety net).
- **Note attribute census** (500 notes): `pname`/`oct` on 483;
  **17 drum notes are unpitched** — they carry `@loc` (staff position,
  0 = bottom line) instead. Join needs an unpitched tier: match by
  staff position / vertical order, not pitch. Accidentals are child
  `<accid>` elements (`accid` or `accid.ges`), not note attributes.
  `dur`/`dur.ppq` present only on non-chord-member notes (119).
- **Slash measures render as MEI `<space>`** elements (2 per 4/4, 1 per
  2/4) — nothing drawable, nothing in the timemap, as expected.

## Phase 1 T0 — music21 behavior (`spikes/m21_behavior.py`, 2026-07-10)

- **`<measure-style><slash/>` is dropped entirely** by music21 (no object
  anywhere with slash in its class). Slash regions must come from a raw
  XML scan (plan D1) — confirmed.
- **Slash measures parse as full-measure `Rest`s** (music21 converts the
  `<forward>` skips). These are *not* musical rests; ScoreModel must
  exclude them via the slash-region measure set, not by inspecting rests.
- **`toSoundingPitch()` matches Verovio's concert render**: P1 c# minor →
  e minor, F#5→A4 etc. After neutralizing the 2 octave-only
  `<transpose>` elements (P5 Guitar, P6 Bass), both stay at written
  octave through `toSoundingPitch()` — pitch alignment by construction
  holds.
- **music21 replaces `Part.id` with the part *name*** ("Sop. Alto Ten. 1",
  not "P1"). Canonical part key = document order; the prep scan carries
  (order, P-id, name).
- **Grace notes** (3): `offset` = the principal's offset (e.g. 1.0),
  `quarterLength` 0, `duration.isGrace` True — as assumed; onset-equality
  checks must exempt them.
- **Voices**: most parts have no `Voice` containers (single voice);
  Tbns has Voices '1'/'2', Drum Set '5'/'6'. Drum notes are `Unpitched`
  with displayStep/displayOctave.
- No `PartStaff` splitting (all 7 parts single-staff).

## Phase 1 build findings (T3–T5, 2026-07-10)

Discovered while implementing the adapter/join; these are library facts,
not design decisions:

- **Verovio styles its SVG via one small `<style>` block**, not element
  attributes: every shape gets `stroke: currentColor`; tempo/reh/ending/
  fing text is bold, dir/dynam/mNum italic. The adapter bakes these into
  primitives so the redraw needs no CSS. Rehearsal-mark boxes use
  `fill-opacity="0"` (mapped to `fill="none"`).
- **music21 realizes `<harmony>` as `ChordSymbol`**, a `Chord` subclass
  that appears in `.notes` — the m19 D7 symbols added 8 phantom
  "noteheads" until excluded from ScoreModel.
- **Verovio's gestural accidental (`accid.ges`) is unreliable** on
  exactly 8 fixture notes: the 5 open-tie targets get none (sounding
  D#4 reported as D4), and 3 Tbns m5 notes get one over-propagated
  across octaves. MusicXML `<alter>` (music21 side) is authoritative →
  the join keys on (step, octave) without alter.
- **Tied-to notes appear as fresh `on` events in the timemap** (all 500
  notes have onsets, including 58 tie-stop noteheads). Phase 3+ reveal
  logic must gate on `ScoreNote.tie`, not the timemap, to avoid
  re-triggering tied notes.
- **MEI `@loc` ↔ display pitch**: loc = diatonic(step, oct) − 30
  (0 = bottom line, treble numbering) — verified hi-hat B5→11, kick F4→1.
- The 5 open ties produce **no drawn tie curve** (59 TIE elements from
  64 source ties).
- Slash-measure durations come from timemap `measureOn` qstamp deltas;
  synthesized slashes use the per-measure drum staff-lines bbox for
  geometry (even slots; system-start measures share the slot logic —
  clef/key prefix slightly narrows visual centering, accepted for v1).
- **Corrected slash regions** (supersedes the Phase 0 "mm. 3ff"/"mm. 3–19"
  approximation): the drum part has THREE `[start, stop)` regions —
  **mm 3–9, 11–15, 16–17**. m10 and m18 contain real drum fills; m16
  carries both a `stop` and a `start` (region boundary, still slash).
  Meters inside the regions are 4/4 except m5 and m14 (2/4).
- **Text decomposition** (T-fix after Phase 1 review): Verovio puts a
  text's anchor point + `text-anchor` either on `<text>` itself (labels,
  tempo) or on a positioned `rend` tspan inside it (pgHead lines), and
  styles runs via nested tspans — labels are END-anchored, the title
  middle, the composer block end, "Project Lyricist" carries
  `fill="#C0C0C0"`. The tempo mark is four runs in one `<text>`; the
  metronome note is a separate 720px `font-family="Bravura"` run
  (rendered via the @font-face Verovio embeds in the SVG), while
  Verovio's own tofu glyph sits inside the 405px text run (upstream,
  BACKLOG item 3). TextPrimitive therefore stores anchor + styled runs,
  and the redraw replays them; pinned in
  tests/test_adapter_layout.py::test_text_decomposition_preserves_anchor_and_styling.

# Phase 0 spike notes

Environment: Python 3.12.13 (uv venv), verovio 6.2.1-8d42439, music21 10.5.0,
PySide6 6.11.1. Test material: `testdata/testscore.musicxml` (Dorico 6.0.0.6026
export, "Det var en gang", Grieg arr. Grand, 7 parts, 19 measures) +
`testdata/testscore.pdf` (3 pages).

## 0.2 Dorico → Verovio fidelity (`spikes/fidelity.py`)

### Options that matter

```python
{
    "breaks": "encoded",             # honor new-system / new-page from the file
    "font": "Bravura",               # Dorico's font; bundled with Verovio
    "pageWidth": 2096,               # 1/10 mm, computed from the score's
    "pageHeight": 2967,              #   <defaults> (scaling: 5.99722mm = 40 tenths)
    "scaleToPageSize": True,
    "header": "encoded", "footer": "encoded",
    "svgViewBox": True,
    "transposeToSoundingPitch": True # see "written vs concert" below
}
```

- Verovio does NOT read page size from the MusicXML `<defaults>`; we compute
  it (tenths → mm → 1/10 mm) and pass `pageWidth`/`pageHeight` explicitly.
- The Python binding's `getOptions()`/`setOptions()` take/return **dicts**,
  not JSON strings (older examples show strings).

### Written vs concert pitch — the big one

The MusicXML encodes **written (transposed) pitch**: P1 "Sop. Alto Ten. 1"
and P2 "Ten. 2 Bari." carry `<transpose>` chromatic −9 (P2 also
octave-change −1), i.e. E♭-instrument-style transposition, written key
4 sharps; P3 trumpets 3 sharps. **The companion PDF is a concert-pitch
score** (1 sharp on every staff). A default Verovio render therefore shows
different key signatures than the PDF, and P2's written pitches sit far
above its concert-layout bass clef (looks broken; it isn't — it renders
exactly what the XML says).

`transposeToSoundingPitch: True` makes Verovio render at concert pitch and
matches the PDF's presentation. Both artifact sets are kept:
`spikes/out/page-{1,2,3}.svg` (written) and `page-{1,2,3}-concert.svg`
(concert). Rasterized PNGs alongside, plus `pdf-page-{1,2,3}.png` extracted
from the PDF for side-by-side comparison.

**RESOLVED (user ruling, 2026-07-10)**: ScoreAnim always animates concert
pitch; `transposeToSoundingPitch: True` is a fixed part of EngravingParams,
not a user option in v1. Exception: parts whose `<transpose>` is octave-only
(`octave-change` with no chromatic shift — here Guitar P5 and Bass Guitar P6,
both `(0, 0, -1)`) keep conventional written octave; chromatic
transpositions render at concert pitch. Note: Verovio's
`transposeToSoundingPitch` honors octave-change too, which drops guitar/bass
an octave into heavy ledger lines (visible in `page-*-concert.svg`); Verovio
has no per-part transpose option, so the adapter must handle the exception
at the boundary (e.g. neutralize octave-only `<transpose>` elements before
load). All fidelity comparisons and test expectations are against
concert-pitch renders.

### Structural comparison (facts)

| metric | Dorico PDF | Verovio (both variants) |
|---|---|---|
| pages | 3 | 3 |
| systems per page | 1 / 2 / 2 | 1 / 2 / 2 |
| measures per system | 4 / 4,4 / 4,3 | 4 / 4,4 / 4,3 |
| system starts | mm. 1, 5, 9, 13, 17 | same |

Page count and casting-off match exactly with `breaks: "encoded"`.
Also matching: grace notes m.1, rehearsal marks A/B, courtesy 2/4 at page 1
end, mid-system meter changes (2/4↔4/4 in mm. 13–19), dynamics, articulation,
"bucket mute"/"(crash)"/"ad lib"/"sim." texts, D7 chord symbols in m. 19,
measure numbers at system starts (5, 9, 13, 17).

### Deviations observed (for the user to judge)

1. **Drum slash region renders empty.** Dorico exports mm. 3ff of the drum
   part (precise regions: mm 3–9, 11–15, 16–17 — see the Phase 1 findings
   above, which supersede this approximation) as
   `<measure-style><slash type="start" use-stems="no"/>` with **no
   `<note>` elements** in those measures. Verovio ignores this measure-style
   → empty drum staff from m. 3 on (PDF shows beat slashes). Note for later
   phases: those measures contain no note events, so there is nothing to
   animate there either — the gap in the XML affects both renderer and
   timemap.
2. **Title block.** Dorico's big title layout (28 pt title, subtitle,
   composer/arranger block) is rendered by Verovio as a small one-line
   running header. All credit texts are present (incl. gray "Project
   Lyricist"), but size/placement differ.
3. **Metronome mark glyph.** "Swing ♩ = 120" renders as "Swing □♩ = 120" —
   a tofu box before the note glyph (some glyph in the metronome text that
   Verovio can't map).
4. **m. 19 guitar D7 slash notehead** renders as a stack of horizontal
   strokes rather than the PDF's single slash notehead.
5. **Staff labels** are single-line ("Sop. Alto Ten. 1") vs Dorico's
   stacked three-line labels; page 2–3 running header ("2 / Det var en
   gang") not rendered.
6. **Import warning**: `MusicXML import: There are 5 ties left open` —
   investigated, see "Tie warning" section below.
7. Note spacing within systems differs slightly (Verovio's spacing engine);
   casting-off is identical.

### Sax section bracket (backlog item 1) — cause established

The Dorico export contains **no `<part-group>` elements at all** (checked:
no `part-group`, `group-symbol`, or `group-barline` anywhere in the file),
so the sax bracket is absent from the source data — there is no Verovio
option that could render it. Remedies when the backlog item is picked up:
re-export from Dorico with bracket/group export enabled (then Verovio's
default part-group handling should apply), or synthesize brackets in the
adapter. Filed in `docs/BACKLOG.md` (fix before first production use).

### Tie warning (`spikes/ties.py`) — investigated, time-boxed

`MusicXML import: There are 5 ties left open`. Facts:

- The MusicXML's `<tie>`/`<tied>` elements balance exactly (start/stop
  pairs match per part) — the file is well-formed; this is an importer
  matching quirk, not bad Dorico data.
- In Verovio's MEI, 64 ties exist; 5 have `@endid` missing:
  E#4 m5→6 (Tpts), D#4 m5→6 (Tbns), E#4 m8→9 (Tpts, across a system
  break), B4 m14→15 and m17→18 (staff 1).
- The destination notes DO exist: verified m5→m6 Tpts — the target chord
  contains the E#4 tie-stop, and its chord-mates C#5 and A4 matched fine.

Best hypothesis: a quirk in Verovio's chord-member tie resolution (possibly
confused by duplicate pname/oct candidates in the destination measure —
m6 contains two e4 notes). Visual result judged acceptable by the user.
**Phase 1 watch item**: an unmatched tie may make the tied-to note appear
as a fresh onset in the timemap; the ScoreModel⇄timemap join (task 1.4)
should assert how these 5 notes behave.

## 0.3 Timemap (`spikes/timemap.py`)

`tk.renderToTimemap({"includeMeasures": True, "includeRests": True})` returns
a **list of dicts** (no JSON parsing needed), one entry per distinct time
point — 83 entries / 500 note-on events for the test score. Entry format:

```python
{
  "tstamp": 500,          # milliseconds from score start (float-friendly int)
  "qstamp": 1,            # quarter notes from score start (float)
  "on":  [ids...],        # note ids starting here
  "off": [ids...],        # note ids ending here
  "restsOn"/"restsOff": [ids...],   # only with includeRests
  "measureOn": id,        # only with includeMeasures
  "tempo": 120,           # present when tempo (re)defined at this point
}
```

Verified for the test score: onsets **monotone non-decreasing**, tempo 120
picked up from the score's metronome mark (quarter = 500 ms), and measure 1
is musically exact — drum beat 1 at 0 ms, the two grace notes just before
beat 2 at 441/471 ms (grace notes get real timestamps), tutti chord on
beat 2 at 500 ms. `tk.getTimesForElement(id)` gives per-element
on/off/duration both in ms (`tstampOn`) and as quarter-note fractions
(`qfracOn`, list of `[num, den]` pairs).

### Element ID determinism — matters for Phase 1

Verovio **generates fresh random ids on every load** (Dorico's MusicXML has
no note ids to preserve): two runs gave `c10n47li` vs `s92wprl` for the same
first note. Two remedies, both verified deterministic across runs:

- `xmlIdSeed: <int>` — same seed → same ids for the same input.
- `xmlIdChecksum: True` — ids derived from content checksum.

Rule 4 keeps Verovio ids behind the adapter anyway, but the adapter itself
should set one of these so that timemap ↔ SVG ↔ music21 cross-referencing is
reproducible between loads (and in tests). Timemap and SVG ids DO agree
within a single load.

## 0.4 SVG anatomy (`spikes/svg_anatomy.py`)

### Document structure

```
<svg id="<pageid>">                    # outer, viewBox in page units (2096x2967)
  <desc>, <style>
  <defs>                               # SMuFL glyphs as <path>, keyed "E0A4-<pageid>"
  <svg class="definition-scale" viewBox="0 0 20960 29670">   # 10x page units
    <g class="page-margin" transform="translate(...)">
      <g class="system" id=...>
        <g class="measure" id=...>
          <g class="staff" id=...>
            <g class="layer" id=...>
              <g class="beam" id=...>          # only when beamed
                <g class="chord" id=...>       # only for chords
                  <g class="note" id=...>
                    <g class="notehead">       # NO id (see below)
                      <use xlink:href="#E0A4-<pageid>"
                           transform="translate(5840, 1973) scale(0.54, 0.54)"/>
```

- All coordinates live in "definition-scale" units = 10 x the page unit
  (page = 1/10 mm, so 1 unit = 1/100 mm). Glyphs are `<use>` references into
  `<defs>`; defs paths carry `scale(1,-1)` (SMuFL y-up), positions come from
  the `translate(x, y)` on the `<use>`.
- Class census page 1 (709 classed elements): note 119, notehead 119,
  accid 110, stem 59, chord 26, rest 20, artic 18, dynam 10, beam 9, tie 9,
  mRest 9, flag 5, measure 4, barLine 4, system 1, slur 1, tempo 1, reh 1
  (+ clef/keySig/meterSig/label/ledgerLines/...).

### ID coverage / addressability (the 0.4 verification)

- **Unique ids on**: note, chord, stem, beam, tie, slur, accid, artic, dynam,
  rest, measure, staff, layer, system, clef, keySig, meterSig, tempo, reh —
  effectively every musical element.
- **No ids on**: `notehead`, `ledgerLines`, `dots`. A notehead is the single
  `<g class="notehead">` child of its id-bearing `<g class="note">` (chord
  notes are separate `note` groups), so noteheads ARE individually
  addressable as note-id -> notehead child. Slurs have their own ids and are
  drawn as a self-contained cubic-bezier `<path>` with absolute coordinates
  (good for clip-rect reveal).
- Verdict for PHASES 0.4: noteheads and slurs individually addressable —
  **confirmed**, with the "notehead = child of note" indirection noted.

### Rasterization gotcha (Phase 2 relevant)

Qt's SVG module (QtSvg, SVG Tiny 1.2) **cannot render Verovio SVG**: Verovio
nests an inner `<svg>` element and QtSvg skips it → blank output. Chrome
renders it fine. Phase 1/2 plan (decompose SVG into per-element QGraphicsItems
via QPainterPath) is unaffected, but "just hand the whole SVG to QtSvg" is
not a viable shortcut.

## Phase 10 — triage spike (`spikes/video_test_triage.py`, 2026-07-13)

Task 10.0: the proper freeze of the session triage below, with THREE
mechanism corrections found while planning (verified against the real
files; the spike pins all of them and reproduces the four failure points
in order — section F). The fixes' shape follows these, not the earlier
hypotheses:

- **music21 PartStaff contract (10.1)**: a `<staves>2</staves>` part
  splits into adjacent `PartStaff` objects, document order, in the
  score-part's slot, ids `'<score-part-id>-Staff<k>'` — the ONLY parts
  whose original id survives (plain Parts get their id replaced by the
  part NAME). music21 also emits a `layout.StaffGroup(symbol='brace')`
  over the pair. So `sum(prep staff_count) == len(score.parts)` and a
  grouped positional zip reconciles 8-vs-7 by construction. The
  note-empty `P5-Staff2` still carries all 45 Measure streams.
- **The m12 "ledger dash matches no notehead" is a REST, not
  cross-staff (10.2)**: staff 2 (Ten/Bari — not even the piano) has two
  voices in m12; the voice-1 half rest is displaced off the staff and
  Verovio draws a ledger dash through it. The (page, measure, staff)
  scope key is already right; the candidate pool just lacks rests.
  Score-wide: 351 dashes note-owned, 4 attributable only to a rest.
- **Tie continuation ink is drawn ONLY in the tie's END system (10.3)**:
  the Phase 5 spike only ever saw 2-system spanners, where end system ==
  the only continuation system. On video_test the old
  `start < n <= end` predicate over-counts pass-through ties (per-system
  drawn/old/end-rule: sys4 6/9/6, sys7 4/9/4, sys11 10/17/10, sys12
  9/18/9, sys13 14/25/14, sys15 11/11/11); the end-system rule closes
  every count. Separately, **6 MEI ties produce NO ink** — all render as
  id-bearing 0-path `<g>`s (the testscore open-tie shape, NOT absent
  groups): 5 with no `@endid` ("5 ties left open") + 1 cross-staff tie
  whose end precedes its start (m41 staff 3 → m38 staff 4, "tie
  ignored... start does not occur temporally before end"). Detection is
  structural (id-bearing spanner group with zero drawables), no log
  parsing.
- **The systemDivider root cause is Verovio's `condense` option,
  default `"auto"` (10.4)**: at ≥2 staff-groups Verovio silently switches
  to condensed layout — hides empty staves per system (testscore 2-group:
  7/3/6/3/5 staff rows vs 7×5) and draws id-less `systemDivider` glyphs
  (2 polygons, direct child of `system`). `condense: "encoded"` restores
  the encoded layout: 2 groups → 10 grpSyms, ZERO dividers, and the
  0-group and 1-group renders are byte-identical to `auto`. That makes
  it a rule-7-reinforcing fixed adapter option (the
  transposeToSoundingPitch shape). SYSTEM_DIVIDER stays mapped anyway
  (ruling a) as defense.
- **Native-brace suppression**: video_test's piano brace is ONE grpSym
  per system (15 total); injecting a group that overlaps P5 (e.g.
  P4–P5) SUPPRESSES the native brace — still 1 symbol/system. Slot
  bookkeeping for grpSym identity would need suppression rules;
  geometric identity (which staves the symbol's bbox spans) is
  self-identifying (10.4).
- `bracketSpan` (1) and `mSpace` (2) are id-bearing, EMPTY `<g>`s on
  video_test — non-guard-fatal today; 10.4 registers them defensively.

## Phase 10 — video_test.musicxml triage (2026-07-13)

`testdata/video_test.musicxml` (real production score) does not load.
Both open defects (multi-bracket + this file) are the SAME class of bug:
the adapter was built against `testscore` and `broken_hairpin_and_slur_test`,
neither of which exercises multi-staff parts, system dividers, or several
notation classes. Root causes reproduced against the real files:

- **Multi-staff part (load-bearing).** Piano is `<staves>2</staves>` — ONE
  `<score-part id="P5">`, two staves. music21 splits it into `P5-Staff1` /
  `P5-Staff2` (8 parts); prep counts 7 score-parts. This single fact cascades:
  1. `build_score_model` raises `music21 sees 8 parts, prep sees 7`.
  2. `_attribute_ledger_dashes` raises: `page 2 m12 staff 2: ledger dash at
     x=674 matches no notehead` (attribution assumes single-staff geometry).
  3. `_attribute_spanner_segments` raises: `system 4: 6 tie continuation
     segment(s) but 9 crossing source spanner(s)`, then `_build_elements`
     raises `continuation tie segment in system 4 has no source element`.
     Verovio also warns "5 ties left open" / "tie ignored, start does not
     occur temporally before end" — grand-staff tie matching.

- **systemDivider (multi-bracket).** Injecting two disjoint part-groups into
  `testscore` validates and produces correct part-list XML, but Verovio then
  draws a `<g class="systemDivider">` (drawable) that the decomposer whitelist
  rejects → `ValueError: page 2: unknown SVG class 'systemDivider'`. One group
  never draws a divider. Reproduce: load testscore with two PartGroupSpecs.

- **New SVG classes, non-blocking.** `bracketSpan` and `mSpace` appear but are
  NON-drawable (don't hit the guard today); add to the container/ignore set
  defensively. New notation present — trill/`wavy-line`, `fermata`,
  `ornaments`, `strong-accent`, `ppp`, `wedge`, chord-symbol `bass` — maps to
  classes already whitelisted; renders once the load succeeds (verify visually).

Fixtures the prior two never exercised: multi-staff (grand-staff) parts;
two+ part-groups in a system (systemDivider); `ppp` dynamics; `wedge`
hairpins in this configuration; trill wavy-lines; chord-symbol bass notes.

## Phase R (2026-07-22) — adapter package split

`core/engraving/verovio_adapter.py` (1823 lines) was decomposed into the
`core/engraving/verovio/` package, one module per pipeline stage (kinds /
mei_index / records / decompose / attribution / identity / synthesis /
provider) and DELETED — imports repoint to the package. For spike
authors: the monkeypatch seams moved with the code. Patch
`verovio.decompose.parse_transform` (complex1_triage's rotate shim) and
`verovio.attribution._attribute_ledger_dashes` (both triage spikes) —
the provider calls stages module-qualified, so patching the old
verovio_adapter attributes would silently do nothing. Both triage spikes
were updated in the same commits that broke their seams and run
end-to-end. The golden suite (tests/goldens/, 12 loads byte-for-byte) is
the standing regression net for any adapter change.

## Beat-domain census (2026-07-22) — spikes/beat_domain.py

FINDING-1 fix groundwork: per fixture, the engraved timemap's measure
starts/spans (derived exactly as the provider derives them) against
music21's `measure.offset` / `barDuration`. Facts the fix builds on:

- **1:1 ordinal coverage holds everywhere**: every MEI measure ordinal
  has a timemap `measureOn` start on all 11 fixtures — the loud
  provider invariant is safe.
- **The timemap is playback-EXPANDED**: complex3's repeat (printed
  m35–36) emits second-pass clone measure ids (`e1jy649-rend2` at
  q147, `qa3bpe5-rend2` at q151) which the `measure_by_id` guard
  drops; the kept ordinal-37 span is 12 = 4 notated + 8 repeat pass.
  music21 never expands → −8 shear after the repeat. No duplicate
  note ids in `on`/`restsOn` — repeated bars' notes keep FIRST-pass
  qstamps.
- **music21 pads the X0 pickup to nominal length** (complex3 m1:
  engraved 1 beat, model 4 → +3 shear; pickup_min parses correctly
  with `paddingLeft=3`, so the padding behavior is export-dependent).
  Intra-measure note offsets start at 0 in BOTH cases — the rebase
  formula `starts[ordinal] + el.offset` needs no padding correction.
- **Half-beat bars round down in music21**: complex3 m52 (4.5 vs 4),
  complex2 m8 and m120 (4.5 vs 4) — so complex2 shears too (+0.5,
  then +1.0), previously unnoticed (the diagnosis never ran complex2).
- **music21 per-part accumulation self-diverges**: complex3 part 0
  drifts +7.75 beats from every other part by m78 (the 714
  notes-outside-measure finding). Per-ordinal rebasing erases it.
- **A trailing event-less bar has no timemap end**: bar_repeat_min's
  final bar-repeat measure gets engraved span 0 (score_end stops at
  its downbeat) → build_score_model floors the LAST measure's span
  with its notated length. Mid-score empty bars are safe (spans are
  next-downbeat deltas).

## Hide empty staves on the FIRST system (2026-07-24, during M1)

`spikes/hide_first_system.py`, verovio 6.2.1 — Marcus asked for an
option that drops the first-system-full convention:

- **`condenseFirstPage: true` is the knob**: on the Phase 10R optimize
  round-trip it extends empty-staff hiding to the first system —
  video_test staves/system goes 8,2,2,4,… → **4**,2,2,4,… with every
  other row and the page count unchanged. Despite the name it acts on
  the first SYSTEM group in our encoded-breaks setup.
- **Id- and timemap-transparent**: xml:ids and the timemap are
  identical with and without the option (both fixtures) — overrides,
  goldens, and the join are unaffected. The adapter still sets it only
  when the option is on, so default renders stay byte-identical.
- **Without optimize the option is inert** (nothing is being
  condensed); the adapter gates it on hide_empty_staves anyway, and
  the hide-unavailable fallback (slash regions, rule 10) drops both
  flags together.
- bigband1 shows no change (no staff is empty for a whole first
  system there) — the option only removes the convention exemption;
  which staves qualify stays Verovio's per-system emptiness rule.
