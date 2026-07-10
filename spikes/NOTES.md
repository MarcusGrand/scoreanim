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
   part as `<measure-style><slash type="start" use-stems="no"/>` with **no
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
