# Spike & build notes

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
