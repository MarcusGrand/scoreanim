# Systems-mode rework — staged plan

Parked 2026-08-29, to be tackled after the UI redesign (docs/UI_REDESIGN.md)
is finished. Each stage is one Claude Code prompt with its own check.

## The problem

In systems mode the view keeps the page's frame and re-frames per system
(`show_system_band` in `ui/stage_view.py`): a page-sized window centered on
the current system's band. Every switch is "move the camera to a different
part of the paper", so the paper visibly jumps on each switch, and user zoom
is thrown away by the re-fit.

## The target model

The frame is a fixed piece of glass; each system is placed into it.

1. One constant frame in systems mode: page width, constant height (tallest
   system band + padding; the video canvas frame when the overlay is on).
   Fit fits this frame. Identical for every system.
2. Each system vertically centered in the frame; horizontal position
   unchanged (page margins keep systems left-aligned with each other).
3. No visible page context — uniform background, no paper edge to act as a
   moving reference. Neighbor masking stays as today.
4. A switch preserves user zoom and pan: a pure camera translation by the
   delta between old and new band centers. Never fitInView on a switch.

Export shares the scenes and has its own systems framing — it must end up
following the same rule, or the stage stops being a preview (stage 4).

## Stage 1 — the fixed frame — BUILT 2026-08-30

Built on `systems-fixed-frame` (off `ui-e2-tooltips`). The frame is
`core/engraving/systems.py::systems_frame` — page width by tallest band
plus 6 % of that height each side, Marcus's number. Everything else in
the view generalised from "is there a canvas" to "is there a frame",
so the canvas path's solid fill and wobble-free fit now serve both.

Follow-up the same day, on Marcus's report: the mask was slicing the
title block. It masks to a NEIGHBOUR now, not to the band — nothing
shares the paper above the first system on a page, so there was nothing
to hide there.

> Work on a branch, commit when done. Use plan mode first.
>
> Systems mode, step 1 of a rework (docs/SYSTEMS_MODE_REWORK.md has the
> full picture): replace the per-system page frame with one constant frame.
> Compute it once per load: page width, height = tallest system band plus
> even padding. Present each system vertically centered in that frame,
> horizontal position unchanged. Hide all page context in systems mode —
> uniform background over the whole frame, no visible paper edge. Fit fits
> the frame. Keep today's switch mechanics otherwise (re-centering is fine
> for now; zoom preservation is the next step). Factor the frame
> computation as a pure function so it's headless-testable.
>
> Check: at default zoom, play across several system switches — the frame
> never changes size or position, no paper edge anywhere, each system
> appears centered. Systems with different staff counts don't resize
> anything.

## Stage 2 — switches preserve zoom and pan — BUILT 2026-08-30

Built on `systems-fixed-frame`. A zoomed switch no longer touches the
zoom: the view remembers where the frame sits ON SCREEN, in device
pixels, and puts it back there after the swap, which is the camera
translating by the delta between the two band centres. Fitted, nothing
changed — the fit it would land on is the one it already has.

The trap was `QGraphicsView.centerOn`, which rounds through the integer
scrollbars with a bias and crept one pixel per switch. The fix is the
same snap stage 1 used for the fit: two frames snapped to the same
sub-pixel phase are a whole number of device pixels apart, so the step
between them is exact. Pinned by a test that switches 60 times and comes
back to the same camera, to the bit.

> Systems mode, step 2: a system switch must preserve the user's zoom and
> pan. Implement the switch as a pure camera translation by the delta
> between the old and new band centers — never a fit. Zoomed to 200% on the
> left half of a system, a switch must show the new system at the same
> zoom and same screen position. Fit (Ctrl+0) still returns to the full
> frame. Manual prev/next takes the same path as follow-driven switches.
>
> Check: zoom in, let playback switch systems several times — zoom and
> position hold and the current system is always in view. Fit still works.
> Paged mode is completely unaffected.

Follow-up 2026-08-30, on Marcus's report — "small parts of neighbouring
systems still show inside the frame". The mask was doing its job and
still could not win: a band is the union of its elements' BBOXES, and
painted ink is bigger than that (text metrics, stroke widths, and
anything the animation scales), so a neighbour's ink stands outside its
own band — 1 page unit on testscore, 3 to 17 on grieg and condense — and
lands in the strip the mask must leave alone. Systems mode now filters
ITEMS: `ScoreScenes.set_visible_system` hides every system but the
current one, called from `ViewRouter.show_system` / `show_page`, which
are the only two routes into the stage. View-level presentation state,
never the document; the mask stays as the backstop for ink no system
owns (the title), and export builds its own scenes so it cannot see it.

## Stage 3 — the video canvas as the frame

> Systems mode, step 3: when the video-canvas overlay preview is on, the
> systems-mode frame becomes the canvas frame (preset/custom size, scale
> applied), instead of the page-width frame from step 1. Same rules: fixed
> frame, system centered, switches translate only.
>
> Check: toggle the overlay on and off in systems mode — the frame swaps
> between canvas and default cleanly, no jump on subsequent switches in
> either state.

## Stage 4 — export parity

Now two things, not one: export still frames with the pre-rework
page-sized window, AND it clips to a region the way the stage used to,
so it has the same neighbour leak the item filter fixed. Its private
scenes can take `set_visible_system` too.


> Systems mode, step 4: audit how export frames systems mode against the
> stage's new fixed-frame rule (docs/SYSTEMS_MODE_REWORK.md). If it
> already matches, document that in a comment where export frames systems
> and stop. If not, make export follow the same frame computation — share
> the pure function from step 1 rather than duplicating the math.
>
> Check: export a short clip in systems mode; frame-by-frame, the framing
> matches what the stage shows at Fit, including canvas-overlay runs.

## Optional stage 5 — transition polish

Only after living with stages 1–4: a short crossfade or vertical slide on
system switches (~150 ms), disabled during scrubbing. Decide then whether
it helps or distracts; hard cuts are the standard in score videos and may
be fine.
